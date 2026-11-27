"""Build a portable bundle on its target OS, from an explicit source allowlist."""

import argparse
import json
import os
import shutil
import subprocess
import sys
import zipfile
from importlib.metadata import version as installed_version
from pathlib import Path
from uuid import uuid4

from packaging.version import Version
from PIL import Image
from tuf.api.metadata import Metadata, Root

from launcher.install import current_platform
from launcher.paths import MACOS_APP, MACOS_RUNTIME, bundle_entrypoint
from launcher.releases import generation_floors
from launcher.version import VERSION
from omk.accounts.drasl import DraslClient
from omk.shared.profiles import PROJECT_ROOT
from scripts.release.release_materials import (
    analysis_entries,
    json_file,
    prepare_notices,
    verify_materials,
    write_materials,
)


def packaging_icon(source: Path, stage: Path) -> Path:
    """Pad the original pixels so platform converters cannot stretch a rectangle."""
    with Image.open(source) as opened:
        image = opened.convert("RGBA")
        edge = max(128, *image.size)
        canvas = Image.new("RGBA", (edge, edge))
        canvas.paste(image, ((edge - image.width) // 2, (edge - image.height) // 2))
        target = stage / "app-icon.png"
        canvas.save(target)
    return target


def _stage_macos_app(dist: Path, bundle: Path, platform: str) -> None:
    bundle.mkdir(parents=True)
    app = bundle / MACOS_APP
    shutil.move(dist / MACOS_APP, app)
    executable = bundle / bundle_entrypoint(platform)
    runtime = executable.with_name(MACOS_RUNTIME)
    executable.rename(runtime)
    subprocess.run(
        [
            "/usr/bin/clang",
            "-Os",
            "-fobjc-arc",
            "-framework",
            "AppKit",
            str(Path(__file__).with_name("macos_bootstrap.m")),
            "-o",
            str(executable),
        ],
        check=True,
    )
    # The former main binary can no longer use the signature of the app it belonged to.
    for code in (runtime, app):
        subprocess.run(
            ["/usr/bin/codesign", "--force", "--sign", "-", str(code)], check=True
        )
    subprocess.run(
        ["/usr/bin/codesign", "--verify", "--deep", "--strict", str(app)], check=True
    )


def _write_zip(archive: Path, bundle: Path, *, macos: bool) -> None:
    with zipfile.ZipFile(
        archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6
    ) as target:
        for path in sorted(bundle.rglob("*")):
            if macos and path.is_symlink():
                raise ValueError(
                    "macOS launcher app must be portable without ZIP symlinks"
                )
            if path.is_file():
                target.write(path, path.relative_to(bundle).as_posix())


def build(
    output: Path,
    root_metadata: Path,
    auth_url: str,
    api_url: str,
    version: str,
    *,
    minimum_pack_generations: dict[str, int] | None = None,
    send_client_reports: bool = False,
) -> Path:
    Version(version)
    floors = generation_floors(minimum_pack_generations or {})
    if not isinstance(Metadata.from_file(str(root_metadata)).signed, Root):
        raise ValueError("Expected public TUF root metadata")
    auth_url, api_url = DraslClient(auth_url).base_url, DraslClient(api_url).base_url
    stage = PROJECT_ROOT / ".local/build" / uuid4().hex[:10]
    stage.mkdir(parents=True)
    for package, names in {
        "launcher": [
            path.relative_to(PROJECT_ROOT / "launcher").as_posix()
            for path in (PROJECT_ROOT / "launcher").rglob("*.py")
            if all(
                part.isidentifier() and not part.startswith(".")
                for part in path.relative_to(PROJECT_ROOT / "launcher")
                .with_suffix("")
                .parts
            )
        ],
        "omk": [
            "__init__.py",
            "accounts/__init__.py",
            "accounts/drasl.py",
            "observability/__init__.py",
            "observability/diagnostics.py",
            "observability/incident_delivery.py",
            "observability/incidents.py",
            "shared/__init__.py",
            "shared/content_policy.py",
            "shared/fs.py",
            "shared/nbt.py",
            "shared/profiles.py",
        ],
    }.items():
        for name in names:
            destination = stage / package / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(PROJECT_ROOT / package / name, destination)
    assets = stage / "launcher/assets"
    for name in [
        "fonts/Rubik.ttf",
        "fonts/OFL.txt",
        "fonts/Monocraft-Bold.ttf",
        "fonts/Monocraft-LICENSE.txt",
        "fonts/provenance.json",
        "dj2.svg",
        "external-link.svg",
        "checkmark.svg",
        "forge-1.12.2-log4j2.xml",
        "theme.qss",
        "social-youtube.svg",
        "social-twitch.svg",
        "social-kick.svg",
        "social-telegram.svg",
        "release-keys.json",
        "branding/icon.png",
        "branding/provenance.json",
        "guides/dj2-claims.png",
        "guides/dj2-inventory.png",
        "skins/default-slim.png",
        "skins/default-classic.png",
        "skins/default-legacy.png",
        "skins/provenance.json",
    ]:
        destination = assets / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(PROJECT_ROOT / "launcher/assets" / name, destination)
    shutil.copyfile(root_metadata, assets / "tuf-root.json")
    icon = packaging_icon(assets / "branding/icon.png", stage)
    (assets / "deployment.json").write_text(
        json.dumps(
            {
                "auth_url": auth_url,
                "api_url": api_url,
                "minimum_pack_generations": floors,
                "send_client_reports": send_client_reports,
            }
        ),
        encoding="utf-8",
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
    bundle = output / "OmkalityCraft"
    macos = sys.platform == "darwin"
    dist = stage / "dist" if macos else output
    if any((output / name).exists() for name in ("OmkalityCraft", MACOS_APP)):
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
            # The macOS one-file app needs no ZIP symlinks, including on 0.3.5 upgrades.
            "--onefile" if macos else "--onedir",
            "--windowed",
            "--name",
            "OmkalityCraft",
            *(["--icon", str(icon)] if sys.platform in {"win32", "darwin"} else []),
            *(
                [
                    "--osx-bundle-identifier",
                    "io.github.omkality.omkalitycraft",
                    "--runtime-tmpdir",
                    "userdata/tmp",
                ]
                if macos
                else []
            ),
            "--distpath",
            str(dist),
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
    platform = current_platform()
    if macos:
        _stage_macos_app(dist, bundle, platform)
    if not (bundle / bundle_entrypoint(platform)).is_file():
        raise ValueError("Built launcher entrypoint is missing")
    entries = analysis_entries(stage / "work/OmkalityCraft/Analysis-00.toc")
    prepare_notices(bundle, entries, embedded_fonts=assets / "fonts" if macos else None)
    json_file(
        bundle / "release-info.json",
        {
            "schema": 1,
            "version": version,
            "platform": platform,
            "python": "3.14.2",
            "pyinstaller": installed_version("pyinstaller"),
        },
    )
    archive = output / f"OmkalityCraft-{version}-{platform}.zip"
    _write_zip(archive, bundle, macos=macos)
    write_materials(archive, version, platform)
    verify_materials(archive, version, platform)
    return archive


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--root-metadata", type=Path, required=True)
    parser.add_argument("--auth-url", required=True)
    parser.add_argument("--api-url", required=True)
    parser.add_argument(
        "--send-client-reports",
        action="store_true",
        help="Send a short crash report to the trusted API after a crash",
    )
    parser.add_argument("--version", default=VERSION)
    parser.add_argument(
        "--minimum-pack-generations",
        type=json.loads,
        default={},
        help='Trusted minimum generations in JSON, for example {"dj2":1}',
    )
    args = parser.parse_args()
    print(
        build(
            args.output,
            args.root_metadata,
            args.auth_url,
            args.api_url,
            args.version,
            minimum_pack_generations=args.minimum_pack_generations,
            send_client_reports=args.send_client_reports,
        )
    )


if __name__ == "__main__":
    main()
