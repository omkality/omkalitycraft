import hashlib
import json
import sys
import zipfile
from types import SimpleNamespace
from uuid import uuid4

import pytest

from omk import linux_world_restore as restore
from omk.backup_archive import validate_inventory, verify_archive
from omk.backup_store import BackupPolicy, BackupStore

POLICY = BackupPolicy(16 * 1024**2, 3, 8 * 1024**2, 1)


def files(name="world/data/ftb_lib/players/con.dat"):
    return {
        "world/level.dat": {"bytes": 5, "sha256": hashlib.sha256(b"level").hexdigest()},
        name: {"bytes": 4, "sha256": hashlib.sha256(b"data").hexdigest()},
    }


@pytest.mark.parametrize(
    "name",
    ["con.dat", "CON.dat", "nul.dat", "aux.dat", "prn.dat", "com1.dat", "LPT9.dat"],
)
def test_reserved_names_are_explicit_linux_policy_only(name):
    inventory = files("world/data/ftb_lib/players/" + name)
    with pytest.raises(ValueError):
        validate_inventory(inventory)
    validate_inventory(inventory, path_policy="linux-server")


@pytest.mark.parametrize(
    "name",
    [
        "/absolute",
        "../escape",
        "world/../escape",
        "world//file",
        "world/C:stream",
        "world/a\\b",
        "world/a.",
        "world/a ",
        "world/a\x00b",
    ],
)
def test_linux_policy_keeps_path_guards(name):
    with pytest.raises(ValueError):
        validate_inventory(files(name), path_policy="linux-server")


def test_linux_policy_rejects_case_collisions_and_unknown_policy():
    inventory = files()
    inventory["world/data/ftb_lib/players/CON.dat"] = inventory[
        "world/data/ftb_lib/players/con.dat"
    ]
    with pytest.raises(ValueError):
        validate_inventory(inventory, path_policy="linux-server")
    with pytest.raises(ValueError):
        validate_inventory(files(), path_policy="unreviewed")


@pytest.mark.parametrize("char", ["*", "?", "|", "<", ">", '"'])
def test_linux_policy_keeps_other_nonportable_character_guards(char):
    with pytest.raises(ValueError):
        validate_inventory(files("world/a" + char + "b"), path_policy="linux-server")


def test_linux_policy_rejects_a_zip_symlink_even_with_reserved_basename(tmp_path):
    inventory = files()
    path = tmp_path / "linked.zip"
    with zipfile.ZipFile(path, "w") as file:
        file.writestr("world/level.dat", b"level")
        info = zipfile.ZipInfo("world/data/ftb_lib/players/con.dat")
        info.create_system = 3
        info.external_attr = 0o120777 << 16
        file.writestr(info, b"data")
    with pytest.raises(ValueError):
        verify_archive(path, inventory, path_policy="linux-server")


def test_insufficient_space_never_creates_a_world(tmp_path, monkeypatch):
    store, result, _archive, _inventory = make_store(tmp_path, reserved=False)
    target = tmp_path / "target"
    target.mkdir()
    req = request(result)
    monkeypatch.setattr(restore.sys, "platform", "linux")
    restore.execute({**req, "action": "initialize"}, store.root, target)
    monkeypatch.setattr(restore.shutil, "disk_usage", lambda _: SimpleNamespace(free=0))
    with pytest.raises(OSError):
        restore.execute({**req, "action": "stage"}, store.root, target)
    assert not (target / "world").exists() and not (target / restore.PLAN).exists()


def make_store(tmp_path, reserved=True):
    inventory = files() if reserved else files("world/normal.dat")
    archive = tmp_path / "input.zip"
    with zipfile.ZipFile(archive, "w") as file:
        for name in inventory:
            file.writestr(name, b"level" if name.endswith("level.dat") else b"data")
    store = BackupStore.create(tmp_path / "store", POLICY, path_policy="linux-server")
    result = store.publish(archive, inventory)
    return store, result, archive, inventory


