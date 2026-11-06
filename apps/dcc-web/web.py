"""DCC Web: independently versioned, local-first Docker workspace."""
import argparse
import base64
from datetime import timedelta
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import secrets
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from flask import Flask, Response, abort, g, jsonify, redirect, render_template, request, send_file, session
from cryptography.fernet import InvalidToken
from markupsafe import Markup
from werkzeug.exceptions import HTTPException
from werkzeug.security import check_password_hash, generate_password_hash

from catalogs import Catalogs, InstalledCatalogScans, app_id, install_plan, validate_catalog
from markdown_render import render_markdown
from engine import DockerBackend, EngineError, Jobs
from security import initialize_security, admin, authorize, redact, validate_profile, CAPABILITIES, trusted_https_request
from state import State
from ports import container_revision,enrich_containers,inventory
from remote_access import (
    ACTIONS as REMOTE_ACTIONS, PORT as REMOTE_PORT,
    WORKSPACE_JOB_ACTIONS as REMOTE_WORKSPACE_JOB_ACTIONS, register_remote_access,
)
from profile_ssh import WORKSPACE_ACTIONS, MAX_FILE
from urllib.parse import urlsplit

VERSION = Path(__file__).with_name("VERSION").read_text(encoding="utf-8").strip()
THEMES = {"obsidian":"Obsidian Graphite", "violet":"Midnight Violet", "ocean":"Deep Ocean", "arctic":"Arctic Light", "emerald":"Emerald Terminal"}
DEFAULT_SETTINGS = {"theme":"ocean", "accent":"#72d9df", "intensity":65, "effects":True, "density":"comfortable", "animations":True, "language":"EN", "refresh":15, "refresh_changes_only":False, "terminal_limit":16, "check_updates_on_refresh":True, "audio":{"enabled":True,"master":40,"effects":60,"notifications":55,"style":"soft"}}
MCP_GRANT_ACTIONS={"mcp.grant.pause","mcp.grant.resume","mcp.grant.revoke","mcp.grant.delete-history"}
REMOTE_CONFIRMATIONS = {"remote-access." + action for action in REMOTE_ACTIONS}
REMOTE_WORKSPACE_JOBS = {"remote-access." + action for action in REMOTE_WORKSPACE_JOB_ACTIONS}


def profile_display_address(profile, info, panel_host):
    """Return the configured engine host, or the address used to open this panel for local profiles."""
    kind=profile.get('kind','local')
    address=''
    port=None
    if kind in {'ssh','balena'}:
        address=profile.get('host','')
        port=profile.get('port',22)
        try:
            port=int(port)
        except (TypeError,ValueError):
            port=None
        if port==22:
            port=None
    elif kind in {'tcp','tunnel'}:
        endpoint=urlsplit(profile.get('endpoint',''))
        address=endpoint.hostname or ''
        try:
            port=endpoint.port
        except ValueError:
            port=None
    elif kind in {'local','wsl'} and not profile.get('context'):
        parsed=urlsplit('//'+panel_host)
        address=parsed.hostname or ''
        try:
            port=parsed.port
        except ValueError:
            port=None
        if port in (80,443):
            port=None
    elif profile.get('panel_host'):
        address=profile['panel_host']
    if not address:
        address=(info.get('Swarm') or {}).get('NodeAddr','')
    if address and port:
        address=f'[{address}]' if ':' in address and not address.startswith('[') else address
        address+=f':{port}'
    return address


def provision_random_admin(state):
    """Create one strong, log-recoverable administrator for a fresh LAN install."""
    username = "admin"
    password = secrets.token_urlsafe(24)
    with state.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        if db.execute("SELECT 1 FROM users LIMIT 1").fetchone():
            return None
        db.execute(
            "INSERT INTO users VALUES(?,?,?,?)",
            (secrets.token_hex(12), username, generate_password_hash(password), "admin"),
        )
    return username, password


