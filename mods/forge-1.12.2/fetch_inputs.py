"""Download compile-only dependencies with pinned hashes and atomic promotion."""

import argparse
import hashlib
import json
import os
import tempfile
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent


def ensure_input(name, cache, pins, *, opener=urlopen, max_bytes=32 * 1024**2):
    pin = pins[name]
    filename = pin["filename"]
    if (
        Path(filename).name != filename
        or "\\" in filename
        or not filename.endswith(".jar")
    ):
        raise ValueError("Noncanonical dependency filename")
    if not pin["download"].startswith("https://"):
        raise ValueError("Dependency must use HTTPS")
    cache = Path(cache).absolute()
    if cache.is_symlink() or cache.is_junction():
        raise ValueError("Linked dependency cache")
    cache.mkdir(parents=True, exist_ok=True)
    target = cache / filename
    if target.is_symlink() or target.is_junction():
        raise ValueError("Linked dependency file")
    if target.exists():
        if hashlib.sha256(target.read_bytes()).hexdigest() != pin["sha256"]:
            raise ValueError("Cached dependency hash mismatch: " + name)
        return target
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=cache, prefix=".download-", delete=False
        ) as output:
            temporary = Path(output.name)
            digest, size = hashlib.sha256(), 0
            request = Request(
                pin["download"], headers={"User-Agent": "OmkalityCraft-ModBuilder/1.0"}
            )
            with opener(request, timeout=30) as response:
                if not response.geturl().startswith("https://"):
                    raise ValueError("Insecure dependency redirect")
                while block := response.read(64 * 1024):
                    size += len(block)
                    if size > max_bytes:
                        raise ValueError("Dependency exceeds download budget")
                    digest.update(block)
                    output.write(block)
            if digest.hexdigest() != pin["sha256"]:
                raise ValueError("Downloaded dependency hash mismatch: " + name)
        os.replace(temporary, target)
        return target
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, default=ROOT / "tools")
    args = parser.parse_args()
    pins = json.loads((ROOT / "build-tools.json").read_text(encoding="utf-8"))
    for name in pins:
        ensure_input(name, args.cache, pins)
        print(name + ": verified " + pins[name]["sha256"])


if __name__ == "__main__":
    main()
