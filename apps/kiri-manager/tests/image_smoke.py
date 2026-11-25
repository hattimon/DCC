"""Exercise the installed server within an isolated Linux build container."""
import json
import os
import subprocess
import sys
import tempfile
import time
from http.cookiejar import CookieJar
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import HTTPCookieProcessor, Request, build_opener

from backend.config import VERSION

PASSWORD = "isolated-runtime-test-only"
origin = "http://127.0.0.1:18796"


class PanelHTTP:
    def __init__(self, url):
        self.url = url
        self.csrf = None
        self.opener = build_opener(HTTPCookieProcessor(CookieJar()))

    def get(self, route):
        return self.request(route)

    def request(self, route, data=None, method=None):
        headers = {"Accept": "application/json"}
        body = None
        if data is not None:
            body = json.dumps(data).encode()
            headers.update({"Content-Type": "application/json", "Origin": self.url})
            if self.csrf:
                headers["X-CSRF-Token"] = self.csrf
        request = Request(self.url + route, data=body, headers=headers, method=method)
        with self.opener.open(request, timeout=20) as answer:
            return json.load(answer)

    def login(self):
        self.csrf = self.get("/api/session")["csrf"]
        response = self.request("/api/login", {"username": "admin", "password": PASSWORD})
        assert response["authenticated"]
        self.csrf = response["csrf"]
        return response


def wait_ready(client, seconds=15):
    until = time.monotonic() + seconds
    while time.monotonic() < until:
        try:
            if client.get("/healthz") == {"status": "ok"}:
                return
        except (URLError, TimeoutError, OSError):
            pass
        time.sleep(.15)
    raise AssertionError("Panel health check failed")


def smoke():
    assert os.getuid() == 10001
    assert os.access("/data", os.W_OK)
    with tempfile.TemporaryDirectory(prefix="dcc-kiri-smoke-", dir="/data") as directory:
        env = {**os.environ, "KIRI_PANEL_DATA": directory, "KIRI_PANEL_BIND": "127.0.0.1", "KIRI_PANEL_PORT": "18796"}
        subprocess.run([sys.executable, "-m", "backend.admin", "--password-stdin"], input=PASSWORD + "\n",
                       text=True, env=env, check=True)
        client = PanelHTTP(origin)
        for restart in (False, True):
            start = time.monotonic()
            with subprocess.Popen([sys.executable, "-m", "backend"], env=env) as service:
                try:
                    wait_ready(client)
                    delay = time.monotonic() - start
                    evidence = client.login()
                    assert evidence["version"] == VERSION
                    assert evidence["endpoints"] == [] and not evidence["demo"]
                    if restart:
                        assert evidence["preferences"]["theme"] == "light"
                    else:
                        client.request("/api/preferences", {"theme": "light"}, "PUT")
                        try:
                            client.request("/api/profiles", {"name": "Rejected", "host": "linux", "runtime": "docker",
                                                             "endpoint": "/var/run/docker.sock"})
                        except HTTPError as error:
                            assert error.code == 409
                        else:
                            raise AssertionError("Engine fallback accepted")
                        memory_kib, peak_kib = 0, 0
                        for line in Path(f"/proc/{service.pid}/status").read_text().splitlines():
                            if line.startswith("VmRSS:"):
                                memory_kib = int(line.split()[1])
                            elif line.startswith("VmHWM:"):
                                peak_kib = int(line.split()[1])
                        cpu_file = Path(f"/proc/{service.pid}/stat")
                        counters = cpu_file.read_text().split()
                        before_cpu = int(counters[13]) + int(counters[14])
                        before_time = time.monotonic()
                        time.sleep(1)
                        counters = cpu_file.read_text().split()
                        ticks = int(counters[13]) + int(counters[14]) - before_cpu
                        cpu_percent = 100 * ticks / os.sysconf("SC_CLK_TCK") / (time.monotonic() - before_time)
                        print(json.dumps({"readiness_s": round(delay, 3), "server_rss_kib_after_login": memory_kib,
                                          "server_peak_rss_kib": peak_kib, "idle_cpu_percent_1s": round(cpu_percent, 2),
                                          "python_processes": 1}))
                finally:
                    service.terminate()
                    try:
                        service.wait(timeout=7)
                    except subprocess.TimeoutExpired:
                        service.kill()
                        raise
                    assert service.returncode == 0


if __name__ == "__main__":
    smoke()
