"""Prepare and verify launcher release materials from the actual PyInstaller input."""

import argparse
import ast
import hashlib
import json
import re
import shutil
import sys
import zipfile
from importlib import metadata
from pathlib import Path, PurePosixPath

from launcher.install import current_platform
from launcher.releases import sha256_file
from launcher.updater import LauncherUpdater
from launcher.version import VERSION

FIRST_PARTY = {
    "omk",
    "omk.drasl",
    "omk.profiles",
    "omk.fs",
    "omk.diagnostics",
    "omk.incidents",
    "omk.content_policy",
    "omk.nbt",
}
FORBIDDEN_PACKAGES = {
    "litestar",
    "granian",
    "pytest",
    "_pytest",
    "pytestqt",
    "testcontainers",
    "mypy",
    "black",
    "ruff",
}
FORBIDDEN_FILES = {
    ".git",
    ".env",
    ".omk-admin",
    "userdata",
    "instances",
    "mods",
    "world",
    "operator.toml",
    "auth_token.json",
    "drasl-session.json",
}


def json_file(path: Path, value) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def analysis_entries(path: Path) -> list[tuple[str, str, str]]:
    # The serializer's field order is taken from the installed, locked PyInstaller.
    from PyInstaller.building.build_main import Analysis  # noqa: PLC0415

    values = ast.literal_eval(path.read_text(encoding="utf-8"))
    if not isinstance(values, tuple) or len(values) != len(Analysis._GUTS):
        raise ValueError("Unsupported PyInstaller analysis format")
    fields = dict(zip((field[0] for field in Analysis._GUTS), values, strict=True))
    entries = []
    for field in ["pure", "scripts", "binaries", "datas"]:
        for entry in fields[field]:
            if len(entry) != 3 or not all(isinstance(value, str) for value in entry):
                raise ValueError("Invalid PyInstaller analysis entry")
            name, _, _kind = entry
            if field in {"pure", "scripts"}:
                package = name.split(".")[0]
                if package in FORBIDDEN_PACKAGES or (
                    package in {"omk", "api"} and name not in FIRST_PARTY
                ):
                    raise ValueError(f"Non-player module in launcher: {name}")
            entries.append(tuple(entry))
    return entries


def pinned_licenses() -> dict[str, bytes]:
    folder = Path(__file__).with_name("release_licenses")
    provenance = json.loads((folder / "sources.json").read_text(encoding="utf-8"))
    result = {}
    for record in provenance["sources"]:
        path = folder / record["file"]
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != record["sha256"]:
            raise ValueError("Pinned license text changed")
        result[path.name] = data
    return result


def _legal_file(path) -> bool:
    name = PurePosixPath(str(path)).name.upper()
    return name.startswith(
        ("LICENSE", "LICENCE", "COPYING", "NOTICE", "COPYRIGHT")
    ) and not name.endswith((".PY", ".PYC"))


def check_python_ownership(entries, owned_sources) -> None:
    for name, source, kind in entries:
        if (
            (kind.startswith("PYMODULE") or kind == "EXTENSION")
            and ({"site-packages", "dist-packages"} & set(Path(source).parts))
            and Path(source).resolve() not in owned_sources
        ):
            raise ValueError(
                f"No distribution metadata for collected Python dependency: {name}"
            )


def prepare_notices(bundle: Path, entries, *, distributions=None) -> dict:
    """Select installed distributions by exact collected source files, not pip freeze."""
    sources = {Path(source).resolve() for _, source, _ in entries if source}
    distributions = metadata.distributions() if distributions is None else distributions
    pinned = pinned_licenses()
    licenses = bundle / "licenses"
    licenses.mkdir()
    components, owned_sources = [], set()
    for distribution in distributions:
        files = list(distribution.files or [])
        matched = {
            Path(distribution.locate_file(file)).resolve() for file in files
        } & sources
        if not matched:
            continue
        name, version = distribution.metadata["Name"], distribution.version
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", name):
            raise ValueError("Invalid distribution name")
        slug = re.sub(r"[-_.]+", "-", name).lower()
        target = licenses / slug
        target.mkdir()
        notices = []
        for index, file in enumerate(sorted(filter(_legal_file, files), key=str)):
            original = Path(distribution.locate_file(file))
            destination = target / f"{index:03d}-{PurePosixPath(str(file)).name}"
            shutil.copyfile(original, destination)
            notices.append(destination.relative_to(bundle).as_posix())
        if slug.startswith("pyside6") or slug == "shiboken6":
            for filename in ["GPL-2.0.txt", "GPL-3.0.txt", "LGPL-3.0.txt"]:
                (target / filename).write_bytes(pinned[filename])
                notices.append((target / filename).relative_to(bundle).as_posix())
        if not notices:
            raise ValueError(f"No license material for collected distribution: {name}")
        components.append(
            {
                "name": name,
                "version": version,
                "collected_input_files": len(matched),
                "declared_license": distribution.metadata.get("License-Expression")
                or distribution.metadata.get("License"),
                "project_urls": distribution.metadata.get_all("Project-URL", []),
                "homepage": distribution.metadata.get("Home-page"),
                "notices": sorted(notices),
            }
        )
        owned_sources.update(matched)
    check_python_ownership(entries, owned_sources)
    if sys.version_info[:3] != (3, 14, 2):
        raise ValueError("Review the pinned Python license for this runtime version")
    python_license = licenses / "Python-3.14.2.txt"
    python_license.write_bytes(pinned[python_license.name])
    components.append(
        {
            "name": "CPython",
            "version": "3.14.2",
            "declared_license": "PSF-2.0",
            "notices": [python_license.relative_to(bundle).as_posix()],
        }
    )
    fonts = bundle / "_internal/launcher/assets/fonts"
    for filename in ["OFL.txt", "Monocraft-LICENSE.txt"]:
        if not (fonts / filename).is_file():
            raise ValueError("Bundled font license is missing")
    components.append(
        {
            "name": "Launcher fonts",
            "notices": [
                f"_internal/launcher/assets/fonts/{name}"
                for name in ["OFL.txt", "Monocraft-LICENSE.txt"]
            ],
        }
    )
    shutil.copyfile(
        Path(__file__).with_name("release_licenses") / "sources.json",
        licenses / "sources.json",
    )
    # Native dependencies outside wheel RECORDs need explicit review; do not invent owners.
    unassigned = sorted(
        {
            name
            for name, source, kind in entries
            if kind == "BINARY" and Path(source).resolve() not in owned_sources
        }
    )
    document = {
        "schema": 1,
        "components": sorted(components, key=lambda item: item["name"].casefold()),
        "native_files_requiring_license_review": unassigned,
        "license_review_required_before_public_release": True,
    }
    json_file(bundle / "components.json", document)
    lines = [
        "OmkalityCraft: included components and license materials",
        "The installed wheel notices and pinned primary license texts are reproduced unchanged.",
        "This inventory is not a certification of all redistribution obligations.",
        "Review native dependencies and Qt third-party notices before a public release.",
        "See licenses/sources.json for pinned text provenance; font provenance is in launcher assets.",
        "",
    ]
    for component in document["components"]:
        lines.append(f"{component['name']} {component.get('version', '')}")
        lines.extend(component["notices"])
        lines.append("")
    (bundle / "THIRD_PARTY_NOTICES.txt").write_text(
        "\n".join(lines), encoding="utf-8", newline="\n"
    )
    return document


