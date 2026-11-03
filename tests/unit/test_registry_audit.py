import gzip
import hashlib
import json
from types import SimpleNamespace

import pytest

from launcher.nbt import MAX_BYTES, Tag, write_nbt
from omk.cli import main
from omk.registry_audit import CRITICAL, audit_registry_files, read_registries


def fixture(tmp_path, name, *, change=None):
    groups = {
        key: Tag(
            10,
            {
                "ids": Tag(
                    9,
                    (
                        10,
                        [Tag(10, {"K": Tag(8, "test:kept"), "V": Tag(3, 1)})],
                    ),
                )
            },
        )
        for key in CRITICAL | {"test:registry:legacy"}
    }
    if change:
        change(groups)
    path = tmp_path / name
    path.write_bytes(
        gzip.compress(write_nbt("", {"FML": Tag(10, {"Registries": Tag(10, groups)})}))
    )
    return path


def audit(source, target):
    return audit_registry_files(SimpleNamespace(source=source, target=target))


def test_numeric_remapping_and_new_names_are_not_missing_items(tmp_path):
    source = fixture(tmp_path, "old.dat")

    def change(groups):
        entries = groups["minecraft:items"].value["ids"].value[1]
        entries[0].value["V"] = Tag(3, 77)
        entries.append(Tag(10, {"K": Tag(8, "test:new"), "V": Tag(3, 1)}))

    target = fixture(tmp_path, "new.dat", change=change)
    original = source.read_bytes(), target.read_bytes()
    result = audit(source, target)
    assert result["ok"] and result["read_only"]
    assert not result["upgrade_accepted"]
    assert not result["requires_registry_review"]
    items = result["registries"]["minecraft:items"]
    assert items["numeric_id_changes"] == 1
    assert items["added"]["names"] == ["test:new"]
    assert "test:registry:legacy" in result["registries"]
    assert original == (source.read_bytes(), target.read_bytes())
    assert result["sha256"]["source"] == hashlib.sha256(original[0]).hexdigest()


def test_removals_and_output_truncation_require_review(tmp_path):
    def many(groups):
        groups["minecraft:items"].value["ids"] = Tag(
            9,
            (
                10,
                [
                    Tag(10, {"K": Tag(8, f"test:item{n:03}"), "V": Tag(3, n)})
                    for n in range(150)
                ],
            ),
        )

    source = fixture(tmp_path, "old.dat", change=many)
    target = fixture(tmp_path, "new.dat")
    result = audit(source, target)
    assert not result["ok"] and result["requires_registry_review"]
    assert not result["upgrade_accepted"]
    removed = result["registries"]["minecraft:items"]["removed"]
    assert removed["count"] == 150 and removed["truncated"]
    assert len(removed["names"]) == 100


def test_removed_empty_registry_is_still_reported(tmp_path):
    def before(groups):
        groups["test:empty"] = Tag(10, {"ids": Tag(9, (0, []))})

    result = audit(
        fixture(tmp_path, "old.dat", change=before), fixture(tmp_path, "new.dat")
    )
    assert result["requires_registry_review"]
    assert not result["registries"]["test:empty"]["target_present"]


def test_legacy_biome_spaces_are_preserved_exactly(tmp_path):
    def legacy(groups):
        groups["minecraft:biomes"].value["ids"].value[1][0].value["K"] = Tag(
            8, "galacticraftcore:outer space"
        )

    source = fixture(tmp_path, "old.dat", change=legacy)
    target = fixture(tmp_path, "new.dat")
    result = audit(source, target)
    assert result["registries"]["minecraft:biomes"]["removed"]["names"] == [
        "galacticraftcore:outer space"
    ]


@pytest.mark.parametrize(
    "mutation",
    [
        lambda g: g.pop("minecraft:blocks"),
        lambda g: g.update({"bad\nname:ids": g["minecraft:items"]}),
        lambda g: g["minecraft:items"].value.update({"ids": Tag(9, (8, []))}),
        lambda g: g["minecraft:items"]
        .value["ids"]
        .value[1]
        .append(Tag(10, {"K": Tag(8, "test:kept"), "V": Tag(3, 2)})),
        lambda g: g["minecraft:items"]
        .value["ids"]
        .value[1]
        .append(Tag(10, {"K": Tag(8, "test:other"), "V": Tag(3, 1)})),
        lambda g: g["minecraft:items"]
        .value["ids"]
        .value[1][0]
        .value.update({"V": Tag(3, -1)}),
        lambda g: g["minecraft:items"]
        .value["ids"]
        .value[1][0]
        .value.update({"V": Tag(8, "1")}),
    ],
)
def test_malformed_registry_is_not_a_clean_diff(tmp_path, mutation):
    source = fixture(tmp_path, "old.dat")
    bad = fixture(tmp_path, "bad.dat", change=mutation)
    result = audit(source, bad)
    assert not result["ok"] and not result["upgrade_accepted"]
    assert result["error"] == "Unreadable or invalid Forge registry input"


@pytest.mark.parametrize(
    "raw", [b"not-gzip", b"\x1f\x8b\x08", gzip.compress(b"bad-nbt")]
)
def test_corruption_returns_safe_error(tmp_path, raw):
    source = fixture(tmp_path, "old.dat")
    bad = tmp_path / "bad.dat"
    bad.write_bytes(raw)
    assert "error" in audit(source, bad)


def test_bounded_compressed_and_expanded_input(tmp_path):
    source = fixture(tmp_path, "old.dat")
    bad = tmp_path / "bad.dat"
    for raw in (b"x" * (MAX_BYTES + 1), gzip.compress(b"x" * (MAX_BYTES + 1))):
        bad.write_bytes(raw)
        assert "error" in audit(source, bad)
    bad.write_bytes(source.read_bytes()[:-4])
    assert "error" in audit(source, bad)
    corrupt = bytearray(source.read_bytes())
    corrupt[10] = 0xFF
    bad.write_bytes(corrupt)
    assert "error" in audit(source, bad)


def test_links_and_parent_links_are_rejected(tmp_path):
    folder = tmp_path / "real"
    folder.mkdir()
    source = fixture(folder, "level.dat")
    link = tmp_path / "link"
    try:
        link.symlink_to(folder, target_is_directory=True)
    except OSError:
        pytest.skip("Symlinks unavailable on this host")
    assert "error" in audit(source, link / "level.dat")
    leaf = tmp_path / "file-link.dat"
    leaf.symlink_to(source)
    assert "error" in audit(source, leaf)


def test_cli_reports_failure_without_writing_worlds(tmp_path, capsys):
    source = fixture(tmp_path, "old.dat")
    target = fixture(
        tmp_path,
        "new.dat",
        change=lambda g: g["minecraft:items"].value.update({"ids": Tag(9, (0, []))}),
    )
    assert (
        main(
            [
                "upgrade",
                "registry-audit",
                "--source",
                str(source),
                "--target",
                str(target),
            ]
        )
        == 1
    )
    result = json.loads(capsys.readouterr().out)
    assert result["requires_registry_review"]
    assert not result["upgrade_accepted"]
    assert len(list(tmp_path.iterdir())) == 2
    assert read_registries(source)["registries"]["minecraft:items"] == {"test:kept": 1}
