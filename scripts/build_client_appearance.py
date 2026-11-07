"""Build a review-only Forge 1.12.2 appearance overlay in a NEW directory.

Never applies to an installed pack or edits a manifest. Generated textures use
the bundled project icon/fonts; optional legacy screenshots stay outside Git.
"""

import argparse
import hashlib
import io
import json
import re
import zipfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "launcher/assets"
BACKGROUND, SURFACE, BORDER, ICE = "#0b0d10", "#12161b", "#303842", "#dbe7f2"
MINECRAFT_SHA256 = "8ada07da5ee77dad3527bd7278fbd05ee1fc8a597813b216a871a2d7d64cc64f"


def _vanilla_screens(source: Path, output: Path) -> None:
    if hashlib.sha256(source.read_bytes()).hexdigest() != MINECRAFT_SHA256:
        raise ValueError("Unreviewed Minecraft client texture input")
    with zipfile.ZipFile(source) as archive:
        raw = archive.read("assets/minecraft/textures/gui/widgets.png")
    with Image.open(io.BytesIO(raw)) as opened:
        image = opened.convert("RGBA")
    if image.size != (256, 256):
        raise ValueError("Unexpected Minecraft widget atlas dimensions")
    painter = ImageDraw.Draw(image)
    for state, fill, border in (
        (0, "#15191f", "#252d37"),
        (1, "#1b2128", "#4b5968"),
        (2, "#344658", ICE),
    ):
        y = 46 + state * 20
        painter.rectangle((0, y, 199, y + 19), fill=(0, 0, 0, 0))
        painter.rounded_rectangle(
            (0, y, 199, y + 19), radius=4, fill=fill, outline=border
        )
    destination = output / "resources/minecraft/textures/gui"
    destination.mkdir(parents=True)
    image.save(destination / "widgets.png")
    # Vanilla dims this tile to 25%; the resulting background is obsidian.
    tile = Image.new("RGB", (64, 64), "#343c48")
    painter = ImageDraw.Draw(tile)
    for y in range(0, 64, 8):
        for x in range(0, 64, 8):
            if (x + y) % 16 == 0:
                painter.rectangle((x, y, x + 7, y + 7), fill="#303844")
    tile.save(destination / "options_background.png")


