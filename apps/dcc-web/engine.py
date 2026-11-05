"""Argument-based Docker transports. No shell is used on the web host."""
import json
import os
import re
import socket
import shlex
import subprocess
import threading
import time

import paramiko
from paramiko.ssh_exception import NoValidConnectionsError
from profile_ssh import configure_client, connection_options
from ports import container_revision


class EngineError(RuntimeError):
    pass


def _ssh_error_message(error, stage):
    """Translate common SSH failures into safe guidance without exposing secrets."""
    if isinstance(error, paramiko.BadHostKeyException):
        return "SSH host key verification failed. Verify the host fingerprint and trusted known_hosts file in Profiles."
    if isinstance(error, paramiko.AuthenticationException):
        return "SSH authentication failed. Check the username, password, private key or key passphrase in Profiles."
    if isinstance(error, socket.gaierror):
        return "The SSH host name could not be resolved. Check the profile host name and DNS from the DCC Web server."
    if isinstance(error, ConnectionRefusedError):
        return "The SSH connection was refused. Check that SSH is running on the target and that the profile port is correct."
    if isinstance(error, (socket.timeout, TimeoutError)):
        return "The SSH connection timed out. Check the host, port, firewall and network route from the DCC Web server."
    if isinstance(error, NoValidConnectionsError):
        causes = tuple(getattr(error, "errors", {}).values())
        if any(isinstance(value, ConnectionRefusedError) for value in causes):
            return "The SSH connection was refused. Check that SSH is running on the target and that the profile port is correct."
        if any(isinstance(value, socket.gaierror) for value in causes):
            return "The SSH host name could not be resolved. Check the profile host name and DNS from the DCC Web server."
        if any(isinstance(value, (socket.timeout, TimeoutError)) for value in causes):
            return "The SSH connection timed out. Check the host, port, firewall and network route from the DCC Web server."
        return "The SSH host is unreachable from the DCC Web server. Check the host, port, firewall and network route."
    if isinstance(error, (paramiko.SSHException, EOFError)):
        if stage == "files":
            return "An SSH key or trusted-host file could not be read. Check the files and permissions in Profiles."
        if stage == "command":
            return "SSH connected, but the remote Docker command failed to start. Check remote shell access and Docker or Balena CLI availability."
        return "The SSH handshake failed. Check the authentication settings and trusted known_hosts file in Profiles."
    if isinstance(error, OSError):
        if stage == "files":
            return "An SSH key or trusted-host file could not be read. Check that the file exists and is accessible to DCC Web."
        if stage == "command":
            return "The SSH connection ended while running the remote Docker command. Check the remote host and its Docker service."
        return "The SSH connection failed. Check the host, port, firewall and network route from the DCC Web server."
    return "The SSH connection failed. Check the selected profile and its authentication settings."


def _connect_ssh(client, profile):
    try:
        configure_client(client, profile)
        options = connection_options(profile)
    except (paramiko.SSHException, OSError, EOFError) as error:
        raise EngineError(_ssh_error_message(error, "files")) from error
    try:
        client.connect(**options)
    except (paramiko.SSHException, OSError, EOFError) as error:
        raise EngineError(_ssh_error_message(error, "connect")) from error


