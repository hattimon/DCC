"""Bounded SSH commands for explicitly authorized MCP host profiles.

Use the same strict host verification as the browser terminal. No local shell,
Docker socket shell, credential export or alternate connection is provided.
"""
import time

from engine import EngineError
from profile_ssh import configure_client, connection_options

MAX_OUTPUT = 131072


def host_profile(profile):
    if profile.get("kind") not in {"ssh", "balena"}:
        raise ValueError("MCP host access requires an SSH or Balena profile with host.exec permission")


class SSHCommand:
    def __init__(self, profile):
        import paramiko
        host_profile(profile)
        self.client = paramiko.SSHClient()
        try:
            configure_client(self.client, profile)
            self.client.connect(**connection_options(profile))
            self.channel = self.client.get_transport().open_session(timeout=12)
            self.channel.settimeout(12)
        except Exception:
            self.client.close()
            raise EngineError("Could not open the verified SSH connection. Check this profile in DCC Web.") from None

    def run(self, command, timeout, authorize):
        deadline = time.monotonic() + timeout
        stdout, stderr = bytearray(), bytearray()
        truncated = False
        authorize()
        self.channel.settimeout(min(timeout, 12))
        try:
            self.channel.exec_command(command)
        except TimeoutError:
            return self._result(stdout, stderr, None, True, False)
        while True:
            authorize()
            if time.monotonic() >= deadline:
                return self._result(stdout, stderr, None, True, truncated)
            for ready, receive, destination in (
                (self.channel.recv_ready, self.channel.recv, stdout),
                (self.channel.recv_stderr_ready, self.channel.recv_stderr, stderr),
            ):
                if ready():
                    chunk = receive(32768)
                    remaining = max(0, MAX_OUTPUT - len(stdout) - len(stderr))
                    destination.extend(chunk[:remaining])
                    truncated |= len(chunk) > remaining
            if self.channel.exit_status_ready() and not self.channel.recv_ready() and not self.channel.recv_stderr_ready():
                return self._result(stdout, stderr, self.channel.recv_exit_status(), False, truncated)
            time.sleep(.02)

    @staticmethod
    def _result(stdout, stderr, code, timed_out, truncated):
        return {"stdout": stdout.decode("utf-8", "replace"), "stderr": stderr.decode("utf-8", "replace"),
                "exit_code": code, "timed_out": timed_out, "truncated": truncated}

    def close(self):
        try:
            self.channel.close()
        finally:
            self.client.close()
