import json
import zipfile
from importlib import metadata

import pytest
from PyInstaller.building.build_main import Analysis

from launcher.install import current_platform
from launcher.releases import ReleaseError
from launcher.version import VERSION
from scripts.release import release_materials as materials
from tests.fixtures.unit.release.release_materials import bundle

__all__ = ["bundle"]


def distribution(site, name, *, legal=True):
    folder = site / f"{name}-1.0.dist-info"
    folder.mkdir(parents=True)
    module = site / name / "__init__.py"
    module.parent.mkdir()
    module.write_bytes(b"synthetic module")
    (folder / "METADATA").write_text(
        f"Name: {name}\nVersion: 1.0\nLicense: MIT\n", encoding="utf-8"
    )
    paths = [f"{name}/__init__.py"]
    if legal:
        (folder / "licenses").mkdir()
        (folder / "licenses/LICENSE").write_bytes(b"exact upstream license bytes\r\n")
        paths.append(f"{folder.name}/licenses/LICENSE")
    (folder / "RECORD").write_text(
        "".join(f"{path},,\n" for path in paths), encoding="utf-8"
    )
    return metadata.Distribution.at(folder), module


def zip_bundle(folder, *, extra=None):
    archive = folder.parent / f"OmkalityCraft-{VERSION}-{current_platform()}.zip"
    with zipfile.ZipFile(archive, "w") as zipped:
        for path in sorted(folder.rglob("*")):
            if path.is_file():
                zipped.write(path, path.relative_to(folder).as_posix())
        if extra:
            zipped.writestr(*extra)
    return archive


def test_only_collected_distribution_not_all_installed_gets_notices(bundle, tmp_path):
    used, source = distribution(tmp_path / "site", "used")
    unused, _ = distribution(tmp_path / "site", "unused_backend")
    report = materials.prepare_notices(
        bundle, [("used", str(source), "PYMODULE")], distributions=[unused, used]
    )
    names = {c["name"] for c in report["components"]}
    assert names == {"used", "CPython", "Launcher fonts"}
    assert (
        bundle / "licenses/used/000-LICENSE"
    ).read_bytes() == b"exact upstream license bytes\r\n"
    assert not (bundle / "licenses/unused-backend").exists()
    assert str(tmp_path) not in json.dumps(report)
    assert report["license_review_required_before_public_release"] is True


def test_qt_open_license_alternatives_and_unknown_native_are_explicit(bundle, tmp_path):
    qt, source = distribution(tmp_path / "site", "PySide6_Essentials")
    native = tmp_path / "external/libssl.so"
    entries = [
        ("PySide6", str(source), "PYMODULE"),
        ("libssl.so", str(native), "BINARY"),
    ]
    report = materials.prepare_notices(bundle, entries, distributions=[qt])
    assert report["native_files_requiring_license_review"] == ["libssl.so"]
    for filename in ["GPL-2.0.txt", "GPL-3.0.txt", "LGPL-3.0.txt"]:
        assert (
            bundle / "licenses/pyside6-essentials" / filename
        ).read_bytes() == materials.pinned_licenses()[filename]


def test_missing_distribution_license_stops_preparation(bundle, tmp_path):
    used, source = distribution(tmp_path / "site", "used", legal=False)
    with pytest.raises(ValueError, match="No license material"):
        materials.prepare_notices(
            bundle, [("used", str(source), "PYMODULE")], distributions=[used]
        )


def test_real_zip_inventory_checksum_and_embedded_notices(bundle):
    materials.prepare_notices(bundle, [], distributions=[])
    archive = zip_bundle(bundle)
    original = archive.read_bytes()
    materials.write_materials(archive, VERSION, current_platform())
    result = materials.verify_materials(archive, VERSION, current_platform())
    assert result["materials_verified"] is True
    assert result["files"] == len([p for p in bundle.rglob("*") if p.is_file()])
    assert archive.read_bytes() == original
    assert archive.with_suffix(".zip.sha256").read_bytes() == (
        f"{result['sha256']}  {archive.name}\n".encode()
    )
    manifest = json.loads(archive.with_suffix(".release.json").read_text())
    assert all(
        set(record) == {"path", "size", "sha256"} for record in manifest["files"]
    )
    assert str(bundle) not in json.dumps(manifest)


