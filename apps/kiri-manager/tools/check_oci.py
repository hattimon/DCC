"""Verify both OCI images and optionally compare a registry manifest with the archive."""
import argparse
import hashlib
import json
import tarfile

INDEX = "application/vnd.oci.image.index.v1+json"
PLATFORMS = {"amd64", "arm64"}


def arch_refs(index):
    refs = {row["platform"]["architecture"]: row["digest"] for row in index["manifests"]
            if row.get("platform", {}).get("os") == "linux"}
    if set(refs) != PLATFORMS or len(index["manifests"]) != len(PLATFORMS):
        raise ValueError("Expected exactly two Linux image manifests")
    return refs


def inspect_archive(filename, version):
    with tarfile.open(filename) as archive:
        def read(name):
            return archive.extractfile(name).read()

        def blob(digest):
            method, value = digest.split(":", 1)
            if method != "sha256" or len(value) != 64:
                raise ValueError("Expected a SHA-256 digest")
            data = read("blobs/sha256/" + value)
            if hashlib.sha256(data).hexdigest() != value:
                raise ValueError("OCI blob failed integrity verification")
            return json.loads(data)

        index = json.loads(read("index.json"))
        if len(index["manifests"]) == 1 and index["manifests"][0]["mediaType"] == INDEX:
            index = blob(index["manifests"][0]["digest"])
        refs = arch_refs(index)
        reporting = {}
        for arch, digest in sorted(refs.items()):
            image = blob(digest)
            config = blob(image["config"]["digest"])
            runtime = config["config"]
            if (config["os"], config["architecture"], runtime["User"]) != ("linux", arch, "10001:10001"):
                raise ValueError(f"Incorrect Linux image runtime metadata for {arch}")
            if runtime["Labels"]["org.opencontainers.image.version"] != version:
                raise ValueError("Image and source versions differ")
            if "/data" not in runtime["Volumes"] or not runtime.get("Healthcheck", {}).get("Test"):
                raise ValueError("Expected a persistent volume and healthcheck")

            layers = image["layers"]
            for item in layers:
                layer = archive.getmember("blobs/" + item["digest"].replace(":", "/"))
                if layer.size != item["size"]:
                    raise ValueError("Incorrect OCI layer size")
                with archive.extractfile(layer) as stream:
                    if "sha256:" + hashlib.file_digest(stream, "sha256").hexdigest() != item["digest"]:
                        raise ValueError("OCI layer failed integrity verification")
            reporting[arch] = {"digest": digest, "compressed_layer_bytes": sum(layer["size"] for layer in layers)}
        return reporting


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive")
    parser.add_argument("version")
    parser.add_argument("--registry-index")
    args = parser.parse_args()
    metadata = inspect_archive(args.archive, args.version)
    if args.registry_index:
        with open(args.registry_index, encoding="utf-8") as stream:
            current = arch_refs(json.load(stream))
        if current != {arch: value["digest"] for arch, value in metadata.items()}:
            raise SystemExit("Registry architecture digests differ from the verified archive")
    print(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    main()
