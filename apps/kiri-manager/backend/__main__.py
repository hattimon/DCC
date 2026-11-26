"""Start the panel with a bounded Waitress server."""
import os
import signal

from waitress import create_server

from .app import create_app
from .config import Config


def serve(app, bind, port):
    server = create_server(
        app, host=bind, port=port, threads=5, connection_limit=64,
        channel_timeout=65, max_request_header_size=16 * 1024,
        max_request_body_size=65536, expose_tracebacks=False,
        clear_untrusted_proxy_headers=True, ident="dcc-kiri-manager",
    )

    def stop(signum, frame):
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, stop)
    try:
        server.run()
    finally:
        server.close()


def main():
    os.umask(0o077)
    config = Config.from_env(os.environ)
    serve(create_app(config), config.bind, config.port)


if __name__ == "__main__":
    main()
