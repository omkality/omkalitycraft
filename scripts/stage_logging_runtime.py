"""Prepare explicitly selected release staging files. Does not sign, launch or deploy."""

import argparse
import json
from pathlib import Path

from omk.logging_runtime import logging_classpath, stage_logging_runtime


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--files", type=Path, required=True)
    parser.add_argument("--launch-profile", type=Path, required=True)
    parser.add_argument("--output-profile", type=Path, required=True)
    args = parser.parse_args()
    profile = json.loads(args.launch_profile.read_text(encoding="utf-8"))
    profile["classpath"] = logging_classpath(profile["classpath"])
    stage_logging_runtime(args.files)
    with args.output_profile.open("x", encoding="utf-8") as output:
        output.write(json.dumps(profile, ensure_ascii=False, indent=2) + "\n")
    print(
        "Prepared pinned logging libraries and launch profile; not signed or deployed."
    )


if __name__ == "__main__":
    main()
