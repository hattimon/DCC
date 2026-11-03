"""Opt-in verified email recovery. SMTP and email addresses are encrypted at rest."""
from email.message import EmailMessage
import hashlib
import hmac
import json
import re
import secrets
import smtplib
import ssl
import time

from flask import abort, g, jsonify, render_template, request, session
from werkzeug.security import check_password_hash

from security import admin

SMTP_ID = '__dcc_smtp__'


def email_address(value):
    if not isinstance(value,str) or len(value)>254 or not re.fullmatch(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?\.[A-Za-z]{2,63}",value):
        raise ValueError('Provide a valid email address')
    return value


class Recovery:
    def __init__(self,state):
        self.state = state
        state.execute('CREATE TABLE IF NOT EXISTS recovery_addresses(user_id TEXT PRIMARY KEY, email BLOB NOT NULL)')
        state.execute('CREATE TABLE IF NOT EXISTS email_tokens(user_id TEXT,purpose TEXT,token TEXT,expires REAL,email BLOB,binding TEXT,attempts INTEGER,PRIMARY KEY(user_id,purpose))')

    def smtp(self):
        rows = self.state.rows('SELECT data FROM settings WHERE user_id=?',(SMTP_ID,))
        return self.state.decode_profile(rows[0]['data']) if rows else {}

    def smtp_values(self,data):
        host = str(data.get('host','')).strip()
        if not re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9.-]{0,251}[A-Za-z0-9])?',host):
            raise ValueError('Invalid SMTP hostname')
        port = int(data.get('port') or 587)
        if not 1<=port<=65535:
            raise ValueError('Invalid SMTP port')
        old = self.smtp()
        username = str(data.get('username',''))
        password = data.get('password') or old.get('password','')
        if len(username)>254 or not isinstance(password,str) or len(password)>4096 or '\r' in username or '\n' in username:
            raise ValueError('Invalid SMTP credentials')
        return dict(host=host,port=port,username=username,password=password,sender=email_address(data.get('sender')),implicit_tls=bool(data.get('implicit_tls',port==465)))

    def configure_smtp(self,data):
        value = self.smtp_values(data)
        self.state.execute('INSERT OR REPLACE INTO settings VALUES(?,?)',(SMTP_ID,self.state.encode_profile(value)))

    def test_smtp(self,data,recipient):
        config=self.smtp_values(data)
        message=EmailMessage()
        message['Subject']='DCC Web — SMTP configuration test'
        message['From'],message['To']=config['sender'],email_address(recipient)
        message.set_content('This is a test message from DCC Web. SMTP TLS and sender configuration are working.')
        try:
            context=ssl.create_default_context()
            if config['implicit_tls']:
                client=smtplib.SMTP_SSL(config['host'],config['port'],timeout=10,context=context)
            else:
                client=smtplib.SMTP(config['host'],config['port'],timeout=10)
                client.ehlo();client.starttls(context=context);client.ehlo()
            with client:
                if config['username']:
                    client.login(config['username'],config['password'])
                client.send_message(message)
        except (OSError,smtplib.SMTPException):
            raise ValueError('SMTP test failed. Check TLS, credentials, sender and recipient configuration.') from None

    def address(self,user):
        rows = self.state.rows('SELECT email FROM recovery_addresses WHERE user_id=?',(user,))
        return self.state.vault.decrypt(rows[0]['email']).decode() if rows else ''

    def throttle(self,key):
        key = 'email:' + hashlib.sha256(str(key).encode()).hexdigest()
        with self.state.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            count = db.execute('SELECT COUNT(*) FROM attempts WHERE address=? AND at>?',(key,time.time()-600)).fetchone()[0]
            if count>=5:
                abort(429,'Too many attempts. Try again in ten minutes.')
            db.execute('INSERT INTO attempts VALUES(?,?)',(key,time.time()))

    def send(self,user,purpose,email,binding):
        config = self.smtp()
        if not config:
            raise ValueError('Configure TLS SMTP before using email recovery')
        token = secrets.token_hex(12).upper()
        hashed = hashlib.sha256((user+'\0'+purpose+'\0'+token).encode()).hexdigest()
        self.state.execute('INSERT OR REPLACE INTO email_tokens VALUES(?,?,?,?,?,?,0)',
                           (user,purpose,hashed,time.time()+600,self.state.vault.encrypt(email.encode()),hashlib.sha256(binding.encode()).hexdigest()))
        message = EmailMessage()
        message['Subject'] = 'DCC Web — verification code'
        message['From'], message['To'] = config['sender'], email_address(email)
        message.set_content('DCC Web\n\n'+('Confirm recovery email' if purpose=='verify' else 'Reset login 2FA')+'\n\nCode: '+token+'\n\nExpires in 10 minutes. If you did not request this code, ignore this message. Never share it with another person.')
        try:
            context = ssl.create_default_context()
            if config['implicit_tls']:
                client = smtplib.SMTP_SSL(config['host'],config['port'],timeout=10,context=context)
            else:
                client = smtplib.SMTP(config['host'],config['port'],timeout=10)
                client.ehlo(); client.starttls(context=context); client.ehlo()
            with client:
                if config['username']:
                    client.login(config['username'],config['password'])
                client.send_message(message)
        except (OSError,smtplib.SMTPException):
            self.state.execute('DELETE FROM email_tokens WHERE user_id=? AND purpose=?',(user,purpose))
            raise ValueError('SMTP delivery failed. Check TLS, credentials and sender configuration.') from None

    def consume(self,user,purpose,token,binding):
        if not isinstance(token,str) or len(token)>64:
            return None
        code = token.replace(' ','').replace('-','').upper()
        digest = hashlib.sha256((user+'\0'+purpose+'\0'+code).encode()).hexdigest()
        with self.state.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM email_tokens WHERE user_id=? AND purpose=?',(user,purpose)).fetchone()
            if not row or row['expires']<time.time() or row['attempts']>=5 or not hmac.compare_digest(row['binding'],hashlib.sha256(binding.encode()).hexdigest()):
                return None
            db.execute('UPDATE email_tokens SET attempts=attempts+1 WHERE user_id=? AND purpose=?',(user,purpose))
            if not hmac.compare_digest(row['token'],digest):
                return None
            db.execute('DELETE FROM email_tokens WHERE user_id=? AND purpose=?',(user,purpose))
            return self.state.vault.decrypt(row['email']).decode()