def archive_inventory(archive: Path) -> list[dict]:
    with zipfile.ZipFile(archive) as zipped:
        LauncherUpdater._validate_zip(zipped.infolist())
        records = []
        for info in sorted(zipped.infolist(), key=lambda member: member.filename):
            path = PurePosixPath(info.filename)
            if any(part.casefold() in FORBIDDEN_FILES for part in path.parts):
                raise ValueError(f"Non-player file in launcher archive: {path}")
            if info.is_dir():
                continue
            if path.parts[0] not in {
                "OmkalityCraft",
                "OmkalityCraft.exe",
                "_internal",
                "licenses",
                "components.json",
                "THIRD_PARTY_NOTICES.txt",
                "release-info.json",
            }:
                raise ValueError(f"Unexpected top-level archive file: {path}")
            with zipped.open(info) as file:
                digest = hashlib.file_digest(file, "sha256").hexdigest()
            records.append(
                {"path": info.filename, "size": info.file_size, "sha256": digest}
            )
        required = {"components.json", "THIRD_PARTY_NOTICES.txt", "release-info.json"}
        if not required <= {record["path"] for record in records}:
            raise ValueError("Launcher release materials are missing")
        components = json.loads(zipped.read("components.json"))
        names = {record["path"] for record in records}
        for component in components["components"]:
            if not component["notices"] or not set(component["notices"]) <= names:
                raise ValueError("Component license material is missing from ZIP")
        return records


def write_materials(archive: Path, version: str, platform: str) -> None:
    document = {
        "schema": 1,
        "version": version,
        "platform": platform,
        "archive": {
            "name": archive.name,
            "size": archive.stat().st_size,
            "sha256": sha256_file(archive),
        },
        "files": archive_inventory(archive),
    }
    json_file(archive.with_suffix(".release.json"), document)
    archive.with_suffix(".zip.sha256").write_text(
        f"{document['archive']['sha256']}  {archive.name}\n",
        encoding="utf-8",
        newline="\n",
    )


def verify_materials(archive: Path, version: str, platform: str) -> dict:
    document = json.loads(
        archive.with_suffix(".release.json").read_text(encoding="utf-8")
    )
    digest = sha256_file(archive)
    if (
        document["schema"] != 1
        or document["version"] != version
        or document["platform"] != platform
        or document["archive"]
        != {"name": archive.name, "size": archive.stat().st_size, "sha256": digest}
    ):
        raise ValueError("Archive identity differs from release materials")
    if (
        archive.with_suffix(".zip.sha256").read_text(encoding="utf-8")
        != f"{digest}  {archive.name}\n"
    ):
        raise ValueError("Archive checksum file differs")
    if document["files"] != archive_inventory(archive):
        raise ValueError("Archive contents differ from release inventory")
    with zipfile.ZipFile(archive) as zipped:
        if json.loads(zipped.read("release-info.json")) != {
            "schema": 1,
            "version": version,
            "platform": platform,
            "python": "3.14.2",
            "pyinstaller": metadata.version("pyinstaller"),
        }:
            raise ValueError("Embedded build identity differs")
    return {
        "archive": archive.name,
        "sha256": digest,
        "files": len(document["files"]),
        "materials_verified": True,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    args = parser.parse_args()
    archive = args.archive.resolve()
    if archive.is_dir():
        archive /= f"OmkalityCraft-{VERSION}-{current_platform()}.zip"
    print(json.dumps(verify_materials(archive, VERSION, current_platform())))
