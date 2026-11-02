"""Canonical catalog, optional sources, validated fetches and install previews."""
import hashlib
import http.client
import ipaddress
import json
from pathlib import Path
import re
import shlex
import socket
import ssl
import time
from urllib.parse import urlsplit, urljoin

from dcc_catalog import category_group, localized_categories, catalog_category_sort_key, image_repository, catalog_application_key
from ports import published_ports

OFFICIAL = "https://github.com/hattimon/DCC"


def validate_catalog(payload):
    apps = payload.get("apps") if isinstance(payload, dict) else payload
    if not isinstance(apps, list) or len(apps) > 5000:
        raise ValueError("Catalog must contain an apps array of at most 5000 entries")
    for app in apps:
        if not isinstance(app, dict) or not isinstance(app.get("name"), str) or not isinstance(app.get("image"), str) or not app["name"].strip() or not app["image"].strip():
            raise ValueError("Each catalog entry needs a name and Docker image")
        for key in ("categories", "categories_en"):
            if key in app and app[key] is not None and (not isinstance(app[key], list) or not all(isinstance(v, str) for v in app[key])):
                raise ValueError("Additional categories must be arrays of strings")
    return apps


def candidates(source):
    match = re.fullmatch(r"https://github\.com/([\w.-]+)/([\w.-]+?)(?:\.git)?/?", source)
    if match:
        owner, repo = match.groups()
        return [f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{name}" for branch in ("main", "master") for name in ("dcc-catalog.json", "catalog.json")]
    return [source]


def fetch_public(url, limit=2_000_000):
    """Pin a validated public DNS answer for each connection, including redirects."""
    for _ in range(4):
        parsed = urlsplit(url)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or any(ord(c)<32 for c in url):
            raise ValueError("Catalog URLs must use HTTPS without embedded credentials")
        port = parsed.port or 443
        addresses = socket.getaddrinfo(parsed.hostname, port, type=socket.SOCK_STREAM)
        if not addresses or any(not ipaddress.ip_address(address[4][0]).is_global for address in addresses):
            raise ValueError("Private, loopback and link-local catalog addresses are blocked; import a local JSON file instead")
        address = addresses[0][4][0]
        raw_socket = socket.create_connection((address, port), timeout=8)
        connection = http.client.HTTPSConnection(parsed.hostname, port, timeout=8)
        try:
            connection.sock = ssl.create_default_context().wrap_socket(raw_socket, server_hostname=parsed.hostname)
            connection.request("GET", (parsed.path or "/") + ("?"+parsed.query if parsed.query else ""), headers={"Host":parsed.netloc, "User-Agent":"DCC-Web/0.1", "Accept":"application/json"})
            response = connection.getresponse()
            if response.status in {301,302,303,307,308}:
                url = urljoin(url, response.getheader("Location", ""))
                continue
            if response.status != 200:
                raise ValueError("Catalog source did not return HTTP 200")
            data = response.read(limit+1)
            if len(data)>limit:
                raise ValueError("Catalog exceeds the size limit")
            return data
        finally:
            connection.close()
            raw_socket.close()
    raise ValueError("Too many catalog redirects")


def app_id(app):
    return hashlib.sha256((app["name"].lower()+"\0"+app["image"].lower()).encode()).hexdigest()[:20]


def image_repo(image):
    value = image.split("@",1)[0]
    prefix, separator, last = value.rpartition("/")
    return prefix+separator+last.split(":",1)[0]


class Catalogs:
    def __init__(self, state, root):
        self.state, self.root = state, Path(root)
        self.fallback = validate_catalog(json.loads((self.root / "dcc-catalog.json").read_text(encoding="utf-8")))
        state.execute("INSERT OR IGNORE INTO sources VALUES(?,?,?,?,?,?,?)", ("official", OFFICIAL, 1, 1, json.dumps(self.fallback), 0, ""))

    def sources(self):
        return [{key:row[key] for key in ("id","source","enabled","canonical","checked","error")} | {"count":len(json.loads(row["cache"] or "[]"))} for row in self.state.rows("SELECT * FROM sources ORDER BY canonical DESC, source")]

    def host_panel_ports(self):
        result={}
        for app in self.all():
            port=str(app.get('container_port',''))
            number,_,protocol=port.partition('/')
            if number.isdigit() and 1<=int(number)<=65535 and protocol in {'','tcp'}:
                result[image_repository(app['image'])]=int(number)
        return result

    def all(self):
        merged = {}
        for app in self.fallback:
            merged[catalog_application_key(app["name"], app["image"], app.get("default_name") or app.get("container_name"))] = dict(app)
        for row in self.state.rows("SELECT cache FROM sources WHERE enabled=1 ORDER BY canonical DESC, rowid"):
            for app in json.loads(row["cache"] or "[]"):
                key = catalog_application_key(app["name"], app["image"], app.get("default_name") or app.get("container_name"))
                old = merged.get(key, {})
                new = dict(old, **app)
                for field in ("categories","categories_en","store_description","store_description_en","features","features_en","icon_url","hero_image_url","gallery","build_context","build_dockerfile"):
                    if not new.get(field) and old.get(field):
                        new[field] = old[field]
                merged[key] = new
        return [dict(app, id=app_id(app)) for app in merged.values()]

    def add(self, source, contents=None):
        source = str(source).strip()
        if not source or len(source)>500:
            raise ValueError("A catalog source is required")
        source_id = hashlib.sha256(source.rstrip("/").encode()).hexdigest()[:16]
        if source.rstrip("/").removesuffix(".git").casefold() == OFFICIAL.casefold():
            raise ValueError("The official catalog already exists")
        if contents is not None:
            apps = validate_catalog(contents)
            source = "file:" + Path(source).name
        else:
            apps = self.download(source)
        self.state.execute("INSERT INTO sources VALUES(?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET source=excluded.source,enabled=1,cache=excluded.cache,checked=excluded.checked,error='' WHERE sources.canonical=0", (source_id, source, 1, 0, json.dumps(apps), time.time(), ""))
        return source_id

    def download(self, source):
        last = None
        for url in candidates(source):
            try:
                return validate_catalog(json.loads(fetch_public(url)))
            except (ValueError, OSError, http.client.HTTPException) as error:
                last = error
        raise ValueError("Catalog unavailable or invalid; existing cached data is retained") from last

    def refresh(self, source_id=None):
        for row in self.state.rows("SELECT * FROM sources WHERE enabled=1"):
            if source_id and row["id"] != source_id:
                continue
            if row["source"].startswith("file:"):
                continue
            try:
                apps = self.download(row["source"])
                self.state.execute("UPDATE sources SET cache=?,checked=?,error='' WHERE id=?", (json.dumps(apps), time.time(), row["id"]))
            except ValueError:
                self.state.execute("UPDATE sources SET error=? WHERE id=?", ("Source unavailable; using cached catalog", row["id"]))
        return self.sources()

    def view(self, lang="PL", containers=(), query="", category="all", engine_kind="docker"):
        apps = self.all()
        groups = set()
        result = []
        for app in apps:
            memberships = list(dict.fromkeys(category_group(value) for value in localized_categories(app.get("category", "Inne"), app.get("category_en", ""), app.get("categories"), app.get("categories_en"), lang)))
            if "balena" in (app.get("engines") or []) and "Balena OS" not in memberships:
                memberships.append("Balena OS")
            groups.update(memberships)
            description = app.get("description_en") if lang=="EN" and app.get("description_en") else app.get("description", "")
            image_repository = image_repo(app["image"])
            installed = any(c.get("Image")==app["image"] or (c.get("Names")==app.get("default_name") and image_repo(c.get("Image", ""))==image_repository) for c in containers)
            notes = app.get("notes_en") if lang=="EN" and app.get("notes_en") else app.get("notes", "")
            if query.casefold() not in (app["name"]+" "+app["image"]+" "+description+" "+notes).casefold():
                continue
            if category=="installed" and not installed or category not in {"all","installed"} and category not in memberships:
                continue
            if app.get("engines") and engine_kind not in app["engines"] and "any" not in app["engines"]:
                continue
            installed_ids = [c["ID"] for c in containers if c.get("Image")==app["image"] or (c.get("Names")==app.get("default_name") and image_repo(c.get("Image", ""))==image_repository)]
            result.append(dict(app, category_labels=memberships, installed=installed, installed_ids=installed_ids, localized_description=description))
        groups.discard("DCC")
        return {"apps":result, "categories":["all","installed","DCC",*sorted(groups,key=catalog_category_sort_key)]}


ALLOWED_FLAGS = {"-v","--volume","-p","--publish","-e","--env","--restart","--label","--cap-drop","--cap-add","--security-opt","--network","--user","--hostname","--workdir","--entrypoint","--device","--mount","--memory","--cpus","--gpus","--shm-size","--add-host","--pid","--tmpfs","--pids-limit"}
BOOLEAN_FLAGS = {"--read-only","--init","--privileged"}


def install_plan(app, config, engine):
    if app.get("build_context"):
        try:
            engine.json(["image","inspect",str(config.get("image") or app["image"])])
        except Exception as error:
            raise ValueError("This app needs a separately confirmed source build first. Source code is never executed automatically on the host.") from error
    info = engine.info()
    engine_kind = "balena" if getattr(engine,"profile",{}).get("kind")=="balena" else "docker"
    if app.get("engines") and engine_kind not in app["engines"] and "any" not in app["engines"]:
        raise ValueError("App does not support this Docker engine")
    aliases = {"x86_64":"amd64","aarch64":"arm64","armv7l":"armv7"}
    architecture = aliases.get(info.get("Architecture"), info.get("Architecture"))
    if app.get("archs") and architecture not in {aliases.get(v,v) for v in app["archs"]}:
        raise ValueError("Image does not support the selected host architecture")
    if app.get("ram_min_mb",0)*1024*1024 > info.get("MemTotal",float("inf")):
        raise ValueError("The host does not meet the minimum RAM requirement")
    name = str(config.get("name") or app.get("default_name") or "dcc-app")
    image = str(config.get("image") or app["image"])
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,100}",name) or not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_./:@-]{0,250}",image):
        raise ValueError("Invalid container name or image")
    extra = shlex.split(str(config.get("extra", app.get("extra")) or ""))
    args, warnings, index = ["run","--detach","--name",name], [], 0
    while index<len(extra):
        token = extra[index]
        flag, equal, value = token.partition("=")
        if flag in BOOLEAN_FLAGS:
            args.append(token)
        elif flag in ALLOWED_FLAGS:
            if equal:
                args.append(token)
            elif index+1<len(extra):
                args += [flag,extra[index+1]]
                index += 1
            else:
                raise ValueError("Incomplete catalog container option")
        else:
            raise ValueError("Unsupported catalog option; review the configuration manually")
        index += 1
    port = config.get("host_port", app.get("host_port"))
    extra_end=len(args)
    primary_publish_index=None
    container_port = str(config.get("container_port",app.get("container_port","")))
    if port and container_port:
        if not str(port).isdigit() or not 1<=int(port)<=65535 or not re.fullmatch(r"\d{1,5}(?:/(?:tcp|udp))?",container_port) or not 1<=int(container_port.split('/')[0])<=65535:
            raise ValueError("Invalid port mapping")
        primary_publish_index=len(args)+1
        args += ["--publish",f"{port}:{container_port}"]
    for key,value in (config.get("environment") or {}).items():
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*",key):
            raise ValueError("Invalid environment variable name")
        args += ["--env",key+"="+str(value)]
    published = []
    flags = set()
    for i,token in enumerate(args):
        flag,equal,inline=token.partition("=")
        flags.add(flag)
        if flag in {"--publish","-p"}:
            binding=inline if equal else args[i+1]
            mapping = binding.rsplit(":",2)
            protocol=mapping[-1].split("/",1)[1] if "/" in mapping[-1] else "tcp"
            if len(mapping)<2 or not mapping[-2].isdigit() or not 1<=int(mapping[-2])<=65535 or protocol not in {"tcp","udp"}:
                raise ValueError("Invalid published port option")
            published.append((mapping[0] if len(mapping)>2 else "",mapping[-2],protocol))
    if len(published)!=len(set(published)):
        raise ValueError("Duplicate published host port")
    current = engine.containers()
    if any(c.get("Names")==name for c in current):
        raise ValueError("Container name already exists")
    occupied={(p['host_port'],p['protocol']):c.get('Names','Docker') for c in current for p in published_ports(c.get('Ports'))}
    changes=[]
    for i,token in enumerate(list(args)):
        flag,equal,inline=token.partition('=')
        if flag not in {'-p','--publish'}:continue
        position=i if equal else i+1
        binding=inline if equal else args[position]
        parts=binding.rsplit(':',2)
        original=int(parts[-2]);candidate=original
        protocol=parts[-1].split('/',1)[1] if '/' in parts[-1] else 'tcp'
        if (candidate,protocol) in occupied:
            if config.get('auto_port') is not True:
                next_port=candidate
                while (next_port,protocol) in occupied and next_port<65535:next_port+=1
                raise ValueError(f'Port {original}/{protocol} is used by {occupied[(original,protocol)]}. Suggested free port: {next_port}. Enable automatic port selection or choose another port.')
            while (candidate,protocol) in occupied and candidate<65535:candidate+=1
            if (candidate,protocol) in occupied:raise ValueError('No free port in the selected range')
            parts[-2]=str(candidate)
            args[position]=(flag+'=' if equal else '')+':'.join(parts)
            changes.append({'from':original,'to':candidate,'protocol':protocol})
        occupied[(candidate,protocol)]=name
    if any("docker.sock" in token or "docker_engine" in token for token in args):
        warnings.append("docker-socket")
    if flags & {"--privileged","--cap-add","--device","--pid"} or any(token in {"host","seccomp=unconfined","apparmor=unconfined"} for token in args):
        warnings.append("privileged")
    if flags & {"-v","--volume","--mount"}:
        warnings.append("persistent-data")
    if app.get("requires"):
        warnings.append("dependencies")
    command = config.get("command", app.get("command", ""))
    args += [image,*(shlex.split(command) if isinstance(command,str) else command)]
    resolved=dict(config,name=name,image=image,extra=shlex.join(args[4:extra_end]),auto_port=False)
    if primary_publish_index is not None:resolved['host_port']=args[primary_publish_index].rsplit(':',2)[-2]
    return {"args":args,"name":name,"image":image,"warnings":warnings,"port_changes":changes,"resolved_configuration":resolved,"persistent_data":"Volumes and bind mounts are retained during uninstall"}
