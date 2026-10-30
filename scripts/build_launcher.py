"""Build a portable bundle on its target OS, from an explicit source allowlist."""

import argparse
import json
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from uuid import uuid4

from packaging.version import Version
from tuf.api.metadata import Metadata, Root

from launcher.install import current_platform
from launcher.version import VERSION
from omk.drasl import DraslClient
from omk.profiles import PROJECT_ROOT


def build(
    output: Path, root_metadata: Path, auth_url: str, api_url: str, version: str
) -> Path:
    Version(version)
    if not isinstance(Metadata.from_file(str(root_metadata)).signed, Root):
        raise ValueError("Expected public TUF root metadata")
    auth_url, api_url = DraslClient(auth_url).base_url, DraslClient(api_url).base_url
    stage = PROJECT_ROOT / ".local/build" / uuid4().hex[:10]
    stage.mkdir(parents=True)
    for package, names in {
        "launcher": [path.name for path in (PROJECT_ROOT / "launcher").glob("*.py")],
        "omk": [
            "__init__.py",
            "drasl.py",
            "profiles.py",
            "fs.py",
            "diagnostics.py",
            "incidents.py",
        ],
        "api": ["__init__.py", "core/__init__.py", "core/content_policy.py"],
    }.items():
        for name in names:
            destination = stage / package / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(PROJECT_ROOT / package / name, destination)
    assets = stage / "launcher/assets"
    for name in [
        "fonts/Rubik.ttf",
        "fonts/OFL.txt",
        "fonts/provenance.json",
        "dj2.svg",
        "gtnh.svg",
        "external-link.svg",
        "release-keys.json",
    ]:
        destination = assets / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(PROJECT_ROOT / "launcher/assets" / name, destination)
    shutil.copyfile(root_metadata, assets / "tuf-root.json")
    (assets / "deployment.json").write_text(
        json.dumps({"auth_url": auth_url, "api_url": api_url}), encoding="utf-8"
    )
    (stage / "launcher/version.py").write_text(
        f"VERSION = {version!r}\n", encoding="utf-8"
    )
    (stage / "profiles").mkdir()
    shutil.copyfile(
        PROJECT_ROOT / "profiles/servers.toml", stage / "profiles/servers.toml"
    )
    entrypoint = stage / "start_launcher.py"
    entrypoint.write_text(
        "from launcher.__main__ import main\nraise SystemExit(main())\n",
        encoding="utf-8",
    )
    output = output.resolve()
    if (output / "OmkalityCraft").exists():
        raise ValueError("Use a fresh build output folder")
    environment = {**os.environ, "PYTHONNOUSERSITE": "1"}
    for name in ["PYTHONHOME", "PYTHONPATH"]:
        environment.pop(name, None)
    if sys.platform == "win32":
        windows = Path(os.environ["SYSTEMROOT"])
        # Do not collect unrelated ICU/Qt DLLs from tools installed on the builder's PATH.
        environment["PATH"] = os.pathsep.join(
            map(
                str,
                [
                    Path(sys.executable).parent,
                    Path(sys.base_prefix),
                    Path(sys.base_prefix) / "DLLs",
                    windows / "System32",
                    windows,
                ],
            )
        )
    subprocess.run(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--clean",
            "--onedir",
            "--windowed",
            "--name",
            "OmkalityCraft",
            "--distpath",
            str(output),
            "--workpath",
            str(stage / "work"),
            "--specpath",
            str(stage),
            "--paths",
            str(stage),
            "--add-data",
            f"{assets}:launcher/assets",
            "--add-data",
            f"{stage / 'profiles'}:profiles",
            str(entrypoint),
        ],
        cwd=stage,
        env=environment,
        check=True,
    )
    bundle = output / "OmkalityCraft"
    archive = output / f"OmkalityCraft-{version}-{current_platform()}.zip"
    with zipfile.ZipFile(
        archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6
    ) as target:
        for path in sorted(bundle.rglob("*")):
            if path.is_file():
                target.write(path, path.relative_to(bundle).as_posix())
    return archive


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--root-metadata", type=Path, required=True)
    parser.add_argument("--auth-url", required=True)
    parser.add_argument("--api-url", required=True)
    parser.add_argument("--version", default=VERSION)
    args = parser.parse_args()
    print(
        build(
            args.output, args.root_metadata, args.auth_url, args.api_url, args.version
        )
    )


if __name__ == "__main__":
    main()
