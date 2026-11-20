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
        pixels = image.convert("RGBA").resize((16, 16), Image.Resampling.NEAREST)
        rows.append("pub const ORE: [[u8; 4]; 256] = [")
        for r, g, b, a in pixels.get_flattened_data():
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