def create_app(config=None, backend_factory=None, terminal_factory=None):
    app = Flask(__name__)
    app.config.update(DATA_DIR=os.environ.get("DCC_WEB_DATA", str(Path.home()/".dcc-web")), ALLOWED_HOSTS={"localhost","127.0.0.1","::1"}, SESSION_COOKIE_NAME="dcc_web_session", SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Strict", SESSION_COOKIE_SECURE=os.environ.get("DCC_WEB_HTTPS")=="1", PUBLIC_ORIGIN=os.environ.get("DCC_WEB_PUBLIC_ORIGIN"), PERMANENT_SESSION_LIFETIME=timedelta(hours=12), MAX_CONTENT_LENGTH=2_000_000, MASTER_KEY=os.environ.get("DCC_WEB_MASTER_KEY"))
    if config:
        app.config.update(config)
    state = State(app.config["DATA_DIR"], app.config.get("MASTER_KEY"))
    from mfa import MFA
    state.mfa = MFA(state)
    from recovery import Recovery, register_recovery
    state.recovery = Recovery(state)
    app.secret_key = state.session_key
    catalogs = Catalogs(state, ROOT)
    installed_scans = InstalledCatalogScans()
    jobs = Jobs()
    factory = backend_factory or DockerBackend
    app.extensions.update(dcc_state=state, dcc_catalogs=catalogs, dcc_catalog_scans=installed_scans, dcc_jobs=jobs)
    initialize_security(app, state)
    def ui_language():
        requested=request.args.get('lang')
        if requested in {'PL','EN'}:return requested
        if g.get('user'):
            rows=state.rows('SELECT data FROM settings WHERE user_id=?',(g.user['id'],))
            if rows:return json.loads(rows[0]['data']).get('language','EN')
        return request.cookies.get('dcc_web_language','EN') if request.cookies.get('dcc_web_language') in {'PL','EN'} else 'EN'

    @app.context_processor
    def localized_templates():
        from translations import translate
        language=ui_language()
        return {'language':language,'tr':lambda value:translate(value,language)}

    @app.after_request
    def remember_language(response):
        if request.args.get('lang') in {'PL','EN'}:
            response.set_cookie('dcc_web_language',request.args['lang'],max_age=31536000,samesite='Strict',secure=app.config.get('SESSION_COOKIE_SECURE',False) or trusted_https_request(app))
        return response
    @app.before_request
    def validate_targets():
        target=(request.view_args or {}).get("target")
        if target and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,200}",target):
            abort(400,"Invalid container identifier")
    if not state.profiles():
        state.save_profile("local", {"name":"Local Docker", "kind":"local", "permissions":["read"]})

    from host_terminal import HostTerminals
    terminals=HostTerminals(terminal_factory)
    app.extensions['dcc_terminals']=terminals

    def body():
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            abort(400, "A JSON object is required")
        return data

    def profile(profile_id=None, capability="read"):
        value = state.profile(profile_id or request.args.get("profile", "local"), private=True)
        authorize(value, capability)
        return value

    def backend(profile_id=None, capability="read"):
        return factory(profile(profile_id, capability))

    def confirmed(data, action, profile_id, target):
        if not state.consume(data.get("confirmation", ""), session["sid"], action, profile_id, target):
            abort(409, "A fresh explicit confirmation is required")

    def start_job(p, action, work, progress=False):
        owner = g.user["id"]
        def audited(report=None):
            try:
                result = work(report) if progress else work()
                state.audit(owner, action, p["id"], 200)
                if action in {"install", "uninstall"}:
                    installed_scans.invalidate(p["id"])
                return result
            except Exception:
                state.audit(owner, action, p["id"], 500)
                raise
        return jsonify(redact(jobs.start(owner, p["id"], action, audited,progress=progress))), 202

    @app.errorhandler(Exception)
    def error_response(error):
        import paramiko
        if isinstance(error, HTTPException):
            code, message = error.code, error.description
        elif isinstance(error, (ValueError, KeyError, TypeError)):
            code, message = 400, str(error)[:250]
        elif isinstance(error, EngineError):
            code, message = 503, str(error)
        elif isinstance(error, InvalidToken):
            code, message = 500, "Saved profile credentials could not be decrypted. Restore the matching DCC Web data volume and master key together; do not delete either."
        elif isinstance(error, paramiko.SSHException):
            code, message = 503, 'SSH connection failed. Check the username, key, passphrase or SSH agent and trusted known_hosts in Profiles.'
        else:
            code, message = 500, "The request could not be completed"
        if request.path.startswith(("/api/","/mcp","/.well-known/")) or request.path in {'/authorize','/token','/register','/revoke'}:
            return jsonify(error=message), code
        if g.get("user"):
            return render_template("error.html",message=message,code=code),code
        return render_template("login.html", setup=False, error=message), code

    @app.get("/api/health")
    def health():
        return jsonify(status="ok", version=VERSION)

    @app.route("/login", methods=["GET","POST"])
    @app.route("/setup", methods=["GET","POST"])
    def login():
        setup = not state.rows("SELECT id FROM users LIMIT 1")
        if request.path=="/setup" and not setup:
            return redirect("/login")
        if setup and (request.remote_addr not in {"127.0.0.1","::1"} or app.config.get("PUBLIC_ORIGIN")):
            abort(403, "Initial setup is available only from localhost")
        error = ""
        if request.method=="POST":
            username, password = request.form.get("username",""), request.form.get("password", "")
            if len(username)>64 or len(password)>256:
                abort(400,"Invalid credential length")
            address = "remote-access-login" if g.get("dcc_remote") else hashlib.sha256(str(request.remote_addr).encode()).hexdigest()
            recent = state.rows("SELECT COUNT(*) AS total FROM attempts WHERE address=? AND at>?", (address,time.time()-600))[0]["total"]
            if recent >= 8:
                abort(429, "Too many attempts. Try again in ten minutes.")
            state.execute("DELETE FROM attempts WHERE at<?", (time.time()-3600,))
            if setup:
                if not re.fullmatch(r"[\w.@-]{3,64}", username) or not 12<=len(password)<=256:
                    error = "Nazwa: 3–64 znaki. Hasło: co najmniej 12 znaków."
                else:
                    with state.connect() as db:
                        db.execute("BEGIN IMMEDIATE")
                        if db.execute("SELECT COUNT(*) FROM users").fetchone()[0]:
                            abort(409, "Initial setup has already completed")
                        db.execute("INSERT INTO users VALUES(?,?,?,?)", (secrets.token_hex(12),username,generate_password_hash(password),"admin"))
            users = state.rows("SELECT * FROM users WHERE name=?", (username,))
            user = users[0] if users else None
            mfa = user and state.mfa.enabled(user["id"])
            remote_admin_without_mfa = user and g.get("dcc_remote") and user["role"] == "admin" and not mfa
            if not error and user and not remote_admin_without_mfa and check_password_hash(user["password"],password) and (not mfa or state.mfa.verify(user["id"],request.form.get("otp"))):
                # Keep the pending MCP approval target across session rotation.
                # The new session must still review the challenge and use fresh 2FA.
                next_mcp = session.get('mcp_login_next')
                session.clear()
                session["sid"], session["csrf"] = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
                session.permanent = True
                session['mfa_verified'] = state.mfa.enabled(users[0]['id'])
                state.execute("INSERT INTO sessions VALUES(?,?,?)", (hashlib.sha256(session["sid"].encode()).hexdigest(),users[0]["id"],time.time()+43200))
                state.audit(users[0]["id"],"login","session",200)
                return redirect('/mcp-approve/'+next_mcp if isinstance(next_mcp,str) and re.fullmatch(r'[A-Za-z0-9_-]{40,50}',next_mcp) else '/')
            state.execute("INSERT INTO attempts VALUES(?,?)", (address,time.time()))
            error = error or "Nieprawidłowa nazwa użytkownika lub hasło."
        return render_template("login.html", setup=setup, error=error)

    @app.post("/api/logout")
    def logout():
        app.extensions['dcc_mcp_http'].oauth.revoke_user(g.user['id'])
        state.execute("DELETE FROM sessions WHERE token=?", (hashlib.sha256(session["sid"].encode()).hexdigest(),))
        session.clear()
        return jsonify(ok=True)

    def reauthenticate(data, second_factor=True):
        address = 'account:' + g.user['id']
        recent = state.rows('SELECT COUNT(*) AS total FROM attempts WHERE address=? AND at>?', (address,time.time()-600))[0]['total']
        if recent >= 8:
            abort(429, 'Too many attempts. Try again in ten minutes.')
        valid = isinstance(data.get('current_password'), str) and len(data['current_password']) <= 256 and check_password_hash(g.user['password'],data['current_password'])
        if valid and second_factor and state.mfa.enabled(g.user['id']):
            valid = state.mfa.verify(g.user['id'],data.get('otp'))
        if not valid:
            state.execute('INSERT INTO attempts VALUES(?,?)', (address,time.time()))
            abort(403, 'Invalid password or 2FA code')

    def revoke_other_sessions():
        current = hashlib.sha256(session['sid'].encode()).hexdigest()
        state.execute('DELETE FROM sessions WHERE user_id=? AND token!=?', (g.user['id'],current))

    register_recovery(app,state,reauthenticate)
    from host_setup import register_host_setup
    register_host_setup(app,state,reauthenticate,confirmed)
    from panel_proxy import register_panels, panel_links
    register_panels(app,factory,profile,app.extensions['dcc_domains'],catalogs.host_panel_ports,state)

    @app.get('/api/account/2fa')
    def mfa_status():
        return jsonify(enabled=state.mfa.enabled(g.user['id']))

    @app.post('/api/account/2fa/setup')
    def mfa_setup():
        reauthenticate(body())
        return jsonify(state.mfa.begin(g.user['id'],g.user['name'],session['sid']))

    @app.post('/api/account/2fa/enable')
    def mfa_enable():
        data = body()
        reauthenticate(data,second_factor=False)
        try:
            codes = state.mfa.enable(g.user['id'],data.get('otp'),session['sid'])
        except ValueError:
            state.execute('INSERT INTO attempts VALUES(?,?)', ('account:'+g.user['id'],time.time()))
            raise
        session['mfa_verified'] = True
        revoke_other_sessions()
        app.extensions['dcc_mcp_http'].oauth.revoke_user(g.user['id'])
        return jsonify(recovery_codes=codes)

    @app.post('/api/account/2fa/disable')
    def mfa_disable():
        data = body()
        reauthenticate(data,second_factor=False)
        try:
            state.mfa.disable(g.user['id'],data.get('otp'))
        except ValueError:
            state.execute('INSERT INTO attempts VALUES(?,?)', ('account:'+g.user['id'],time.time()))
            raise
        session['mfa_verified'] = False
        revoke_other_sessions()
        app.extensions['dcc_mcp_http'].oauth.revoke_user(g.user['id'])
        return jsonify(ok=True)

    @app.get("/")
    def index():
        if not g.user:
            return redirect("/login")
        return render_template("index.html", version=VERSION)

    @app.get("/about")
    def about():
        return render_template("about.html", version=VERSION)

    @app.get("/docs/<name>")
    def documentation(name):
        allowed = {"installation","configuration","profiles-security","security","catalogs","mcp","ai","themes-audio","feature-matrix","testing","panels"}
        if name not in allowed:
            abort(404)
        labels = {"installation":"Instalacja i uruchamianie","configuration":"Profile i konfiguracja","profiles-security":"Profile, klucze i 2FA","security":"Bezpieczeństwo","catalogs":"Sklep i katalogi","mcp":"AI / MCP","ai":"Asystent AI","themes-audio":"Motywy i dźwięki","feature-matrix":"Macierz funkcji desktop / web","testing":"Testy i ograniczenia"}
        language = ui_language()
        docs = Path(__file__).parent/"docs"
        labels['panels']='Panele kontenerów'
        localized = docs/(name+".pl.md") if language == "PL" else docs/(name+".md")
        source = (localized if localized.is_file() else docs/(name+".md")).read_text(encoding="utf-8")
        return render_template("documentation.html", doc_name=name, doc_label=labels[name], version=VERSION, rendered_content=Markup(render_markdown(source, allowed, language=language)))

    @app.get("/api/bootstrap")
    def bootstrap():
        rows = state.rows("SELECT data FROM settings WHERE user_id=?", (g.user["id"],))
        settings = dict(DEFAULT_SETTINGS, **(json.loads(rows[0]["data"]) if rows else {}))
        settings["refresh"]=max(15,min(900,int(settings.get("refresh",15))))
        settings["refresh_changes_only"]=bool(settings.get("refresh_changes_only",False))
        profiles = []
        for p in state.profiles():
            if not p.get("users") or g.user["id"] in p["users"] or g.user["role"]=="admin":
                profiles.append(p)
        return jsonify(user={key:g.user[key] for key in ("id","name","role")}, profiles=profiles, settings=settings, themes=THEMES, version=VERSION,features={'host_terminal':True,'access_details':True,'installation_progress':True})

    @app.post("/api/confirmations")
    def confirmation():
        data = body()
        action, target = str(data.get("action","")), str(data.get("target",""))
        if action in WORKSPACE_ACTIONS or action in MCP_GRANT_ACTIONS or action in REMOTE_CONFIRMATIONS:
            admin()
            profile_id = "workspace"
        else:
            profile_id = profile(data.get("profile","local"))["id"]
        if len(action)>100 or len(target)>200:
            abort(400)
        return jsonify(confirmation=state.confirm(session["sid"],action,profile_id,target),expires_in=120)

    @app.route("/api/profiles", methods=["GET","POST"])
    def profiles():
        if request.method=="GET":
            return jsonify(profiles=[p for p in state.profiles() if not p.get("users") or g.user["id"] in p["users"] or g.user["role"]=="admin"])
        admin()
        data = body()
        value = validate_profile(data)
        profile_id = secrets.token_hex(10)
        with state.ssh.lock:
            state.save_profile(profile_id,value,data.get("credentials",{}))
        return jsonify(id=profile_id),201

    @app.route("/api/profiles/<profile_id>", methods=["PUT","DELETE"])
    def edit_profile(profile_id):
        admin()
        with state.ssh.lock:
            old = state.profile(profile_id)
            authorize(old)
            data = body()
            if request.method=="DELETE":
                confirmed(data,"profile.remove",profile_id,profile_id)
                state.execute("DELETE FROM profiles WHERE id=?",(profile_id,))
                terminals.close_profiles({profile_id})
            else:
                # Edit stored public paths, never resolved runtime paths or credentials.
                merged = {key:value for key,value in old.items() if key != "id"}
                merged.update(data)
                state.save_profile(profile_id,validate_profile(merged),data.get("credentials"))
        return jsonify(ok=True)

    @app.post("/api/profiles/import")
    def import_profiles():
        admin()
        payload = body()
        data = payload.get("profiles")
        if not isinstance(data,list) or len(data)>100:
            abort(400,"A profiles array is required")
        added, prepared = [], []
        from profile_ssh import key_name
        files = {f['name'] for f in state.ssh.settings()['files'] if f['kind'] == 'private key'}
        for entry in data:
            if not isinstance(entry,dict):
                abort(400)
            if "mode" in entry:
                target = entry.get("ssh_target", "")
                username, _, host = target.rpartition("@")
                entry = {"name":entry["name"],"kind":"ssh" if entry.get("mode")=="ssh" else "tunnel","username":entry.get("ssh_username") or username,"host":host.strip('[]'),"port":entry.get("ssh_port") or 22,"endpoint":entry.get("base_url",""),"key_path":entry.get("ssh_key_path",""),"permissions":["read"]}
            if payload.get('shared_keys') is True and entry.get('kind') in {'ssh', 'balena'}:
                filename = key_name(entry.get('key_path'))
                if filename in files:
                    entry = dict(entry, key_scope='shared', key_path=filename)
            value = validate_profile(entry)
            prepared.append(value)
        for value in prepared:
            ident = secrets.token_hex(10)
            with state.ssh.lock:
                state.save_profile(ident,value,{})
            added.append(ident)
        return jsonify(added=added, note="Credentials are never imported in plaintext; configure them separately")

    @app.route("/api/profiles/export",methods=['GET','POST'])
    def export_profiles():
        admin()
        if request.method == 'GET':
            abort(400,'Use password-protected profile export')
        from profile_transfer import ProfileTransfer
        data = body()
        reauthenticate(data)
        with state.ssh.lock:
            return jsonify(ProfileTransfer(state).export(data.get('ids'),data.get('backup_password'),data.get('include_secrets') is True))

    @app.post('/api/profiles/transfer/preview')
    @app.post('/api/profiles/transfer')
    def transfer_profiles():
        admin()
        from profile_transfer import ProfileTransfer
        data = body()
        with state.ssh.lock:
            transfer = ProfileTransfer(state)
            plan, prepared, files = transfer.plan(data.get('contents'),data.get('backup_password',''),data.get('indices'),data.get('shared_keys') is True,data.get('replace') is True)
            if request.path.endswith('/preview'):
                return jsonify(plan)
            confirmed(data,'profiles.transfer','workspace',plan['target'])
            return jsonify(added=transfer.apply(prepared,files))

    @app.post('/api/profiles/check')
    def check_profile():
        admin()
        data = body()
        value = validate_profile(data.get('configuration',{}))
        secret = data.get('credentials',{})
        if not isinstance(secret,dict) or any(not isinstance(v,str) or len(v)>8192 for v in secret.values()):
            abort(400,'Invalid profile credentials')
        if data.get('existing_id'):
            previous = state.profile(str(data['existing_id']),private=True)['credentials']
            previous.pop('private_key',None)
            secret = dict(previous,**secret)
        value = state.ssh.resolve(dict(value,credentials=secret))
        info = factory(value).info()
        return jsonify(ok=True,name=info.get('Name'),version=info.get('ServerVersion'))

    @app.get("/api/profile-ssh")
    def profile_ssh_settings():
        admin()
        return jsonify(state.ssh.settings())

    @app.post("/api/profile-ssh/directory/preview")
    def ssh_directory_preview():
        admin()
        with state.ssh.lock:
            return jsonify(state.ssh.directory_plan(body().get("directory")))

    @app.put("/api/profile-ssh/directory")
    def ssh_directory_save():
        admin()
        data = body()
        with state.ssh.lock:
            plan = state.ssh.directory_plan(data.get("directory"))
            confirmed(data, "profiles.ssh.directory", "workspace", plan["target"])
            state.ssh.set_directory(plan["directory"])
        return jsonify(ok=True)

    @app.post("/api/profiles/bulk/preview")
    def profiles_bulk_preview():
        admin()
        data = body()
        with state.ssh.lock:
            return jsonify(state.ssh.bulk_plan(data.get("action"), data.get("ids")))

    @app.post("/api/profiles/bulk")
    def profiles_bulk():
        admin()
        data = body()
        action = data.get("action")
        with state.ssh.lock:
            plan = state.ssh.bulk_plan(action, data.get("ids"))
            confirmed(data, action, "workspace", plan["target"])
            state.ssh.apply_bulk(action, plan)
            if action == "profiles.remove.selected":
                terminals.close_profiles({p["id"] for p in plan["changes"]})
        return jsonify(changed=len(plan["changes"]), skipped=len(plan["skipped"]))

    @app.post("/api/profile-ssh/files/preview")
    @app.post("/api/profile-ssh/files")
    def ssh_upload():
        admin()
        uploads = request.files.getlist("files")
        if not 1 <= len(uploads) <= 20:
            abort(400, "Select at most 20 SSH files with a total size of 1 MiB")
        files = [(item.filename, item.stream.read(MAX_FILE + 1)) for item in uploads]
        replace = request.form.get("replace") == "true"
        with state.ssh.lock:
            plan = state.ssh.file_plan(files, replace)
            if request.path.endswith("/preview"):
                # Metadata only: never return, audit or persist uploaded private material here.
                return jsonify(plan)
            confirmed(request.form, "profiles.ssh.files", "workspace", plan["target"])
            state.ssh.write_files(files)
        return jsonify(ok=True, files=[f["name"] for f in plan["files"]])

    @app.post('/api/profile-ssh/files/delete/preview')
    @app.post('/api/profile-ssh/files/delete')
    def ssh_delete():
        admin()
        data = body()
        with state.ssh.lock:
            plan = state.ssh.delete_plan(data.get('names'))
            if request.path.endswith('/preview'):
                return jsonify(plan)
            confirmed(data, 'profiles.ssh.remove', 'workspace', plan['target'])
            state.ssh.delete_files(plan)
            terminals.close_profiles({p['id'] for p in plan['profiles']})
        return jsonify(ok=True)


    @app.get("/terminal")
    def terminal_page():
        if not g.user:return redirect("/login")
        admin()
        p=profile(request.args.get("profile"))
        return render_template("terminal.html",profile_id=p["id"])

    def terminal_dimensions(data):
        cols,rows=int(data.get("cols",120)),int(data.get("rows",32))
        if not 20<=cols<=300 or not 5<=rows<=120:abort(400,"Invalid terminal dimensions")
        return cols,rows

    def terminal_session(terminal_id):
        admin()
        try:value=terminals.get(terminal_id,g.user["id"],hashlib.sha256(session["sid"].encode()).hexdigest())
        except KeyError:abort(404,"Terminal session is unavailable")
        profile(value.profile,"host.exec")
        return value

    @app.post("/api/host-terminal")
    def open_host_terminal():
        admin()
        browser_host=(urlsplit(request.host_url).hostname or "").lower()
        protected=trusted_https_request(app) or (app.config.get('SESSION_COOKIE_SECURE') and str(app.config.get('PUBLIC_ORIGIN','')).startswith('https://'))
        origin=urlsplit(request.headers.get('Origin',''))
        local_http=(
            request.scheme=='http'
            and browser_host in {'localhost','127.0.0.1','::1'}
            and (origin.hostname or '').lower() in {'localhost','127.0.0.1','::1'}
            and origin.scheme=='http'
            and origin.netloc.lower()==request.host.lower()
        )
        # Docker port publishing can make Flask see the bridge gateway as
        # REMOTE_ADDR even when the browser opened the panel on loopback.
        # Trust the validated loopback Host/Origin pair instead of that peer IP.
        if not protected and not local_http:
            abort(403,'Host terminals require HTTPS outside the local computer')
        data=body()
        p=profile(data.get("profile"),"host.exec")
        confirmed(data,"host.terminal",p["id"],p["id"])
        cols,rows=terminal_dimensions(data)
        preferences=state.rows('SELECT data FROM settings WHERE user_id=?',(g.user['id'],))
        limit=int(json.loads(preferences[0]['data']).get('terminal_limit',16)) if preferences else 16
        value=terminals.open(p,g.user["id"],hashlib.sha256(session["sid"].encode()).hexdigest(),cols,rows,limit=limit)
        state.audit(g.user["id"],"host.terminal.open",p["id"],200)
        address = profile_display_address(p, {}, request.host) if p['kind'] in {'ssh', 'balena'} else ''
        return jsonify(id=value.id,profile=p["id"],address=address),201

    @app.get("/api/host-terminal/<terminal_id>")
    def host_terminal_output(terminal_id):
        value=terminal_session(terminal_id)
        offset=int(request.args.get("offset",0))
        if offset<0:abort(400,"Invalid terminal output offset")
        return jsonify(value.output(offset))

    @app.post("/api/host-terminal/<terminal_id>/input")
    def host_terminal_input(terminal_id):
        value=terminal_session(terminal_id)
        data=body().get("data","")
        if not isinstance(data,str) or not 1<=len(data)<=16384:abort(400,"Invalid terminal input")
        try:raw=base64.b64decode(data,validate=True)
        except ValueError:abort(400,"Invalid terminal input")
        if value.closed:abort(409,"Terminal session ended")
        value.touched=time.monotonic()
        value.connection.write(raw)
        if b"\r" in raw or b"\n" in raw:state.audit(g.user["id"],"host.terminal.command",value.profile,200)
        return jsonify(ok=True)

    @app.post("/api/host-terminal/<terminal_id>/resize")
    def resize_host_terminal(terminal_id):
        value=terminal_session(terminal_id)
        cols,rows=terminal_dimensions(body())
        value.connection.resize(cols,rows)
        return jsonify(ok=True)

    @app.post("/api/host-terminal/<terminal_id>/close")
    def close_host_terminal(terminal_id):
        value=terminal_session(terminal_id)
        terminals.close(terminal_id,g.user["id"],hashlib.sha256(session["sid"].encode()).hexdigest())
        state.audit(g.user["id"],"host.terminal.close",value.profile,200)
        return jsonify(ok=True)

    @app.get("/api/infrastructure")
    def infrastructure():
        selected=profile()
        info=factory(selected).info()
        from profile_facts import remember
        remember(state, selected, info)
        address=profile_display_address(selected,info,request.host)
        return jsonify(available=True,name=info.get('Name',''),address=address,operating_system=info.get('OperatingSystem',''),os_type=info.get('OSType',''),architecture=info.get('Architecture',''),docker_version=info.get('ServerVersion',''),cpus=info.get('NCPU',0),memory_bytes=info.get('MemTotal',0),kernel_version=info.get('KernelVersion',''))

    @app.get("/api/overview")
    def overview():
        engine = backend()
        info, containers = engine.info(), engine.containers()
        info['HostAddress']=info['address']=profile_display_address(engine.profile,info,request.host)
        return jsonify(info=redact(info), revision=container_revision(containers), containers=panel_links(containers,engine.profile,app.extensions['dcc_domains'],app,catalogs.host_panel_ports()))

    @app.get("/api/containers")
    def containers():
        engine=backend()
        raw=engine.containers()
        values = panel_links(raw,engine.profile,app.extensions['dcc_domains'],app,catalogs.host_panel_ports())
        query = request.args.get("q","").casefold()
        status = request.args.get("status","")
        return jsonify(revision=container_revision(raw),containers=[v for v in values if query in json.dumps(v).casefold() and (not status or v.get("State")==status)])

    @app.get("/api/containers/revision")
    def containers_revision():
        return jsonify(revision=backend().container_revision())

    @app.get("/api/containers/<target>")
    def inspect_container(target):
        return jsonify(redact(backend().inspect(target)))

    @app.post("/api/containers/<target>/<action>")
    def container_action(target,action):
        data = body()
        p = profile(data.get("profile"),"destructive" if action=="remove" else "containers.write")
        confirmed(data,"container."+action,p["id"],target)
        return jsonify(output=jobs.execute(p['id'],lambda:factory(p).action(target,action)))

    @app.post("/api/exec/<target>")
    def exec_container(target):
        import shlex
        data = body()
        p = profile(data.get("profile"),"exec")
        command = data.get("command", "")
        if not isinstance(command,str) or not 1<=len(command)<=4096:
            abort(400,"A container command is required")
        confirmed(data,"container.exec",p["id"],target)
        return jsonify(output=jobs.execute(p['id'],lambda:factory(p).run(["exec",target,*shlex.split(command)],timeout=30)))

    @app.post("/api/bulk")
    def bulk():
        data = body()
        action, targets = data.get("action"), data.get("targets",[])
        if action not in {"start","stop","restart","pause","unpause","remove","autostart-on","autostart-off"} or not isinstance(targets,list) or not 1<=len(targets)<=100 or len(targets)!=len(set(v for v in targets if isinstance(v,str))) or not all(isinstance(v,str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,200}",v) for v in targets):
            abort(400,"Invalid bulk operation")
        p = profile(data.get("profile"),"destructive" if action=="remove" else "containers.write")
        confirmed(data,"bulk."+action,p["id"],hashlib.sha256(json.dumps(targets,separators=(",",":")).encode()).hexdigest())
        engine = factory(p)
        def work():
            result=[]
            for target in targets:
                try:
                    engine.action(target,action)
                    result.append({"container":target,"ok":True})
                except EngineError as error:
                    result.append({"container":target,"ok":False,"error":redact(str(error))})
            return result
        return start_job(p,"bulk."+action,work)

    @app.get("/api/logs/<target>")
    def logs(target):
        engine = backend()
        tail = int(request.args.get("tail",200))
        text = redact(engine.logs(target,tail))
        query = request.args.get("q","").casefold()
        if query:
            text = "\n".join(line for line in text.splitlines() if query in line.casefold())
        if request.args.get("download")=="1":
            return Response(text,mimetype="text/plain",headers={"Content-Disposition":"attachment; filename=container.log"})
        return jsonify(logs=text,lines=len(text.splitlines()))

    @app.get("/api/monitoring")
    def monitoring():
        p = profile()
        values = factory(p).stats()
        state.sample(p["id"],values)
        history = state.rows("SELECT at,data FROM samples WHERE profile=? ORDER BY id DESC LIMIT 120",(p["id"],))
        return jsonify(stats=values,history=[{"at":row["at"],"stats":json.loads(row["data"])} for row in reversed(history)])

    @app.get("/api/resources/<kind>")
    def resources(kind):
        if kind not in {"images","volumes","networks"}:
            abort(404)
        return jsonify(resources=backend().resources(kind))

    @app.post("/api/resources/<kind>/<action>")
    def resource_action(kind,action):
        data = body()
        if kind not in {"images","volumes","networks"} or action not in {"create","remove","pull","tag","inspect"}:
            abort(400)
        target = str(data.get("target",""))
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_./:@-]{0,250}",target):
            abort(400,"Invalid resource name")
        p = profile(data.get("profile"),"read" if action=="inspect" else "destructive" if action=="remove" else kind+".write")
        engine = factory(p)
        command = {"images":"image","volumes":"volume","networks":"network"}[kind]
        if action=="inspect":
            return jsonify(redact(engine.json([command,"inspect",target])))
        confirmed(data,kind+"."+action,p["id"],target)
        if kind=="volumes" and action=="remove":
            if data.get("delete_data") is not True:
                abort(409,"Deleting a volume requires explicit consent to irreversible data loss")
            for container in engine.containers():
                if any(m.get("Name")==target for m in engine.inspect(container["ID"]).get("Mounts",[])):
                    abort(409,"This volume is still attached to a container")
        args = [command,"rm",target] if action=="remove" else [command,action,target]
        if kind=="images" and action=="tag":
            destination = str(data.get("destination",""))
            if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_./:@-]{0,250}",destination):
                abort(400)
            args.append(destination)
        return start_job(p,kind+"."+action,lambda: engine.run(args,timeout=300))

    @app.get("/api/catalog")
    def catalog():
        p = profile()
        scan = installed_scans.profile_state(p["id"])
        installed_map = scan["installed_map"]
        remote = app.extensions["dcc_remote_access"]
        result = catalogs.view(request.args.get("lang","PL"),query=request.args.get("q",""),category=request.args.get("category","all"),
                               engine_kind="balena" if p["kind"]=="balena" else "docker",installed_map=installed_map,
                               managed_remote_name=remote.name if remote.available and p["kind"]=="local" and not p.get("context") else None)
        return jsonify(**result,connected=True if installed_map is not None else (False if scan["error"] else None),
                       installed_known=installed_map is not None,installed_pending=scan["pending"],installed_error=scan["error"],sources=catalogs.sources())

    @app.post("/api/catalog/installed")
    def scan_catalog_installed():
        data = body()
        p = profile(data.get("profile"))
        def work():
            containers = factory(p).containers()
            remote = app.extensions["dcc_remote_access"]
            result = catalogs.view("PL",containers=containers,engine_kind="balena" if p["kind"]=="balena" else "docker",
                                   managed_remote_name=remote.name if remote.available and p["kind"]=="local" and not p.get("context") else None)["apps"]
            return {item["id"]:{"installed":item["installed"],"installed_ids":item["installed_ids"]} for item in result}
        value = installed_scans.begin(g.user["id"],p["id"],work,force=data.get("force") is True)
        return jsonify(value),202

    @app.get("/api/catalog/installed/<scan_id>")
    def scan_catalog_status(scan_id):
        value = installed_scans.snapshot(scan_id,g.user["id"])
        if not value:
            abort(404)
        profile(value["profile"])
        return jsonify(value)

    @app.route("/api/catalog/sources",methods=["GET","POST"])
    def sources():
        if request.method=="GET":
            return jsonify(sources=catalogs.sources())
        admin()
        data = body()
        return jsonify(id=catalogs.add(data.get("source",""),data.get("contents"))),201

    @app.route("/api/catalog/sources/<source_id>",methods=["PUT","DELETE"])
    def edit_source(source_id):
        admin()
        rows = state.rows("SELECT * FROM sources WHERE id=?",(source_id,))
        if not rows:
            abort(404)
        if rows[0]["canonical"]:
            abort(409,"The main DCC catalog cannot be disabled or removed")
        if request.method=="DELETE":
            state.execute("DELETE FROM sources WHERE id=?",(source_id,))
        else:
            state.execute("UPDATE sources SET enabled=? WHERE id=?",(bool(body().get("enabled")),source_id))
        return jsonify(ok=True)

    @app.post("/api/catalog/validate")
    def validate_source():
        admin()
        return jsonify(count=len(validate_catalog(body().get("contents"))))

    @app.get("/api/catalog/sources/<source_id>/apps")
    def source_contents(source_id):
        rows=state.rows("SELECT cache FROM sources WHERE id=?",(source_id,))
        if not rows:
            abort(404)
        return jsonify(apps=json.loads(rows[0]["cache"] or "[]"))

    @app.get("/media")
    def media():
        if not g.user:
            abort(401)
        path=(ROOT/request.args.get("path","")).resolve()
        allowed=[(ROOT/"catalog/media").resolve(),(ROOT/"catalog-assets").resolve()]
        if not any(path.is_relative_to(root) for root in allowed) or path.suffix.lower() not in {".png",".jpg",".jpeg",".webp"} or not path.is_file():
            abort(404)
        return send_file(path,conditional=True)

    @app.post("/api/catalog/refresh")
    def refresh_catalog():
        admin()
        p = profile()
        return start_job(p,"catalog.refresh",lambda:catalogs.refresh())

    @app.post("/api/install/preview")
    def preview_install():
        data = body()
        p = profile(data.get("profile"),"install")
        if catalogs.managed_remote and data.get("app") == catalogs.managed_remote["id"]:
            abort(400, "Install DCC Remote Access through the managed settings.")
        apps = catalogs.all()
        app_entry = next((item for item in apps if item["id"]==data.get("app")),None)
        if app_entry is None:
            # Manual creation uses the same validation and confirmation path.
            app_entry = {"name":"Manual", "image":data.get("configuration",{}).get("image", ""), "category":"Inne"}
        plan = install_plan(app_entry,data.get("configuration",{}),factory(p))
        return jsonify(redact(plan))

    @app.post("/api/install/ports")
    def installation_ports():
        data=body()
        return jsonify(inventory(backend(data.get('profile')),data.get('ports',[])))

    @app.post("/api/install")
    def install():
        data = body()
        p = profile(data.get("profile"),"install")
        configuration=data.get("configuration",{})
        if not isinstance(configuration,dict):
            abort(400,"Invalid installation configuration")
        app_id=data.get("app")
        app_entry=next((item for item in catalogs.all() if item["id"]==app_id),None) if app_id else None
        if app_id and app_entry is None:
            abort(404,"App not found in the current catalog")
        if app_entry is None:
            app_entry={"name":"Manual","image":configuration.get("image", ""),"category":"Inne"}
        confirmed(data,"install",p["id"],data.get("app") or configuration.get("name") or app_entry.get("default_name") or "dcc-app")
        from installation import execute_install
        language=ui_language()
        acknowledged=data.get("acknowledged",[])
        if not isinstance(acknowledged,list) or not all(isinstance(value,str) for value in acknowledged):
            abort(400,"Invalid installation acknowledgements")
        def work(report):
            engine=factory(p)
            plan=install_plan(app_entry,configuration,engine)
            if set(plan["warnings"])-set(acknowledged):
                raise ValueError("Acknowledge the Docker socket, privileges and persistent data warnings")
            trusted=next((v for v in catalogs.fallback if v.get('name')==app_entry.get('name') and v.get('image')==app_entry.get('image')),None)
            return execute_install(engine,plan,app_entry,report,state.vault,trusted,language)
        return start_job(p,"install",work,progress=True)

    @app.post("/api/build")
    def build_image():
        data=body()
        p=profile(data.get("profile"),"install")
        entry=next((v for v in catalogs.all() if v["id"]==data.get("app")),None)
        if not entry or not re.fullmatch(r"https://github\.com/[\w.-]+/[\w.-]+\.git(?:#[\w./:-]+)?",entry.get("build_context","")):
            abort(400,"Only an explicitly reviewed GitHub build context is accepted")
        dockerfile=entry.get("build_dockerfile") or "Dockerfile"
        if ".." in Path(dockerfile).parts or not re.fullmatch(r"[\w./-]+",dockerfile):
            abort(400,"Invalid build Dockerfile")
        if data.get("reviewed_source") is not True:
            abort(409,"Explicit review of the source repository and Dockerfile is required")
        confirmed(data,"build",p["id"],entry["id"])
        return start_job(p,"build",lambda:factory(p).run(["build","--tag",entry["image"],"--file",dockerfile,entry["build_context"]],timeout=900))

    @app.get("/api/jobs/<job_id>")
    def job(job_id):
        value = jobs.history.get(job_id)
        if not value or value["owner"]!=g.user["id"]:
            abort(404)
        if value["action"] in REMOTE_WORKSPACE_JOBS:
            admin()
        else:
            profile(value["profile"])
        with jobs.lock:
            snapshot={key:item for key,item in value.items() if key not in {"owner","access_blob"}}
        return jsonify(redact(snapshot))

    @app.post("/api/jobs/<job_id>/access")
    def reveal_install_access(job_id):
        admin()
        value=jobs.history.get(job_id)
        if not value or value['owner']!=g.user['id']:abort(404)
        profile(value['profile'],'install')
        blob=value.get('access_blob')
        details=json.loads(state.vault.decrypt(blob.encode())) if blob else []
        state.audit(g.user['id'],'install.access.reveal',job_id,200)
        return jsonify(details=details)

    @app.post("/api/logs/<target>/access")
    def reveal_log_access(target):
        admin()
        data=body()
        engine=backend(data.get('profile'),'install')
        from dcc_catalog import parse_access_details
        details=parse_access_details(engine.logs(target,300),lang=ui_language())
        state.audit(g.user['id'],'container.access.reveal',target,200)
        return jsonify(details=[{'label':label,'value':value} for label,value in details])

    @app.post("/api/uninstall")
    def uninstall():
        data = body()
        p = profile(data.get("profile"),"destructive")
        app_entry=next((v for v in catalogs.all() if v["id"]==data.get("app")),None)
        if not app_entry:
            abort(404,"App not found in the current catalog")
        confirmed(data,"uninstall",p["id"],app_entry["id"])
        def work():
            engine=factory(p)
            containers=engine.containers()
            entry=next((v for v in catalogs.view(containers=containers)["apps"] if v["id"]==app_entry["id"]),None)
            if not entry or not entry["installed_ids"]:
                raise ValueError("No installed containers match this app")
            for target in entry["installed_ids"]:
                value=engine.inspect(target)
                if value.get("State",{}).get("Running"):
                    engine.action(target,"stop")
                engine.action(target,"remove")
            return {"removed":len(entry["installed_ids"]),"volumes_retained":True}
        return start_job(p,"uninstall",work)

    def updater_service(p):
        # Reuse the project's existing safe updater instead of inventing a replacement algorithm.
        import docker
        if p["kind"] not in {"local","tcp","ssh","balena","tunnel"}:
            abort(409,"This adapter cannot expose the Docker API. For WSL use a verified TLS profile or the host Container Updater / Compose.")
        if p['kind'] in {'ssh','balena'}:
            from remote_api import ssh_docker_client
            client=ssh_docker_client(p)
        elif p['kind']=='tunnel':
            client=docker.DockerClient(base_url=p['endpoint'],timeout=30)
        elif p["kind"]=="local":
            if p.get("context"):
                context=factory(p).json(["context","inspect",p["context"]])[0]
                client=docker.DockerClient(base_url=context["Endpoints"]["docker"]["Host"],timeout=30)
            else:
                client=docker.from_env(timeout=30)
        else:
            credentials=p.get("credentials",{})
            cert=(credentials["tls_cert"],credentials["tls_key"]) if credentials.get("tls_cert") and credentials.get("tls_key") else None
            client=docker.DockerClient(base_url=p["endpoint"],tls=docker.tls.TLSConfig(client_cert=cert,ca_cert=credentials.get("tls_ca"),verify=True),timeout=30)
        module_name="dcc_shared_update_service"
        if module_name not in sys.modules:
            spec=importlib.util.spec_from_file_location(module_name,ROOT/"apps/container-updater/updater.py")
            module=importlib.util.module_from_spec(spec)
            sys.modules[module_name]=module
            spec.loader.exec_module(module)
        return sys.modules[module_name].UpdateService(client,catalog_loader=catalogs.all),client

    @app.post("/api/updates/<target>/<action>")
    def updates(target,action):
        data=body()
        p=profile(data.get("profile"),"read" if action=="check" else "update")
        if action not in {"check","apply"}:
            abort(404)
        confirmed(data,"update."+action,p["id"],target)
        def work():
            service,client=updater_service(p)
            try:
                if action=="check":
                    return service.scan(container_ids=[target])
                container=client.containers.get(target)
                image=container.attrs.get("Config",{}).get("Image")
                if not image:
                    raise ValueError("Container image is unavailable")
                return service.update_one(container,image)
            finally:
                client.close()
        # Validate adapter compatibility synchronously, before queuing an operation.
        if p["kind"] not in {"local","tcp","ssh","balena","tunnel"}:
            abort(409,"Direct updates require local, TLS, verified SSH or an explicitly configured localhost tunnel. WSL can use a TLS profile or Compose.")
        return start_job(p,"update."+action,work)

    @app.post("/api/configuration/<target>")
    def configure_container(target):
        data=body()
        p=profile(data.get("profile"),"containers.write")
        authorize(p,"destructive")
        if p["kind"] not in {"local","tcp","ssh","balena","tunnel"}:
            abort(409,"Configuration recreation requires local, TLS, verified SSH or a localhost tunnel; WSL can use TLS or Compose.")
        overrides=data.get("changes",{})
        if not isinstance(overrides,dict) or set(overrides)-{"environment","command","user","working_dir","ports","restart"}:
            abort(400,"Unsupported configuration change")
        confirmed(data,"container.configure",p["id"],target)
        def work():
            service,client=updater_service(p)
            try:
                container=client.containers.get(target)
                config=container.attrs.get("Config",{})
                changes={key:value for key,value in overrides.items() if key not in {"environment","ports","restart"}}
                host_changes={}
                if 'ports' in overrides:
                    from ports import parse_bindings
                    host_changes['PortBindings']=parse_bindings(overrides['ports'])
                    changes['ports']=list(host_changes['PortBindings'])
                if 'restart' in overrides:
                    if overrides['restart'] not in {'no','always','unless-stopped','on-failure'}:raise ValueError('Invalid restart policy')
                    host_changes['RestartPolicy']={'Name':overrides['restart'],'MaximumRetryCount':0}
                if "environment" in overrides:
                    if not isinstance(overrides["environment"],dict):
                        raise ValueError("Environment changes must be an object")
                    env=dict(value.split("=",1) for value in config.get("Env",[]) if "=" in value)
                    env.update({str(key):str(value) for key,value in overrides["environment"].items()})
                    changes["environment"]=[key+"="+value for key,value in env.items()]
                return service.update_one(container,config["Image"],{"config":changes,"host_config":host_changes},_image_already_pulled=True,_expected_image_id=container.image.id)
            finally:
                client.close()
        return start_job(p,"container.configure",work)

    @app.get("/api/compose")
    def compose_projects():
        p=profile()
        projects=factory(p).json(["compose","ls","--all","--format","json"])
        names={v["Name"] for v in projects}
        projects += [{"Name":row["name"],"Status":"Przygotowany — jeszcze nie uruchomiony","ConfigFiles":row["file"]} for row in state.rows("SELECT * FROM compose_projects WHERE profile=?",(p["id"],)) if row["name"] not in names]
        return jsonify(projects=projects)

    @app.post("/api/compose/<project_name>/<action>")
    def compose_action(project_name,action):
        import posixpath
        data = body()
        p = profile(data.get("profile"),"read" if action in {"ps","config","logs"} else "destructive" if action=="down" else "compose.write")
        engine = factory(p)
        projects = engine.json(["compose","ls","--all","--format","json"])
        selected = next((v for v in projects if v.get("Name")==project_name),None)
        if not selected:
            saved=state.rows("SELECT * FROM compose_projects WHERE profile=? AND name=?",(p["id"],project_name))
            selected={"ConfigFiles":saved[0]["file"]} if saved else None
        if not selected or not selected.get("ConfigFiles"):
            abort(409,"Select an existing or prepared Compose project")
        files=selected["ConfigFiles"].split(",")
        filename = files[0]
        directory = str(Path(filename).parent) if re.match(r"^[A-Za-z]:",filename) else posixpath.dirname(filename)
        project={"name":project_name,"directory":directory,"file":filename,"files":files}
        if action not in {"ps","config","logs"}:
            confirmed(data,"compose."+action,p["id"],project_name)
            return start_job(p,"compose."+action,lambda:engine.compose(project,action))
        output=engine.compose(project,action)
        if action=="config":
            output=json.dumps(redact(json.loads(output)),ensure_ascii=False,indent=2)
        else:
            output=redact(output)
        return jsonify(output=output)

    @app.post("/api/compose/import")
    def compose_import():
        data = body()
        p = profile(data.get("profile"),"compose.write")
        if p["kind"] not in {"local","tcp"}:
            abort(409,"Upload Compose files on the Docker CLI host; remote profiles use existing projects")
        name, content = str(data.get("name","")),str(data.get("content",""))
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,60}",name) or not content or len(content)>500000:
            abort(400,"Invalid Compose name or content")
        confirmed(data,"compose.import",p["id"],name)
        directory = state.directory/"compose"/name
        directory.mkdir(parents=True,exist_ok=True)
        filename = directory/"compose.yaml"
        if filename.exists():
            abort(409,"This saved project already exists")
        filename.write_text(content,encoding="utf-8")
        try:
            preview = factory(p).compose({"name":name,"directory":str(directory),"file":str(filename)},"config")
        except Exception:
            filename.unlink()
            raise
        state.execute("INSERT INTO compose_projects VALUES(?,?,?,?)",(p["id"],name,str(filename),str(directory)))
        return jsonify(name=name,preview=redact(json.loads(preview)),file=str(filename),directory=str(directory))

    @app.route("/api/settings",methods=["GET","PUT"])
    def settings():
        rows = state.rows("SELECT data FROM settings WHERE user_id=?",(g.user["id"],))
        value = dict(DEFAULT_SETTINGS,**(json.loads(rows[0]["data"]) if rows else {}))
        value["refresh"]=max(15,min(900,int(value.get("refresh",15))))
        value["refresh_changes_only"]=bool(value.get("refresh_changes_only",False))
        if request.method=="PUT":
            incoming = body()
            if incoming.get('language',value['language']) not in {'PL','EN'}:
                abort(400,'Choose English or Polish')
            if incoming.get("theme",value["theme"]) not in THEMES or incoming.get("density","comfortable") not in {"comfortable","compact"}:
                abort(400,"Invalid appearance setting")
            if not re.fullmatch(r"#[0-9a-fA-F]{6}",incoming.get("accent",value["accent"])):
                abort(400,"Invalid accent color")
            for key in ("theme","accent","effects","density","animations","language"):
                if key in incoming:
                    value[key]=incoming[key]
            value["intensity"]=max(0,min(100,int(incoming.get("intensity",value["intensity"]))))
            value["refresh"]=max(15,min(900,int(incoming.get("refresh",value["refresh"]))))
            value["refresh_changes_only"]=bool(incoming.get("refresh_changes_only",value.get("refresh_changes_only",False)))
            value["terminal_limit"]=max(1,min(32,int(incoming.get("terminal_limit",value.get("terminal_limit",16)))))
            value["check_updates_on_refresh"]=bool(incoming.get("check_updates_on_refresh",value.get("check_updates_on_refresh",True)))
            audio = incoming.get("audio",value["audio"])
            value["audio"]={"enabled":bool(audio.get("enabled")),"style":audio.get("style","soft") if audio.get("style","soft") in {"soft","clear","warm"} else "soft",**{key:max(0,min(100,int(audio.get(key,50)))) for key in ("master","effects","notifications")}}
            state.execute("INSERT OR REPLACE INTO settings VALUES(?,?)",(g.user["id"],json.dumps(value)))
        response=jsonify(value)
        if request.method=='PUT':response.set_cookie('dcc_web_language',value['language'],max_age=31536000,samesite='Strict',secure=app.config.get('SESSION_COOKIE_SECURE',False) or trusted_https_request(app))
        return response

    @app.get("/api/audit")
    def audit():
        admin()
        return jsonify(events=state.rows("SELECT at,user_id,action,target,result FROM audit ORDER BY id DESC LIMIT 100"))

    @app.route("/api/users",methods=["GET","POST"])
    def users():
        admin()
        if request.method=="GET":
            return jsonify(users=state.rows("SELECT id,name,role FROM users"))
        data = body()
        if data.get("role") not in {"admin","operator","viewer"} or not re.fullmatch(r"[\w.@-]{3,64}",data.get("name","")) or not 12<=len(data.get("password",""))<=256:
            abort(400,"Invalid user name, role or password")
        state.execute("INSERT INTO users VALUES(?,?,?,?)",(secrets.token_hex(12),data["name"],generate_password_hash(data["password"]),data["role"]))
        return jsonify(ok=True),201

    @app.put("/api/password")
    def password():
        data = body()
        if not check_password_hash(g.user["password"],data.get("current","")) or not 12<=len(data.get("password",""))<=256:
            abort(400,"Current password or new password is invalid")
        state.execute("UPDATE users SET password=? WHERE id=?",(generate_password_hash(data["password"]),g.user["id"]))
        app.extensions['dcc_mcp_http'].oauth.revoke_user(g.user['id'])
        state.execute("DELETE FROM sessions WHERE user_id=?",(g.user["id"],))
        session.clear()
        return jsonify(ok=True)

    # MCP stdio uses explicit grants; HTTP/OAuth is a separate opt-in transport.
    from mcp_preview import register_mcp
    register_mcp(app,state,profile,reauthenticate,confirmed)
    from ai_assistant import register_ai
    register_ai(app,state,profile,factory,body)
    register_remote_access(app, state, body, profile, confirmed, reauthenticate, start_job, installed_scans.invalidate)
    from mcp_http import register_public_mcp
    register_public_mcp(app,state,reauthenticate,factory,terminal_factory)
    return app