def test_linux_zip_and_store_can_be_verified_opaquely_on_any_host(tmp_path):
    store, result, archive, inventory = make_store(tmp_path)
    verify_archive(archive, inventory, result["sha256"], path_policy="linux-server")
    with pytest.raises(ValueError):
        verify_archive(archive, inventory)
    assert store.readonly_snapshot(result["id"])[1]["files"] == inventory
    assert (
        json.loads((store.root / "owner.json").read_text())["path_policy"]
        == "linux-server"
    )
    with pytest.raises(ValueError):
        BackupStore(store.root, POLICY)
    portable = BackupStore.create(tmp_path / "portable", POLICY)
    with pytest.raises(ValueError):
        BackupStore(portable.root, POLICY, path_policy="linux-server")


def request(result):
    return {
        "operation": uuid4().hex,
        "world": "world",
        "snapshot": result["id"],
        "archive_sha256": result["sha256"],
        "policy": vars(POLICY),
        "world_max_bytes": 16 * 1024**2,
    }


def test_extraction_refuses_windows_before_initialization(tmp_path, monkeypatch):
    store, result, _archive, _inventory = make_store(tmp_path)
    target = tmp_path / "target"
    target.mkdir()
    req = {**request(result), "action": "initialize"}
    monkeypatch.setattr(restore.sys, "platform", "win32")
    with pytest.raises(ValueError, match="requires Linux"):
        restore.execute(req, store.root, target)
    assert not list(target.iterdir())


def test_real_linux_reserved_file_roundtrip_and_no_overwrite(tmp_path):
    if sys.platform != "linux":
        pytest.skip("Reserved file extraction requires real Linux")
    store, result, _archive, _inventory = make_store(tmp_path)
    target = tmp_path / "target"
    target.mkdir()
    req = request(result)
    restore.execute({**req, "action": "initialize"}, store.root, target)
    restore.execute({**req, "action": "stage"}, store.root, target)
    assert restore.execute({**req, "action": "verify"}, store.root, target)["verified"]
    assert (target / "world/data/ftb_lib/players/con.dat").read_bytes() == b"data"
    with pytest.raises(ValueError):
        restore.execute({**req, "action": "stage"}, store.root, target)
    (target / "world/data/ftb_lib/players/con.dat").write_bytes(b"other")
    with pytest.raises(ValueError):
        restore.execute({**req, "action": "verify"}, store.root, target)


def test_partial_stage_and_forged_receipt_cannot_authorize_start(tmp_path, monkeypatch):
    store, result, _archive, _inventory = make_store(tmp_path, reserved=False)
    target = tmp_path / "target"
    target.mkdir()
    req = request(result)
    monkeypatch.setattr(restore.sys, "platform", "linux")
    restore.execute({**req, "action": "initialize"}, store.root, target)
    original = restore._copy

    def partial(source, name, dest, expected):
        original(source, name, dest, expected)
        raise OSError("injected write failure")

    monkeypatch.setattr(restore, "_copy", partial)
    with pytest.raises(OSError):
        restore.execute({**req, "action": "stage"}, store.root, target)
    assert not (target / restore.DONE).exists()
    with pytest.raises(ValueError):
        restore.execute({**req, "action": "verify"}, store.root, target)
    with pytest.raises(ValueError):
        restore.execute({**req, "action": "stage"}, store.root, target)
    (target / restore.DONE).write_bytes((target / restore.PLAN).read_bytes())
    with pytest.raises(ValueError):
        restore.execute({**req, "action": "verify"}, store.root, target)
    assert store.inspect()[0]["id"] == result["id"]


@pytest.mark.parametrize("change", ["hash", "world", "owner", "snapshot"])
def test_wrong_bound_request_refuses_before_world_write(tmp_path, monkeypatch, change):
    store, result, _archive, _inventory = make_store(tmp_path, reserved=False)
    target = tmp_path / "target"
    target.mkdir()
    req = request(result)
    monkeypatch.setattr(restore.sys, "platform", "linux")
    restore.execute({**req, "action": "initialize"}, store.root, target)
    if change == "hash":
        req["archive_sha256"] = "a" * 64
    elif change == "world":
        req["world"] = "other"
    elif change == "owner":
        req["operation"] = uuid4().hex
    else:
        req["snapshot"] = "../escape"
    with pytest.raises(ValueError):
        restore.execute({**req, "action": "stage"}, store.root, target)
    assert not (target / "world").exists() and not (target / restore.PLAN).exists()
