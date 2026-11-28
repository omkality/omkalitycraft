"""Download compile-only dependencies with pinned hashes and atomic promotion."""

import argparse
import hashlib
import json
import os
import sys
import tempfile
import time
from datetime import UTC
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent
RETRY_DELAYS = (2, 5, 10)
RETRY_WAIT_BUDGET = 30


def _retry_after(value):
    if value is None:
        return 0
    value = value.strip()
    if value.isascii() and value.isdecimal():
        return float(value)
    try:
        retry_at = parsedate_to_datetime(value)
        if retry_at.tzinfo is None:
            retry_at = retry_at.replace(tzinfo=UTC)
        return max(0, retry_at.timestamp() - time.time())
    except (ValueError, OverflowError, OSError) as _:
        return 0


def _open_input(request, filename, opener):
    remaining_wait = RETRY_WAIT_BUDGET
    for backoff in (*RETRY_DELAYS, None):
        try:
            return opener(request, timeout=30)
        except HTTPError as error:
            error.add_note(f"Dependency: {filename}")
            if error.code != 429 or backoff is None:
                raise
            retry_after = error.headers.get("Retry-After") if error.headers else None
            delay = max(backoff, _retry_after(retry_after))
            if delay > remaining_wait:
                error.add_note("Dependency retry wait budget exceeded")
                raise
            error.close()
        remaining_wait -= delay
        print(
            f"{filename}: HTTP 429, retrying in {delay:g}s", file=sys.stderr, flush=True
        )
        time.sleep(delay)


def ensure_input(name, cache, pins, *, opener=urlopen, max_bytes=32 * 1024**2):
    """Return a verified dependency from cache or download it atomically."""
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
            with _open_input(request, filename, opener) as response:
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
        temporary.chmod(
            0o644
        )  # Public compile inputs must cross a Linux bind-mount UID boundary.
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
        path = ensure_input(name, args.cache, pins)
        path.chmod(
            0o644
        )  # Repair an older verified cache before the read-only container mount.
        print(name + ": verified " + pins[name]["sha256"])


if __name__ == "__main__":
    main()
