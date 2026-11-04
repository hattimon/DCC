"""Isolated Docker smoke for Remote Access, with zero zrok API calls."""
import argparse
import subprocess
import uuid

from remote_access_fixture import INSIDE


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True)
    args = parser.parse_args()
    name = "dcc-remote-smoke-" + uuid.uuid4().hex[:10]
    volume = name + "-data"
    label = "dcc.qa=remote-access"

    def docker(*command, input_data=None):
        result = subprocess.run(["docker", *command], input=input_data, capture_output=True, text=True, timeout=240)
        if result.returncode:
            raise RuntimeError("Docker QA operation failed: " + command[0] + ": " + result.stderr[-1500:])
        return result.stdout.strip()

    docker("volume", "create", "--label", label, volume)
    panel_started = False
    managed = None
    try:
        docker("run", "-d", "--name", name, "--label", label, "-v", volume+":/data",
               "-v", "/var/run/docker.sock:/var/run/docker.sock", "-e", "DCC_WEB_CONTAINER_NAME="+name, args.image)
        panel_started = True
        print(docker("exec", "-i", name, "/usr/local/bin/dcc-web-entrypoint", "python", "-", input_data=INSIDE))
    finally:
        # Test artifacts have a unique fixture name. Never remove by generic app label.
        if panel_started:
            try:
                managed = docker("exec", "--user", "10001:10001", name, "python", "-c",
                                 "import sys;sys.path.insert(0,'/opt/dcc');from flask import Flask;from state import State;from remote_access import RemoteAccess;print(RemoteAccess(Flask(__name__),State('/data')).name)")
                docker("rm", "-f", managed)
            except RuntimeError:
                pass
            finally:
                docker("rm", "-f", name)
            if managed:
                for suffix in ("-panel", "-egress"):
                    try:
                        docker("network", "rm", managed+suffix)
                    except RuntimeError:
                        pass
        docker("volume", "rm", volume)


if __name__ == "__main__":
    main()