class DockerBackend:
    def __init__(self, profile, compose_root=None):
        self.profile = profile
        self.compose_root = compose_root

    def _local_command(self):
        profile,credentials=self.profile,self.profile.get('credentials',{})
        kind=profile.get('kind','local')
        command = ["docker"]
        if kind == "wsl":
            if os.name != "nt":
                raise EngineError("WSL profiles require a Windows host; use an SSH or TLS profile from Linux")
            command = ["wsl.exe", "--distribution", profile["distro"], "--exec", "docker"]
        elif kind == "tcp":
            command += ["--host", profile["endpoint"].replace('https://','tcp://',1), "--tlsverify"]
            for key, flag in (("tls_ca", "--tlscacert"), ("tls_cert", "--tlscert"), ("tls_key", "--tlskey")):
                if credentials.get(key):
                    command += [flag, credentials[key]]
        elif kind == "tunnel":
            command += ["--host",profile["endpoint"]]
        elif profile.get("context"):
            command += ["--context", profile["context"]]
        environment = {key:value for key,value in os.environ.items() if not key.startswith("_PYI") and key not in {"PYTHONPATH", "PYTHONHOME", "_MEIPASS2"}}
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        return command,environment,flags

    def run(self, args, timeout=45, input_data=None):
        if not isinstance(args, list) or not all(isinstance(arg, str) and "\0" not in arg for arg in args):
            raise ValueError("Invalid Docker arguments")
        profile, credentials = self.profile, self.profile.get("credentials", {})
        kind = profile.get("kind", "local")
        if kind in {"ssh", "balena"}:
            client = paramiko.SSHClient()
            try:
                _connect_ssh(client, profile)
                cli = profile.get('cli') or ("balena" if kind == "balena" else "docker")
                try:
                    stdin, stdout, stderr = client.exec_command(shlex.join([cli, *args]), timeout=timeout)
                    if input_data is not None:
                        stdin.write(input_data)
                        stdin.flush()
                    stdin.channel.shutdown_write()
                    output, error = stdout.read(4_000_001), stderr.read(8192)
                    code = stdout.channel.recv_exit_status()
                except (paramiko.SSHException, OSError, EOFError) as error:
                    raise EngineError(_ssh_error_message(error, "command")) from error
            finally:
                client.close()
        else:
            command,environment,flags=self._local_command()
            try:
                result = subprocess.run([*command, *args], input=input_data, capture_output=True, timeout=timeout, encoding="utf-8", errors="replace", env=environment, creationflags=flags)
            except (OSError, subprocess.TimeoutExpired) as error:
                raise EngineError("Docker is unavailable or the operation timed out. Check the selected profile.") from error
            output, error, code = result.stdout, result.stderr, result.returncode
        if isinstance(output, bytes):
            output = output.decode("utf-8", "replace")
            error = error.decode("utf-8", "replace")
        if code:
            # Do not reflect a command line, credentials or environment into logs/API errors.
            if "conflict" in error.lower() or "already in use" in error.lower():
                raise EngineError("A name, port or resource conflict prevented the operation")
            if "permission" in error.lower():
                raise EngineError("Docker access denied; check this profile's host permissions")
            raise EngineError("Docker rejected the operation. Check the profile and resource state.")
        if args and (args[0]=="logs" or args[0]=="compose" and "logs" in args):
            output += error
        if len(output) > 4_000_000:
            raise EngineError("Docker response is too large; reduce the requested range")
        return output


    def stream(self,args,on_output,timeout=900):
        """Stream Docker progress with bounded memory and the same verified transports."""
        if not isinstance(args,list) or not all(isinstance(v,str) and "\0" not in v for v in args):
            raise ValueError("Invalid Docker arguments")
        if self.profile.get("kind") in {"ssh","balena"}:
            profile=self.profile
            client=paramiko.SSHClient()
            try:
                _connect_ssh(client, profile)
                try:
                    channel=client.get_transport().open_session(timeout=12);channel.set_combine_stderr(True)
                    channel.exec_command(shlex.join([profile.get('cli') or ('balena' if profile['kind']=='balena' else 'docker'),*args]));channel.shutdown_write()
                    import codecs
                    decoder=codecs.getincrementaldecoder('utf-8')('replace')
                    deadline=time.monotonic()+timeout
                    while True:
                        if channel.recv_ready():on_output(decoder.decode(channel.recv(8192)))
                        elif channel.exit_status_ready():break
                        elif time.monotonic()>deadline:raise EngineError("Docker operation timed out")
                        else:time.sleep(.05)
                    remainder=decoder.decode(b'',final=True)
                    if remainder:on_output(remainder)
                    if channel.recv_exit_status():raise EngineError("Docker rejected the operation. Review the installation log.")
                except (paramiko.SSHException, OSError, EOFError) as error:
                    raise EngineError(_ssh_error_message(error, "command")) from error
            finally:client.close()
            return
        command,environment,flags=self._local_command()
        expired=threading.Event()
        try:
            process=subprocess.Popen([*command,*args],stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace',env=environment,creationflags=flags,bufsize=1)
        except OSError as error:raise EngineError("Docker is unavailable. Check the selected profile.") from error
        def timeout_process():
            expired.set()
            if process.poll() is None:process.kill()
        timer=threading.Timer(timeout,timeout_process);timer.daemon=True;timer.start()
        try:
            while True:
                chunk=process.stdout.readline(8192)
                if not chunk:break
                on_output(chunk)
            code=process.wait()
            if expired.is_set():raise EngineError("Docker operation timed out")
            if code:raise EngineError("Docker rejected the operation. Review the installation log.")
        finally:
            timer.cancel()
            if process.poll() is None:process.kill()
            process.stdout.close()
            process.wait(timeout=5)

    def json(self, args, **kwargs):
        text = self.run(args, **kwargs).strip()
        if not text:
            return []
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return [json.loads(line) for line in text.splitlines() if line.strip()]

    def info(self):
        return self.json(["info", "--format", "{{json .}}"])

    def _container_list(self):
        data = self.json(["ps", "--all", "--no-trunc", "--format", "{{json .}}"])
        values=data if isinstance(data,list) else [data]
        for entry in values:
            if not entry.get('State') or entry.get('State')=='unknown':
                text=str(entry.get('Status','')).lower()
                entry['State']='paused' if 'paused' in text else 'running' if text.startswith('up ') else 'exited' if text.startswith('exited') else 'restarting' if text.startswith('restarting') else 'created' if text.startswith('created') else 'dead' if text.startswith('dead') else 'unknown'
        return values

    def containers(self):
        values = self._container_list()
        if values:
            # One bounded inspect request per batch; never return environment/secrets.
            policies = {}
            for start in range(0, len(values), 100):
                try:
                    items = self.json(['inspect', '--format', '{"ID":{{json .Id}},"RestartPolicy":{{json .HostConfig.RestartPolicy.Name}}}',
                                       *[v['ID'] for v in values[start:start+100]]])
                except (EngineError, ValueError, KeyError):
                    continue
                for item in items if isinstance(items, list) else [items]:
                    if isinstance(item, dict):
                        policies[item.get('ID')] = item.get('RestartPolicy')
            for entry in values:
                entry['RestartPolicy'] = policies.get(entry.get('ID'))
        return values

    def container_revision(self):
        return container_revision(self._container_list())

    def inspect(self, target):
        return self.json(["inspect", target])[0]

    def logs(self, target, tail=200, since=None):
        args = ["logs", "--timestamps", "--tail", str(max(1, min(int(tail), 2000)))]
        if since:
            args += ["--since", since]
        return self.run([*args, target])

    def stats(self):
        data = self.json(["stats", "--no-stream", "--no-trunc", "--format", "{{json .}}"])
        return data if isinstance(data, list) else [data]

    def resources(self, kind):
        commands = {"images": ["image", "ls", "--no-trunc"], "volumes": ["volume", "ls"], "networks": ["network", "ls"]}
        data = self.json([*commands[kind], "--format", "{{json .}}"])
        return data if isinstance(data, list) else [data]

    def action(self, target, action):
        actions = {"start": ["start"], "stop": ["stop", "--time", "10"], "restart": ["restart", "--time", "10"], "pause": ["pause"], "unpause": ["unpause"], "remove": ["rm"], "autostart-on": ["update", "--restart", "unless-stopped"], "autostart-off": ["update", "--restart", "no"]}
        if action not in actions:
            raise ValueError("Unsupported container operation")
        return self.run([*actions[action], target])

    def compose(self, project, action="ps"):
        if action not in {"ps", "config", "up", "stop", "restart", "pull", "logs", "down"}:
            raise ValueError("Unsupported Compose operation")
        suffix = {"ps": ["ps", "--all", "--format", "json"], "config": ["config", "--format", "json"], "up": ["up", "-d"], "logs": ["logs", "--tail", "200", "--no-color"], "down": ["down"], "stop": ["stop"], "restart": ["restart"], "pull": ["pull"]}[action]
        args=["compose", "--project-directory", project["directory"]]
        for filename in project.get("files",[project["file"]]):
            args += ["--file",filename]
        return self.run([*args,"--project-name",project["name"],*suffix],timeout=300)


class Jobs:
    """One mutation per Docker profile; bounded completion history."""
    def __init__(self):
        self.lock = threading.Lock()
        self.history = {}
        self.active = set()

    def execute(self,profile,work):
        """Synchronous lifecycle/exec operations share the same per-profile write guard."""
        with self.lock:
            if profile in self.active:
                raise ValueError('Another operation is already running for this profile')
            if len(self.active)>=4:
                raise ValueError('The operation queue is full')
            self.active.add(profile)
        try:return work()
        finally:
            with self.lock:self.active.discard(profile)

    def start(self, owner, profile, action, work, progress=False):
        import secrets
        with self.lock:
            if profile in self.active:
                raise ValueError("Another operation is already running for this profile")
            if len(self.active) >= 4:
                raise ValueError("The operation queue is full")
            job_id = secrets.token_hex(12)
            self.active.add(profile)
            self.history[job_id] = {"id":job_id, "owner":owner, "profile":profile, "action":action, "status":"running", "started":time.time()}
        def report(**updates):
            with self.lock:
                value=self.history[job_id]
                text=updates.pop('log',None)
                if text:value['logs']=(value.get('logs','')+str(text))[-200_000:]
                value.update(updates)
        def run():
            try:
                result = work(report) if progress else work()
                self.history[job_id].update(status="success", result=result)
                if progress:self.history[job_id]['phase']='completed'
            except Exception as error:
                from security import redact
                message=redact(str(error)) if isinstance(error,(EngineError,ValueError)) else "Operation failed; review the selected profile, configuration and Docker state"
                self.history[job_id].update(status="error", error=message)
                if progress:self.history[job_id]['phase']='failed'
            finally:
                with self.lock:
                    self.active.discard(profile)
                    self.history[job_id]["finished"] = time.time()
                    completed = [key for key,value in self.history.items() if value["status"] != "running"]
                    for key in completed[:-50]:
                        self.history.pop(key, None)
        threading.Thread(target=run, name="dcc-web-operation", daemon=True).start()
        return {"id":job_id,"profile":profile,"action":action,"status":"running"}
