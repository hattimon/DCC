"""Local Docker exec control for a single DCC Web update handoff."""
import json
import os
import socket
import socketserver
import stat
import sys
import threading
from pathlib import Path

DIRECTORY = Path("/tmp/dcc-remote-maintenance")
SOCKET = DIRECTORY / "control.sock"
LIMIT = 1024


def start_control(remote):
    DIRECTORY.mkdir(mode=0o700, exist_ok=True)
    info = DIRECTORY.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o700:
        raise OSError("Unsafe Remote Access control directory")
    if SOCKET.is_socket():
        SOCKET.unlink()

    class Handler(socketserver.StreamRequestHandler):
        timeout = 2

        def handle(self):
            try:
                raw = self.rfile.readline(LIMIT)
                args = json.loads(raw) if raw.endswith(b"\n") else None
                ok = isinstance(args, list) and all(isinstance(arg, str) for arg in args) and remote.maintenance(args)
            except Exception:
                ok = False
            try:
                self.wfile.write(b"ok\n" if ok else b"unavailable\n")
            except OSError:
                pass

    server = socketserver.UnixStreamServer(str(SOCKET), Handler)
    threading.Thread(target=server.serve_forever, name="dcc-remote-maintenance", daemon=True).start()


def main(args):
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(25 if args[:1] == ["pause"] else 5)
            client.connect(str(SOCKET))
            client.sendall(json.dumps(args).encode() + b"\n")
            with client.makefile("rb") as reply:
                return 0 if reply.readline(LIMIT) == b"ok\n" else 1
    except OSError:
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