def _brand(size: tuple[int, int]) -> Image.Image:
    image = Image.new("RGBA", size)
    font = ImageFont.truetype(str(ASSETS / "fonts/Rubik.ttf"), 39)
    ImageDraw.Draw(image).text(
        (size[0] // 2, size[1] // 2), "OMKALITYCRAFT", font=font, fill=ICE, anchor="mm"
    )
    return image


def _loading_logo() -> Image.Image:
    image = Image.new("RGBA", (512, 512))
    icon = Image.open(ASSETS / "branding/icon.png").convert("RGBA")
    icon.thumbnail((100, 100), Image.Resampling.NEAREST)
    image.alpha_composite(icon, ((512 - icon.width) // 2, 112))
    font = ImageFont.truetype(str(ASSETS / "fonts/Rubik.ttf"), 32)
    ImageDraw.Draw(image).text(
        (256, 248), "OMKALITYCRAFT", font=font, fill=ICE, anchor="mm"
    )
    return image


def _buttons(path: Path, *, primary: bool) -> None:
    # CMM samples the top half normally and the bottom half on hover.
    image = Image.new("RGBA", (880, 224))
    painter = ImageDraw.Draw(image)
    for y, fill, border in (
        (0, ICE if primary else SURFACE, ICE if primary else BORDER),
        (112, "#f2f7fc" if primary else "#28313b", "#f2f7fc" if primary else "#647485"),
    ):
        painter.rounded_rectangle(
            (0, y, 879, y + 111), radius=24, fill=fill, outline=border, width=3
        )
    image.save(path)


def _backgrounds(
    destination: Path, legacy: Path | None
) -> tuple[list[str], list[dict]]:
    sources = sorted(legacy.glob("background_*.png")) if legacy else []
    if legacy is not None and (not sources or len(sources) > 12):
        raise ValueError("Expected 1-12 explicit legacy background PNGs")
    records, resources = [], []
    for i, source in enumerate(sources):
        with Image.open(source) as opened:
            if opened.width * opened.height > 16_000_000:
                raise ValueError("Legacy background is too large")
            # Keep the original resolution and pixels in the input archive.
            gray = ImageOps.grayscale(opened)
            tinted = ImageOps.colorize(gray, BACKGROUND, "#495869")
        name = f"background-{i}.png"
        tinted.save(destination / name)
        resources.append(f"omk:appearance/{name}")
        records.append(
            {
                "file": source.name,
                "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            }
        )
    if not resources:
        image = Image.new("RGB", (1920, 1080), BACKGROUND)
        painter = ImageDraw.Draw(image)
        for y in range(1080):
            n = int(10 * (1 - y / 1080))
            painter.line((0, y, 1920, y), fill=(11 + n, 13 + n, 16 + n * 2))
        image.save(destination / "background-0.png")
        resources.append("omk:appearance/background-0.png")
    return resources, records


def _menu(pack: str, version: str, backgrounds: list[str]) -> dict:
    buttons = {}
    for index, (name, text) in enumerate(
        (
            ("multiplayer", "Сетевая игра"),
            ("singleplayer", "Одиночная игра"),
            ("options", "Настройки"),
            ("mods", "Моды"),
            ("quit", "Выйти из игры"),
        )
    ):
        primary = index == 0
        buttons[name] = {
            "text": text,
            "posX": -110,
            "posY": -40 + index * 27,
            "width": 220,
            "height": 23,
            "alignment": "center",
            "texture": "omk:appearance/" + ("primary.png" if primary else "button.png"),
            "imageWidth": 880,
            "imageHeight": 112,
            "shadow": False,
            "normalTextColor": int("141b23" if primary else "dbe7f2", 16),
            "hoverTextColor": int("141b23" if primary else "edf2f7", 16),
            "action": (
                {"type": "quit"} if name == "quit" else {"type": "openGui", "gui": name}
            ),
        }
    labels = {}
    for name, text, y, color in (
        ("pack", f"{pack} · {version}", -54, "dbe7f2"),
        (
            "minecraft",
            "Minecraft #mcversion# · Forge · #modsloaded# модов",
            -26,
            "9ba7b5",
        ),
        (
            "credits",
            "DJ2: AtricosHU и команда · © Mojang AB",
            -14,
            "9ba7b5",
        ),
    ):
        labels[name] = {
            "text": text,
            "posX": 0,
            "posY": y,
            "alignment": "center" if name == "pack" else "bottom_center",
            "anchor": "middle",
            "color": int(color, 16),
            "hoverColor": int(color, 16),
        }
    return {
        "images": {
            "brand": {
                "image": "omk:appearance/brand.png",
                "posX": -140,
                "posY": -110,
                "width": 280,
                "height": 52,
                "alignment": "center",
            }
        },
        "buttons": buttons,
        "labels": labels,
        "other": {
            "background": {
                "image": backgrounds[0],
                "slideshow": {
                    "images": backgrounds,
                    "displayDuration": 300,
                    "fadeDuration": 40,
                    "shuffle": True,
                },
            }
        },
    }


def _window_customization(text: str, version: str) -> str:
    match = re.search(r"(customization\s*\{)(.*?)(\n\})", text, re.DOTALL)
    if match is None:
        raise ValueError("Missing Ender Modpack Tweaks customization section")
    section = match[2]
    for key, value in (
        ('B:"[01] Enable Window Customization"', "true"),
        ('B:"[02] Change window title"', "true"),
        ('B:"[04] Replace window icon"', "true"),
        ('S:"[05] Window icon path"', "config/endermodpacktweaks/icon.png"),
    ):
        pattern = r"(?m)^(\s*" + re.escape(key) + r"=)[^\r\n]*$"
        section, count = re.subn(pattern, lambda m, value=value: m[1] + value, section)
        if count == 0:
            section += f"\n    {key}={value}\n"
        elif count != 1:
            raise ValueError("Duplicate window customization property")
    title = f"OmkalityCraft · Divine Journey 2 · {version}"
    declaration = f'    S:"[03] Window title format" <\n        en_us;{title}\n        ru_ru;{title}\n     >'
    section, count = re.subn(
        r'(?ms)^\s*S:"\[03\] Window title format"\s*<.*?^\s*>',
        lambda m: "\n" + declaration,
        section,
    )
    if count == 0:
        section += "\n" + declaration + "\n"
    elif count != 1:
        raise ValueError("Duplicate window title declaration")
    return text[: match.start(2)] + section + text[match.end(2) :]


def _modpack_customization(source: Path, output: Path, version: str) -> None:
    text = source.read_text(encoding="utf-8")
    pattern = r"(default_server\s*\{)(.*?)(\n\})"
    match = re.search(pattern, text, re.DOTALL)
    if match is None:
        raise ValueError("Missing Ender Modpack Tweaks default_server section")
    section = match[2]
    for key, value in (
        ('B:"[01] Enable Default Server"', "false"),
        ('S:"[02] Server IP"', ""),
        ('S:"[02] Server Name"', ""),
    ):
        section, count = re.subn(
            r"(?m)^(\s*" + re.escape(key) + r"=)[^\r\n]*$",
            lambda m, value=value: m[1] + value,
            section,
        )
        if count != 1:
            raise ValueError("Unexpected Ender Modpack Tweaks server configuration")
    destination = output / "config/endermodpacktweaks/modpack.cfg"
    destination.parent.mkdir(parents=True)
    text = text[: match.start(2)] + section + text[match.end(2) :]
    destination.write_text(_window_customization(text, version), encoding="utf-8")
    with Image.open(ASSETS / "branding/icon.png") as opened:
        icon = opened.convert("RGBA")
    edge = max(128, *icon.size)
    canvas = Image.new("RGBA", (edge, edge))
    canvas.alpha_composite(icon, ((edge - icon.width) // 2, (edge - icon.height) // 2))
    canvas.save(destination.parent / "icon.png")


def build(
    output: Path,
    version: str,
    legacy: Path | None = None,
    modpack_config: Path | None = None,
    minecraft_jar: Path | None = None,
) -> Path:
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise ValueError("Expected a DJ2 release version")
    output = output.resolve()
    # Never merge or replace files of an existing player instance.
    output.mkdir(parents=True, exist_ok=False)
    resources = output / "resources/omk/appearance"
    resources.mkdir(parents=True)
    backgrounds, inputs = _backgrounds(resources, legacy)
    _brand((640, 120)).save(resources / "brand.png")
    _loading_logo().save(resources / "loading.png")
    _buttons(resources / "primary.png", primary=True)
    _buttons(resources / "button.png", primary=False)
    menu = output / "config/CustomMainMenu/mainmenu.json"
    menu.parent.mkdir(parents=True)
    menu.write_text(
        json.dumps(
            _menu("Divine Journey 2", version, backgrounds),
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    # Keep Forge's renderer, progress tracking, font and fallback. The optional
    # private client adapter selects the central logo and removes its dark tint.
    (output / "config/splash.properties").write_text(
        "# OmkalityCraft obsidian / ice gray; Forge 14.23.5.2860\n"
        "enabled=true\nrotate=false\nshowMemory=true\nlogoOffset=12\n"
        "background=0x0B0D10\nfont=0xEDF2F7\nbar=0x46596B\n"
        "barBackground=0x1B2128\nbarBorder=0x303842\n"
        "memoryGood=0x304D47\nmemoryWarn=0x5E4B2C\nmemoryLow=0x632F32\n"
        "resourcePackPath=resources\nforgeTexture=fml:textures/gui/forge.png\n"
        "fontTexture=textures/font/ascii.png\n",
        encoding="utf-8",
    )
    if modpack_config is not None:
        _modpack_customization(modpack_config, output, version)
    if minecraft_jar is not None:
        _vanilla_screens(minecraft_jar, output)
    files = [
        {
            "path": p.relative_to(output).as_posix(),
            "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
        }
        for p in sorted(output.rglob("*"))
        if p.is_file()
    ]
    (output / "appearance-review.json").write_text(
        json.dumps(
            {
                "schema": 1,
                "review_only": True,
                "ready_for_distribution": False,
                "minecraft": "1.12.2",
                "forge": "14.23.5.2860",
                "pack_version": version,
                "custom_main_menu": "2.0.9.1",
                "resource_loader": "1.5.3",
                "loading_logo_requires_private_client_adapter": True,
                "jvm_args_required": ["-Domkality.appearance.forge112=true"],
                "featured_server_disabled": modpack_config is not None,
                "vanilla_screens_themed": minecraft_jar is not None,
                "minecraft_texture_source_sha256": (
                    MINECRAFT_SHA256 if minecraft_jar is not None else None
                ),
                "legacy_background_inputs": inputs,
                "branding_input": json.loads(
                    (ASSETS / "branding/provenance.json").read_text(encoding="utf-8")
                ),
                "font_input": json.loads(
                    (ASSETS / "fonts/provenance.json").read_text(encoding="utf-8")
                ),
                "files": files,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--pack-version", required=True)
    parser.add_argument("--legacy-backgrounds", type=Path)
    parser.add_argument(
        "--modpack-config",
        type=Path,
        help="Explicit source Ender Modpack Tweaks config; disable its featured server",
    )
    parser.add_argument(
        "--minecraft-jar",
        type=Path,
        help="Pinned 1.12.2 client JAR; theme vanilla menus without changing HUD atlas regions",
    )
    args = parser.parse_args()
    print(
        build(
            args.output,
            args.pack_version,
            args.legacy_backgrounds,
            args.modpack_config,
            args.minecraft_jar,
        )
    )


if __name__ == "__main__":
    main()
