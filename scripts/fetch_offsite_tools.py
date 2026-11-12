"""Fetch reviewed Linux transport tools into a NEW private build directory."""

import argparse
import bz2
import hashlib
import io
import json
import os
import tarfile
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
MAX_DOWNLOAD = 16 * 1024**2
MAX_BINARY = 64 * 1024**2


def download(url):
    if not url.startswith("https://github.com/restic/"):
        raise ValueError("Offsite tools must use the reviewed upstream release")
    with urlopen(
        Request(url, headers={"User-Agent": "omkalitycraft-tool-fetch"}), timeout=40
    ) as response:
        raw = response.read(MAX_DOWNLOAD + 1)
    if len(raw) > MAX_DOWNLOAD:
        raise ValueError("Offsite download exceeds its bound")
    return raw


def decode(artifact, raw):
    if hashlib.sha256(raw).hexdigest() != artifact["download_sha256"]:
        raise ValueError("Offsite download differs from its reviewed pin")
    maximum = artifact["binary_bytes"]
    if type(maximum) is not int or not 1 <= maximum <= MAX_BINARY:
        raise ValueError("Invalid offsite binary size")
    if artifact["name"] == "restic":
        decoder = bz2.BZ2Decompressor()
        result = decoder.decompress(raw, max_length=maximum + 1)
        if not decoder.eof or decoder.unused_data:
            raise ValueError("Unexpected restic compressed stream")
    elif artifact["name"] == "rest-server":
        candidates = []
        with tarfile.open(fileobj=io.BytesIO(raw), mode="r|gz") as archive:
            for index, member in enumerate(archive):
                if index >= 32:
                    raise ValueError("Rest-server archive has too many entries")
                if member.name.endswith("/rest-server"):
                    if not member.isfile() or member.size != maximum:
                        raise ValueError("Unsupported rest-server binary entry")
                    candidates.append(archive.extractfile(member).read(maximum + 1))
        if len(candidates) != 1:
            raise ValueError("Ambiguous rest-server binary entry")
        result = candidates[0]
    else:
        raise ValueError("Unsupported offsite tool")
    if (
        len(result) != maximum
        or hashlib.sha256(result).hexdigest() != artifact["binary_sha256"]
    ):
        raise ValueError("Offsite binary differs from its reviewed pin")
    return result


def install(output):
    if output.resolve() != output.absolute() or output.exists() or output.is_symlink():
        raise ValueError("Offsite tool output must be a new unlinked directory")
    pins = json.loads((ROOT / "deploy/offsite-tools.json").read_bytes())
    if (
        pins["schema"] != 1
        or pins["platform"] != "linux/amd64"
        or {a["name"] for a in pins["artifacts"]} != {"restic", "rest-server"}
    ):
        raise ValueError("Unsupported offsite tool manifest")
    dockerfile = (ROOT / "deploy/offsite/Dockerfile").read_bytes()
    if ("FROM " + pins["python_image"]).encode() not in dockerfile:
        raise ValueError("Offsite helper base image drifted")
    output.mkdir(parents=True, mode=0o700)
    for artifact in pins["artifacts"]:
        binary = decode(artifact, download(artifact["source"]))
        file = output / artifact["name"]
        with file.open("xb") as stream:
            stream.write(binary)
            stream.flush()
            os.fsync(stream.fileno())
        file.chmod(0o555)
    # A failed fetch has no build recipe and cannot masquerade as a ready context.
    (output / "provenance.json").write_bytes(
        json.dumps(pins, indent=2).encode() + b"\n"
    )
    (output / ".dockerignore").write_text(
        "**\n!restic\n!rest-server\n!Dockerfile\n", encoding="utf-8"
    )
    (output / "Dockerfile").write_bytes(dockerfile)
    return {"tools": len(pins["artifacts"]), "platform": pins["platform"]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(install(args.output.absolute())))
