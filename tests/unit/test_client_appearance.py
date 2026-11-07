"""Appearance staging must never overwrite an installed client or its inputs."""

import hashlib
import io
import json
import zipfile

import pytest
from PIL import Image

from scripts import build_client_appearance as appearance
from scripts.build_client_appearance import build


def test_existing_output_is_refused_without_touching_player_settings(tmp_path):
    instance = tmp_path / "instance"
    instance.mkdir()
    settings = instance / "options.txt"
    settings.write_bytes(b"guiScale:2\n")
    with pytest.raises(FileExistsError):
        build(instance, "2.23.4")
    assert list(instance.iterdir()) == [settings]
    assert settings.read_bytes() == b"guiScale:2\n"


@pytest.mark.parametrize("version", ["../../instance", "2.23.4\nother=value", "latest"])
def test_invalid_version_is_rejected_before_creating_output(tmp_path, version):
    output = tmp_path / "new"
    with pytest.raises(ValueError):
        build(output, version)
    assert not output.exists()


def test_overlay_is_self_contained_and_preserves_legacy_input(tmp_path):
    legacy = tmp_path / "legacy"
    legacy.mkdir()
    source = legacy / "background_1.png"
    Image.new("RGB", (640, 360), "#77aadd").save(source)
    original = source.read_bytes()
    output = build(tmp_path / "review", "2.23.4", legacy)
    menu = json.loads(
        (output / "config/CustomMainMenu/mainmenu.json").read_text(encoding="utf-8")
    )
    background = menu["other"]["background"]
    locations = [background["image"], *background["slideshow"]["images"]]
    locations += [item["image"] for item in menu["images"].values()]
    locations += [item["texture"] for item in menu["buttons"].values()]
    for location in locations:
        domain, name = location.split(":")
        with Image.open(output / "resources" / domain / name) as image:
            image.verify()
    receipt = json.loads(
        (output / "appearance-review.json").read_text(encoding="utf-8")
    )
    for record in receipt["files"]:
        assert (
            hashlib.sha256((output / record["path"]).read_bytes()).hexdigest()
            == record["sha256"]
        )
    assert source.read_bytes() == original
    assert receipt["ready_for_distribution"] is False
    assert not list(output.rglob("*.jar"))


def test_disable_featured_server_preserves_other_modpack_settings(tmp_path):
    source = tmp_path / "modpack.cfg"
    original = """customization {
    B:custom=true
}
default_server {
    B:"[01] Enable Default Server"=true
    S:"[02] Server IP"=example.invalid
    S:"[02] Server Name"=Featured
    S:unrelated=preserved
}
"""
    source.write_text(original, encoding="utf-8")
    output = build(tmp_path / "review", "2.23.4", modpack_config=source)
    result = (output / "config/endermodpacktweaks/modpack.cfg").read_text(
        encoding="utf-8"
    )
    assert 'B:"[01] Enable Default Server"=false' in result
    assert 'S:"[02] Server IP"=\n' in result
    assert 'S:"[02] Server Name"=\n' in result
    assert "B:custom=true" in result and "S:unrelated=preserved" in result
    assert 'B:"[01] Enable Window Customization"=true' in result
    assert 'B:"[04] Replace window icon"=true' in result
    assert "en_us;OmkalityCraft · Divine Journey 2 · 2.23.4" in result
    assert "ru_ru;OmkalityCraft · Divine Journey 2 · 2.23.4" in result
    with Image.open(output / "config/endermodpacktweaks/icon.png") as icon:
        assert icon.width == icon.height and icon.mode == "RGBA"
    assert source.read_text(encoding="utf-8") == original


def test_loading_numbers_remain_readable_on_every_bar_fill(tmp_path):
    output = build(tmp_path / "review", "2.23.4")
    properties = dict(
        line.split("=", 1)
        for line in (output / "config/splash.properties").read_text().splitlines()
        if "=" in line
    )

    def luminance(value):
        color = int(value, 16)
        channels = [(color >> shift & 255) / 255 for shift in (16, 8, 0)]
        linear = [
            n / 12.92 if n <= 0.04045 else ((n + 0.055) / 1.055) ** 2.4
            for n in channels
        ]
        return sum(
            n * weight
            for n, weight in zip(linear, (0.2126, 0.7152, 0.0722), strict=True)
        )

    foreground = luminance(properties["font"])
    for key in (
        "background",
        "barBackground",
        "bar",
        "memoryGood",
        "memoryWarn",
        "memoryLow",
    ):
        background = luminance(properties[key])
        ratio = (max(foreground, background) + 0.05) / (
            min(foreground, background) + 0.05
        )
        assert ratio >= 4.5, (key, ratio)


def test_vanilla_menu_staging_refuses_an_unreviewed_client(tmp_path):
    source = tmp_path / "unreviewed.jar"
    source.write_bytes(b"not the pinned Minecraft artifact")
    with pytest.raises(ValueError, match="Unreviewed"):
        appearance._vanilla_screens(source, tmp_path / "overlay")
    assert not (tmp_path / "overlay").exists()


def test_vanilla_menu_atlas_preserves_every_pixel_outside_buttons(
    tmp_path, monkeypatch
):
    original = Image.new("RGBA", (256, 256), (90, 120, 180, 255))
    original.putpixel((8, 8), (220, 50, 60, 128))
    png = io.BytesIO()
    original.save(png, "PNG")
    source = tmp_path / "fixture.jar"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("assets/minecraft/textures/gui/widgets.png", png.getvalue())
    original_bytes = source.read_bytes()
    monkeypatch.setattr(
        appearance, "MINECRAFT_SHA256", hashlib.sha256(original_bytes).hexdigest()
    )
    output = tmp_path / "overlay"
    appearance._vanilla_screens(source, output)
    with Image.open(output / "resources/minecraft/textures/gui/widgets.png") as styled:
        assert styled.size == original.size
        changed = 0
        for y in range(256):
            for x in range(256):
                if original.getpixel((x, y)) != styled.getpixel((x, y)):
                    assert x < 200 and 46 <= y < 106
                    changed += 1
        assert changed > 0
    assert source.read_bytes() == original_bytes
