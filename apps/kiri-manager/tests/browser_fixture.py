"""Serve the real panel and project website locally with an isolated synthetic connector."""
import os
import tempfile

from flask import request, send_from_directory
from waitress import create_server
from werkzeug.security import generate_password_hash

from backend.app import create_app
from backend.config import ROOT, Config
from backend.kiri_client import Connector
from backend.storage import Storage
from fixtures import FixtureTransport


def main():
    with tempfile.TemporaryDirectory(prefix="dcc-kiri-browser-") as root:
        # Discovery sorts aliases. Keep the fully available test engine before
        # the deliberately incomplete fixture used for failure scenarios.
        endpoints = {"test-engine": "kiri", "offline-test": "offline", "z-partial-test": "partial"}
        app = create_app(Config(root, endpoints), connector=Connector(endpoints, FixtureTransport), demo=True)
        storage = Storage(root)
        test_hash = generate_password_hash("TEST-only-kiri-passphrase")
        storage.set_password(test_hash)

        @app.post("/__fixture/reset")
        def reset():
            with storage.transaction() as connection:
                connection.execute("DELETE FROM sessions")
                connection.execute("DELETE FROM profiles")
                connection.execute("UPDATE preferences SET payload='{}', active=NULL")
                if request.args.get("blank") == "1":
                    connection.execute("DELETE FROM admin")
            if request.args.get("blank") != "1":
                storage.set_password(test_hash, username="admin", replace=True)
            return "", 204

        @app.get("/project/")
        @app.get("/project/<path:filename>")
        def project(filename="index.html"):
            if filename.endswith("/"):
                filename += "index.html"
            return send_from_directory(ROOT / "site", filename)

        server = create_server(app, host="127.0.0.1", port=0, clear_untrusted_proxy_headers=True)
        print(f"PORT={server.effective_port}", flush=True)
        try:
            server.run()
        finally:
            server.close()


if __name__ == "__main__":
    os.umask(0o077)
    main()
