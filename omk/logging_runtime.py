"""Pinned Java 8 Log4j for explicit staging/labs, never downloaded by a game launch."""

import hashlib
import json
from pathlib import Path
from urllib.request import urlopen

from omk.profiles import PROJECT_ROOT


def logging_pins():
    return json.loads(
        (PROJECT_ROOT / "profiles/runtime/log4j-java8.json").read_text(encoding="utf-8")
    )


def stage_logging_runtime(destination: Path) -> list[Path]:
    root = destination.resolve()
    result = []
    for artifact in logging_pins()["artifacts"]:
        path = root / artifact["path"]
        if path.resolve() != path:
            raise ValueError("Linked runtime path")
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            with path.open("rb") as file:
                data = file.read(artifact["size"] + 1)
        else:
            with urlopen(artifact["source"], timeout=30) as response:
                data = response.read(artifact["size"] + 1)
        if (
            len(data) != artifact["size"]
            or hashlib.sha256(data).hexdigest() != artifact["sha256"]
        ):
            raise ValueError("Pinned logging artifact mismatch")
        if not path.exists():
            path.write_bytes(data)
        result.append(path)
    return result


def logging_classpath(classpath: list[str]) -> list[str]:
    paths = [item["path"] for item in logging_pins()["artifacts"]]
    old = tuple(
        "libraries/org/apache/logging/log4j/" + name + "/"
        for name in ("log4j-api", "log4j-core")
    )
    return paths + [p for p in classpath if not p.startswith(old)]
