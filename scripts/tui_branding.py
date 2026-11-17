"""Render the flat Mortum ore asset as terminal cells; never redraw the texture."""

import argparse
import hashlib
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "tui/assets/mortum-ore.png"
OUTPUT = ROOT / "tui/src/ore_pixels.rs"


def generated():
    rows = [
        "// Generated from the unmodified flat Mortum ore texture; see tui/assets/provenance.json.",
        "// SHA256: " + hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
    ]
    with Image.open(SOURCE) as image:
        for name, width, height in (("ORE", 16, 16), ("ORE_LARGE", 32, 32)):
            pixels = image.convert("RGBA").resize(
                (width, height), Image.Resampling.NEAREST
            )
            rows.append(f"pub const {name}: [[u8; 4]; {width * height}] = [")
            for y in range(height):
                for x in range(width):
                    r, g, b, a = pixels.getpixel((x, y))
                    rows.append(f"    [{r}, {g}, {b}, {a}],")
            rows.append("];")
    return "\n".join([*rows, ""])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    content = generated()
    if args.check:
        if OUTPUT.read_text(encoding="utf-8") != content:
            raise SystemExit(
                "TUI ore differs from the flat source texture; run scripts/tui_branding.py"
            )
    else:
        OUTPUT.write_text(content, encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
