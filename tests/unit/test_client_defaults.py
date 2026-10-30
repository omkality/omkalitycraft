import json
from dataclasses import replace
from pathlib import Path

import pytest

from launcher.client_defaults import prepare_client_defaults
from launcher.client_policy import ClientDefaults
from launcher.nbt import Tag, read_nbt, write_nbt
from launcher.releases import ReleaseError
from tests.unit.test_game_runner import fixture


def setup(tmp_path: Path):
    folder, release, _ = fixture(tmp_path)
    font = folder / "resourcepacks/FM_NewFont/pack.mcmeta"
    font.parent.mkdir(parents=True)
    font.write_text('{"pack":{"pack_format":3}}')
    defaults = {
        "required_resourcepacks": ["FM_NewFont"],
        "language": "ru_ru",
        "force_unicode_font": False,
        "servers": [{"id": "dj2", "name": "DJ2 тест", "address": "127.0.0.1:25576"}],
    }
    release = replace(release, launch={**release.launch, "client_defaults": defaults})
    return folder, release


def test_first_run_seeds_font_language_and_only_compatible_server(tmp_path: Path):
    folder, release = setup(tmp_path)
    prepare_client_defaults(release, folder)
    options = (folder / "options.txt").read_text()
    assert 'resourcePacks:["FM_NewFont"]' in options
    assert "forceUnicodeFont:false" in options
    assert "lang:ru_ru" in options
    root = read_nbt((folder / "servers.dat").read_bytes())[1]
    servers = root["servers"].value[1]
    assert len(servers) == 1 and servers[0].value["ip"].value == "127.0.0.1:25576"


def test_defaults_merge_without_resetting_player_options_or_other_servers(
    tmp_path: Path,
):
    folder, release = setup(tmp_path)
    original_options = b'lang:en_us\nrenderDistance:6\nsoundCategory_master:0.25\nresourcePacks:["MyPack"]\n'
    (folder / "options.txt").write_bytes(original_options)
    custom = Tag(
        10,
        {
            "name": Tag(8, "Мой сервер 🎮"),
            "ip": Tag(8, "example.org"),
            "modField": Tag(11, [1, -1]),
        },
    )
    (folder / "servers.dat").write_bytes(
        write_nbt("", {"servers": Tag(9, (10, [custom]))})
    )
    prepare_client_defaults(release, folder)
    prepare_client_defaults(release, folder)
    options = (folder / "options.txt").read_text()
    assert (
        "lang:en_us" in options
        and "renderDistance:6" in options
        and "soundCategory_master:0.25" in options
    )
    assert json.loads(
        next(
            line.split(":", 1)[1]
            for line in options.splitlines()
            if line.startswith("resourcePacks:")
        )
    ) == ["MyPack", "FM_NewFont"]
    servers = read_nbt((folder / "servers.dat").read_bytes())[1]["servers"].value[1]
    assert len(servers) == 2 and servers[1] == custom
    assert any(
        path.read_bytes() == original_options
        for path in (folder / ".omk-defaults-backups").glob("*options.txt")
    )


def test_managed_server_address_can_change_without_duplicate_entries(tmp_path: Path):
    folder, release = setup(tmp_path)
    prepare_client_defaults(release, folder)
    release.launch["client_defaults"]["servers"][0]["address"] = "localhost:25577"
    prepare_client_defaults(release, folder)
    servers = read_nbt((folder / "servers.dat").read_bytes())[1]["servers"].value[1]
    assert len(servers) == 1 and servers[0].value["ip"].value == "localhost:25577"


def test_corrupt_server_list_is_not_overwritten(tmp_path: Path):
    folder, release = setup(tmp_path)
    path = folder / "servers.dat"
    path.write_bytes(b"invalid NBT")
    with pytest.raises(ReleaseError):
        prepare_client_defaults(release, folder)
    assert path.read_bytes() == b"invalid NBT"


def test_journeymap_defaults_seed_once_and_preserve_player_changes(tmp_path: Path):
    folder, release = setup(tmp_path)
    profile = Path(__file__).resolve().parents[2] / "profiles/client-defaults/dj2.json"
    release.launch["client_defaults"]["initial_configs"] = json.loads(
        profile.read_text(encoding="utf-8")
    )["initial_configs"]
    prepare_client_defaults(release, folder)
    base = folder / "journeymap/config/5.7"
    minimap = base / "journeymap.minimap.config"
    settings = json.loads(minimap.read_text(encoding="utf-8"))
    assert settings["shape"] == "Square" and settings["showGrid"] == "false"
    assert settings["position"] == "TopRight"
    assert (
        json.loads((base / "journeymap.fullmap.config").read_text())["showGrid"]
        == "false"
    )
    personal = b'{"shape":"Circle","showGrid":"true"}'
    minimap.write_bytes(personal)
    prepare_client_defaults(release, folder)
    assert minimap.read_bytes() == personal


@pytest.mark.parametrize(
    "path",
    [
        "../outside.config",
        "journeymap/data/map.config",
        "config/executable.js",
        "journeymap/config/5.7/../../map.config",
    ],
)
def test_initial_configs_cannot_seed_maps_or_arbitrary_files(path):
    with pytest.raises(ValueError):
        ClientDefaults.parse(
            {"initial_configs": [{"path": path, "content": {"shape": "Square"}}]}
        )


def test_empty_java_server_list_and_managed_icon_are_preserved(tmp_path: Path):
    folder, release = setup(tmp_path)
    path = folder / "servers.dat"
    path.write_bytes(write_nbt("", {"servers": Tag(9, (0, []))}))
    prepare_client_defaults(release, folder)
    name, root = read_nbt(path.read_bytes())
    root["servers"].value[1][0].value["icon"] = Tag(8, "test-icon")
    path.write_bytes(write_nbt(name, root))
    prepare_client_defaults(release, folder)
    assert (
        read_nbt(path.read_bytes())[1]["servers"].value[1][0].value["icon"].value
        == "test-icon"
    )


@pytest.mark.parametrize(
    "address",
    [
        "https://server.example",
        "user:password@host",
        "host/../../outside",
        "host:0",
        "host:65536",
        "host\nother",
    ],
)
def test_invalid_default_server_addresses_rejected(address):
    with pytest.raises(ValueError):
        ClientDefaults.parse(
            {"servers": [{"id": "dj2", "name": "DJ2", "address": address}]}
        )


def test_nbt_roundtrip_preserves_modified_utf8_and_unknown_types():
    root = {
        "name": Tag(8, "Тест\0🎮"),
        "bytes": Tag(7, b"abc"),
        "float": Tag(5, 1.5),
        "double": Tag(6, 2.5),
        "short": Tag(2, -3),
        "longs": Tag(12, [1, 2**45]),
    }
    assert read_nbt(write_nbt("root", root)) == ("root", root)
    with pytest.raises(ValueError):
        read_nbt(b"\x0a\0\0\x09\0\x01x\x08\xff\xff\xff\xff")
