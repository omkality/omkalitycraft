"""Native TUI checks; the Rust integration test must use this project's Python."""

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    subprocess.run(
        [sys.executable, str(ROOT / "scripts/tui_branding.py"), "--check"],
        check=True,
        timeout=15,
    )
    environment = {**os.environ, "OMK_TEST_PYTHON": sys.executable}
    for arguments in (
        ["fmt", "--check"],
        ["test", "--locked", "-j", "4"],
        ["clippy", "--locked", "-j", "4", "--all-targets", "--", "-D", "warnings"],
        ["build", "--locked", "--release", "-j", "4"],
    ):
        subprocess.run(
            ["cargo", "+1.93.1", *arguments],
            cwd=ROOT / "tui",
            env=environment,
            check=True,
            timeout=600,
        )


if __name__ == "__main__":
    main()