def main():
    parser = argparse.ArgumentParser(description="DCC Web local workspace")
    parser.add_argument("--host",default="127.0.0.1")
    parser.add_argument("--port",type=int,default=8789)
    parser.add_argument("--allow-lan",action="store_true")
    parser.add_argument("--data",default=os.environ.get("DCC_WEB_DATA",str(Path.home()/".dcc-web")))
    parser.add_argument("--self-check",action="store_true")
    parser.add_argument("--mcp-stdio",action="store_true")
    parser.add_argument("--init-admin",action="store_true")
    args = parser.parse_args()
    if args.init_admin:
        import getpass
        state=State(args.data,os.environ.get("DCC_WEB_MASTER_KEY"))
        if state.rows("SELECT id FROM users LIMIT 1"):
            parser.error("Administrator initialization has already completed")
        username=input("Administrator name: ").strip()
        password=getpass.getpass("Password (at least 12 characters): ")
        if not re.fullmatch(r"[\w.@-]{3,64}",username) or not 12<=len(password)<=256:
            parser.error("Invalid administrator name or password")
        state.execute("INSERT INTO users VALUES(?,?,?,?)",(secrets.token_hex(12),username,generate_password_hash(password),"admin"))
        print("Administrator created. No password was written to configuration or logs.")
        return
    if args.self_check:
        validate_catalog(json.loads((ROOT/"dcc-catalog.json").read_text(encoding="utf-8")))
        print(json.dumps({"app":"DCC Web","version":VERSION,"catalog":"valid"}))
        return
    if args.mcp_stdio:
        from mcp_preview import stdio
        return stdio(State(args.data,os.environ.get("DCC_WEB_MASTER_KEY")))
    if args.host not in {"127.0.0.1","localhost","::1"} and not args.allow_lan:
        parser.error("LAN exposure requires --allow-lan and an HTTPS reverse proxy")
    allowed = {"127.0.0.1","localhost","::1",args.host,*os.environ.get("DCC_WEB_HOSTS","").split(",")}
    blocked_digests = frozenset(value.strip() for value in os.environ.get("DCC_REMOTE_BLOCKED_DIGESTS", "").split(","))
    app = create_app({"DATA_DIR":args.data,"ALLOWED_HOSTS":allowed,"DCC_REMOTE_BLOCKED_DIGESTS":blocked_digests})
    if args.allow_lan:
        credentials = provision_random_admin(app.extensions["dcc_state"])
        if credentials:
            username, password = credentials
            print(f"DCC_WEB_INITIAL_CREDENTIALS username={username} password={password}", flush=True)
    import threading
    def refresh_sources():
        while True:
            try:
                app.extensions["dcc_catalogs"].refresh()
            except Exception:
                pass
            time.sleep(3600)
    threading.Thread(target=refresh_sources,name="dcc-catalog-refresh",daemon=True).start()
    from waitress import create_server, serve
    if args.port != REMOTE_PORT and Path("/.dockerenv").is_file() and Path("/var/run/docker.sock").is_socket():
        remote = app.extensions["dcc_remote_access"]
        try:
            remote.repair_panel_network()
        except Exception as error:
            remote.network_error = "The isolated panel network could not be repaired. Remote Access remains unavailable until it is fixed."
            print(f"DCC Remote Access panel network repair failed ({type(error).__name__}); ingress remains unavailable.", flush=True)
        try:
            ingress = create_server(remote.as_ingress, map={}, host="0.0.0.0", port=REMOTE_PORT,
                                    threads=8, channel_timeout=60, ident="DCC-Web")
        except OSError:
            print("DCC Remote Access ingress could not start.", flush=True)
        else:
            remote.available = True
            threading.Thread(target=ingress.run, name="dcc-remote-ingress", daemon=True).start()
            try:
                from remote_maintenance import start_control
                start_control(remote)
            except OSError as error:
                print(f"DCC Remote Access update control unavailable ({type(error).__name__}).", flush=True)
            remote.start_recovery()
    print(f"DCC Web {VERSION}: http://{args.host}:{args.port} (initial setup at /login)",flush=True)
    serve(app,host=args.host,port=args.port,threads=8,channel_timeout=60,ident="DCC-Web")


if __name__=="__main__":
    main()
