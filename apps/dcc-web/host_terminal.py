"""Owner/session/profile-scoped interactive PTYs. Output stays in bounded memory."""
import base64
import os
import secrets
import subprocess
import threading
import time

from engine import EngineError
from profile_ssh import configure_client, connection_options


class PTYConnection:
    def __init__(self, profile, cols=120, rows=32):
        self.kind=profile.get("kind","local")
        self.client=None
        if self.kind in {"ssh","balena"}:
            import paramiko
            client=paramiko.SSHClient()
            configure_client(client, profile)
            credentials=profile.get("credentials",{})
            try:
                client.connect(**connection_options(profile))
                self.channel=client.invoke_shell(term="xterm-256color",width=cols,height=rows)
                self.channel.settimeout(None)
                self.client=client
            except Exception:
                client.close()
                raise EngineError("Could not open the verified SSH terminal. Check profile credentials and known_hosts.") from None
        elif self.kind in {"local","wsl"}:
            if self.kind=="local" and os.environ.get("DCC_WEB_CONTAINER_NAME"):
                raise ValueError("A Docker socket does not expose a host shell. Use an SSH profile for the actual Docker host.")
            environment={key:value for key,value in os.environ.items() if not key.startswith(("_PYI","DCC_WEB_")) and key not in {"PYTHONPATH","PYTHONHOME","_MEIPASS2","GH_TOKEN","GITHUB_TOKEN","OPENAI_API_KEY"}}
            if os.name=="nt":
                from winpty import PtyProcess
                command=["wsl.exe","--distribution",profile["distro"],"--exec","/bin/bash","--noprofile","--norc","-i"] if self.kind=="wsl" else [os.path.join(os.environ.get("SystemRoot",r"C:\Windows"),"System32","WindowsPowerShell","v1.0","powershell.exe"),"-NoProfile","-NoLogo"]
                self.process=PtyProcess.spawn(subprocess.list2cmdline(command),dimensions=(rows,cols),env=environment,cwd=os.path.expanduser("~"))
            else:
                if self.kind=="wsl":raise ValueError("WSL terminal requires Windows")
                from ptyprocess import PtyProcessUnicode
                shell="/bin/bash" if os.path.exists("/bin/bash") else "/bin/sh"
                self.process=PtyProcessUnicode.spawn([shell,"-i"],dimensions=(rows,cols),env=environment,cwd=os.path.expanduser("~"))
        else:
            raise ValueError("This Docker API profile has no host shell. Select an SSH profile for this host.")

    def read(self):
        value=self.channel.recv(65536) if self.client else self.process.read(65536)
        return value.encode("utf-8") if isinstance(value,str) else value

    def write(self,value):
        if self.client:self.channel.sendall(value)
        else:self.process.write(value.decode("utf-8","replace"))

    def resize(self,cols,rows):
        if self.client:self.channel.resize_pty(width=cols,height=rows)
        else:self.process.setwinsize(rows,cols)

    def close(self):
        if self.client:
            self.channel.close()
            self.client.close()
        else:
            self.process.terminate(force=True)


class TerminalSession:
    def __init__(self, connection, owner, login, profile):
        self.id=secrets.token_urlsafe(24)
        self.owner,self.login,self.profile=owner,login,profile
        self.connection=connection
        self.condition=threading.Condition()
        self.buffer=bytearray()
        self.offset=0
        self.closed=False
        self.created=self.touched=time.monotonic()
        threading.Thread(target=self._reader,name="dcc-host-terminal-output",daemon=True).start()

    def _reader(self):
        try:
            while not self.closed:
                data=self.connection.read()
                if not data:break
                with self.condition:
                    self.buffer.extend(data)
                    excess=max(0,len(self.buffer)-1_000_000)
                    if excess:
                        del self.buffer[:excess]
                        self.offset+=excess
                    self.condition.notify_all()
        except Exception:
            pass
        finally:
            with self.condition:
                self.closed=True
                self.condition.notify_all()
            try:self.connection.close()
            except Exception:pass

    def output(self,offset,wait=1):
        self.touched=time.monotonic()
        with self.condition:
            if offset>self.offset+len(self.buffer):raise ValueError("Invalid terminal output offset")
            if offset==self.offset+len(self.buffer) and not self.closed:self.condition.wait(min(1,max(0,wait)))
            start=max(offset,self.offset)
            return {"data":base64.b64encode(bytes(self.buffer[start-self.offset:])).decode(),"offset":self.offset+len(self.buffer),"closed":self.closed,"truncated":offset<self.offset}

    def close(self):
        with self.condition:
            self.closed=True
            self.condition.notify_all()
        try:self.connection.close()
        except Exception:pass


class HostTerminals:
    def __init__(self,factory=None):
        self.factory=factory or PTYConnection
        self.sessions={}
        self.lock=threading.RLock()
        self.reaper=None

    def open(self,profile,owner,login,cols,rows,limit=16):
        with self.lock:
            self._expire()
            active=[value for value in self.sessions.values() if not value.closed]
            if len(active)>=64 or sum(v.owner==owner for v in active)>=max(1,min(32,limit)):
                raise ValueError(f"Terminal session limit ({limit}) reached. Close an unused session or change the limit in Settings.")
            connection=self.factory(profile,cols,rows)
            value=TerminalSession(connection,owner,login,profile["id"])
            self.sessions[value.id]=value
            if not self.reaper or not self.reaper.is_alive():
                self.reaper=threading.Thread(target=self._cleanup,name="dcc-terminal-expiry",daemon=True)
                self.reaper.start()
            return value

    def _expire(self):
        now=time.monotonic()
        for key,value in list(self.sessions.items()):
            if now-value.created>3600 or now-value.touched>600 or (value.closed and now-value.touched>30):
                value.close()
                self.sessions.pop(key,None)

    def _cleanup(self):
        while True:
            time.sleep(30)
            with self.lock:
                self._expire()
                if not self.sessions:return

    def get(self,terminal_id,owner,login):
        with self.lock:
            self._expire()
            value=self.sessions.get(terminal_id)
            if not value or value.owner!=owner or value.login!=login:raise KeyError("Terminal session is unavailable")
            return value

    def close(self,terminal_id,owner,login):
        with self.lock:
            value=self.get(terminal_id,owner,login)
            value.close()
            self.sessions.pop(terminal_id,None)

    def close_profiles(self, profile_ids):
        with self.lock:
            for ident, value in list(self.sessions.items()):
                if value.profile in profile_ids:
                    value.close()
                    self.sessions.pop(ident, None)