def register_recovery(app,state,reauthenticate):
    recovery = state.recovery

    @app.route('/api/admin/smtp',methods=['GET','PUT'])
    def smtp_configuration():
        admin()
        if request.method=='PUT':
            data = request.get_json() or {}
            reauthenticate(data)
            recovery.configure_smtp(data)
        config = recovery.smtp()
        public_config = {key:config.get(key) for key in ('host','port','username','sender','implicit_tls')}
        public_config.update(configured=bool(config),password_set=bool(config.get('password')))
        return jsonify(public_config)

    @app.post('/api/admin/smtp/test')
    def smtp_test():
        admin()
        data=request.get_json() or {}
        reauthenticate(data)
        recovery.throttle(g.user['id']+':smtp-test')
        recovery.test_smtp(data,data.get('test_recipient'))
        return jsonify(ok=True)

    @app.get('/api/account/recovery-email')
    def email_status():
        return jsonify(email=recovery.address(g.user['id']),smtp_configured=bool(recovery.smtp()))

    @app.post('/api/account/recovery-email/request')
    def email_request():
        data = request.get_json() or {}
        reauthenticate(data)
        recovery.throttle(g.user['id']+':verify')
        recovery.send(g.user['id'],'verify',email_address(data.get('email')),session['sid'])
        return jsonify(ok=True)

    @app.post('/api/account/recovery-email/verify')
    def email_verify():
        email = recovery.consume(g.user['id'],'verify',(request.get_json() or {}).get('code'),session['sid'])
        if email is None:
            abort(403,'Invalid or expired email code')
        state.execute('INSERT OR REPLACE INTO recovery_addresses VALUES(?,?)',(g.user['id'],state.vault.encrypt(email.encode())))
        return jsonify(ok=True)

    @app.route('/recover-2fa',methods=['GET','POST'])
    def recover_2fa():
        stage, error, complete = 'request', '', False
        if request.method=='POST':
            recovery.throttle(str(request.remote_addr)+':reset')
            if request.form.get('stage')=='confirm':
                user = session.get('recovery_user')
                if not user or session.get('recovery_until',0)<time.time():
                    error = 'Recovery request expired. Start again.'
                else:
                    email = recovery.consume(user,'reset',request.form.get('code'),session.get('recovery_nonce',''))
                    if email and hmac.compare_digest(email,recovery.address(user)):
                        state.execute('DELETE FROM mfa WHERE user_id=?',(user,))
                        state.execute('DELETE FROM sessions WHERE user_id=?',(user,))
                        session.clear(); complete=True
                    else:
                        stage, error = 'confirm', 'Invalid or expired email code'
            else:
                for key in ('recovery_user','recovery_nonce','recovery_until'):
                    session.pop(key,None)
                name, password = request.form.get('username',''),request.form.get('password','')
                if len(name)>64 or len(password)>256:
                    abort(400,'Invalid credential length')
                users = state.rows('SELECT * FROM users WHERE name=?',(name,))
                # Identical response for unknown users and unconfigured recovery.
                stage = 'confirm'
                if users and check_password_hash(users[0]['password'],password) and state.mfa.enabled(users[0]['id']):
                    user = users[0]['id']; email = recovery.address(user)
                    if email and recovery.smtp():
                        nonce = secrets.token_urlsafe(32)
                        recovery.send(user,'reset',email,nonce)
                        session['recovery_user'],session['recovery_nonce'],session['recovery_until']=user,nonce,time.time()+600
        return render_template('recovery.html',stage=stage,error=error,complete=complete)
