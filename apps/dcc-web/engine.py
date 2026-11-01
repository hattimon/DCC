"""Argument-based Docker transports. No shell is used on the web host."""
import json
import os
import re
import shlex
import subprocess
import threading
import time

import paramiko


class EngineError(RuntimeError):
    pass


class DockerBackend:
    def __init__(self, profile, compose_root=None):
        self.profile = profile
        self.compose_root = compose_root

    def run(self, args, timeout=45, input_data=None):
        if not isinstance(args, list) or not all(isinstance(arg, str) and "\0" not in arg for arg in args):
            raise ValueError("Invalid Docker arguments")
        profile, credentials = self.profile, self.profile.get("credentials", {})
        kind = profile.get("kind", "local")
        if kind in {"ssh", "balena"}:
            client = paramiko.SSHClient()
            client.load_system_host_keys()
            client.set_missing_host_key_policy(paramiko.RejectPolicy())
            try:
                client.connect(profile["host"], port=profile.get("port", 22), username=profile["username"], password=credentials.get("password") or None, passphrase=credentials.get("passphrase") or None, key_filename=profile.get("key_path") or None, timeout=12, auth_timeout=12, banner_timeout=12)
                cli = profile.get('cli') or ("balena" if kind == "balena" else "docker")
                stdin, stdout, stderr = client.exec_command(shlex.join([cli, *args]), timeout=timeout)
                if input_data is not None:
                    stdin.write(input_data)
                    stdin.flush()
                stdin.channel.shutdown_write()
                output, error = stdout.read(4_000_001), stderr.read(8192)
                code = stdout.channel.recv_exit_status()
            finally:
                client.close()
        else:
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

    def containers(self):
        data = self.json(["ps", "--all", "--no-trunc", "--format", "{{json .}}"])
        return data if isinstance(data, list) else [data]

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

    def start(self, owner, profile, action, work):
        import secrets
        with self.lock:
            if profile in self.active:
                raise ValueError("Another operation is already running for this profile")
            if len(self.active) >= 4:
                raise ValueError("The operation queue is full")
            job_id = secrets.token_hex(12)
            self.active.add(profile)
            self.history[job_id] = {"id":job_id, "owner":owner, "profile":profile, "action":action, "status":"running", "started":time.time()}
        def run():
            try:
                result = work()
                self.history[job_id].update(status="success", result=result)
            except Exception:
                self.history[job_id].update(status="error", error="Operation failed; review the selected profile, configuration and Docker state")
            finally:
                with self.lock:
                    self.active.discard(profile)
                    self.history[job_id]["finished"] = time.time()
                    completed = [key for key,value in self.history.items() if value["status"] != "running"]
                    for key in completed[:-50]:
                        self.history.pop(key, None)
        threading.Thread(target=run, name="dcc-web-operation", daemon=True).start()
        return {key:value for key,value in self.history[job_id].items() if key != "owner"}
