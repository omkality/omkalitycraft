"""Review the exact tracked publication boundary, not ignored local build data."""

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PREFIX = "mods/forge-1.12.2/"


def main():
    names = (
        subprocess.check_output(["git", "ls-files", "-z", "--", "mods/"], cwd=ROOT)
        .decode()
        .split("\0")
    )
    outside = {name for name in names if name and not name.startswith(PREFIX)}
    if outside != {"mods/README.md", "mods/AGENTS.md"}:
        raise ValueError(
            "Unreviewed top-level mod source paths: " + str(sorted(outside))
        )
    actual = {name.removeprefix(PREFIX) for name in names if name.startswith(PREFIX)}
    expected = set(
        json.loads((ROOT / PREFIX / "public-files.json").read_text())["files"]
    )
    if actual != expected:
        raise ValueError(
            f"Public mod boundary differs: missing={sorted(expected-actual)}, extra={sorted(actual-expected)}"
        )
    for name in sorted(actual):
        path = Path(name)
        if {"lab", "validation", "tools", "build", ".git"} & set(path.parts):
            raise ValueError("Private/build directory is tracked: " + name)
        allowed = {".java", ".py", ".md", ".json", ".properties", ".png"}
        if path.suffix.lower() not in allowed and name not in {
            ".gitignore",
            ".gitattributes",
            ".dockerignore",
            "Dockerfile.build",
        }:
            raise ValueError("Non-source payload is tracked: " + name)
        data = subprocess.check_output(["git", "show", ":" + PREFIX + name], cwd=ROOT)
        if len(data) > 2 * 1024**2:
            raise ValueError("Public source object exceeds size budget: " + name)
        if path.suffix != ".png":
            data.decode("utf-8")
    print(
        f"Public Forge source boundary: {len(actual)} tracked files; no private lab or build payload"
    )


if __name__ == "__main__":
    main()