@pytest.mark.parametrize(
    "field", ["version", "platform", "checksum", "file-hash", "archive-bytes"]
)
def test_material_mismatch_fails(bundle, field):
    materials.prepare_notices(bundle, [], distributions=[])
    archive = zip_bundle(bundle)
    materials.write_materials(archive, VERSION, current_platform())
    sidecar = archive.with_suffix(".release.json")
    data = json.loads(sidecar.read_text())
    if field in {"version", "platform"}:
        data[field] = "wrong"
    elif field == "file-hash":
        data["files"][0]["sha256"] = "0" * 64
    elif field == "checksum":
        archive.with_suffix(".zip.sha256").write_text("wrong")
    else:
        archive.write_bytes(archive.read_bytes() + b"changed")
    materials.json_file(sidecar, data)
    with pytest.raises(ValueError):
        materials.verify_materials(archive, VERSION, current_platform())


@pytest.mark.parametrize(
    "path",
    [".env", "_internal/userdata/auth_token.json", "server/ops.json", "sources/api.py"],
)
def test_non_player_archive_contents_rejected(bundle, path):
    materials.prepare_notices(bundle, [], distributions=[])
    archive = zip_bundle(bundle, extra=(path, b"synthetic forbidden content"))
    with pytest.raises((ValueError, ReleaseError)):
        materials.write_materials(archive, VERSION, current_platform())


def test_unknown_python_dependency_cannot_silently_lose_its_notices(bundle, tmp_path):
    source = tmp_path / "site-packages/unknown.py"
    with pytest.raises(ValueError, match="No distribution metadata"):
        materials.prepare_notices(
            bundle, [("unknown", str(source), "PYMODULE")], distributions=[]
        )


def test_pinned_license_bytes_are_verified(tmp_path, monkeypatch):
    folder = tmp_path / "release_licenses"
    folder.mkdir()
    (folder / "GPL.txt").write_bytes(b"changed")
    materials.json_file(
        folder / "sources.json",
        {"schema": 1, "sources": [{"file": "GPL.txt", "sha256": "0" * 64}]},
    )
    monkeypatch.setattr(materials, "__file__", str(tmp_path / "release_materials.py"))
    with pytest.raises(ValueError, match="Pinned license text changed"):
        materials.pinned_licenses()


def test_missing_license_in_zip_rejected_even_with_fresh_hashes(bundle):
    materials.prepare_notices(bundle, [], distributions=[])
    (bundle / "licenses/Python-3.14.2.txt").unlink()
    with pytest.raises(ValueError, match="license material is missing"):
        materials.write_materials(zip_bundle(bundle), VERSION, current_platform())


@pytest.mark.parametrize(
    "module", ["omk.owner.admin", "api.main", "pytest", "litestar.app"]
)
def test_analysis_policy_checks_modules_hidden_inside_executable(tmp_path, module):
    values = [None] * len(Analysis._GUTS)
    fields = [field[0] for field in Analysis._GUTS]
    for name in ["pure", "scripts", "binaries", "datas"]:
        values[fields.index(name)] = []
    values[fields.index("pure")] = [(module, "/synthetic/source.py", "PYMODULE")]
    path = tmp_path / "Analysis-00.toc"
    path.write_text(repr(tuple(values)), encoding="utf-8")
    with pytest.raises(ValueError, match="Non-player module"):
        materials.analysis_entries(path)


def test_locked_analysis_format_preserves_expected_runtime_modules(tmp_path):
    values = [None] * len(Analysis._GUTS)
    fields = [field[0] for field in Analysis._GUTS]
    for name in ["pure", "scripts", "binaries", "datas"]:
        values[fields.index(name)] = []
    entries = [
        (name, "/synthetic/source.py", "PYMODULE")
        for name in ["launcher.app", "omk.accounts.drasl", "omk.shared.content_policy"]
    ]
    values[fields.index("pure")] = entries
    path = tmp_path / "Analysis-00.toc"
    path.write_text(repr(tuple(values)), encoding="utf-8")
    assert materials.analysis_entries(path) == entries
    path.write_text(repr(tuple(values[:-1])), encoding="utf-8")
    with pytest.raises(ValueError, match="analysis format"):
        materials.analysis_entries(path)
