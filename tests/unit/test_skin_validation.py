import hashlib
import io
import json

import pytest
from PIL import Image, PngImagePlugin

from launcher.skin_defaults import SKIN_ASSETS
from launcher.skins import MAX_SKIN_BYTES, SkinError, decode_skin
from omk.lab import skin_fixture


def png(size=(64, 64), color=(100, 130, 200, 255), **kwargs):
    output = io.BytesIO()
    Image.new("RGBA", size, color).save(output, format="PNG", **kwargs)
    return output.getvalue()


@pytest.mark.parametrize(
    "value",
    [
        b"not a PNG",
        skin_fixture()[:40],
        png((128, 128)),
        png(color=(0, 0, 0, 0)),
        skin_fixture() + b"x" * MAX_SKIN_BYTES,
    ],
    ids=["wrong-type", "truncated", "dimensions", "transparent", "too-large"],
)
def test_invalid_skin_rejected(value):
    with pytest.raises(SkinError):
        decode_skin(value)


def test_legacy_skin_cannot_claim_slim_model():
    legacy = png((64, 32))
    assert decode_skin(legacy).legacy
    with pytest.raises(SkinError):
        decode_skin(legacy, "slim")


def test_skin_metadata_is_stripped():
    metadata = PngImagePlugin.PngInfo()
    metadata.add_text("comment", "private metadata")
    result = decode_skin(png(pnginfo=metadata), "slim")
    assert b"private metadata" not in result.png
    assert result.model == "slim"


def test_animated_png_rejected():
    stream = io.BytesIO()
    Image.new("RGBA", (64, 64), "red").save(
        stream,
        format="PNG",
        save_all=True,
        append_images=[Image.new("RGBA", (64, 64), "blue")],
        duration=100,
    )
    with pytest.raises(SkinError):
        decode_skin(stream.getvalue())


@pytest.mark.parametrize(
    "name,model,size",
    [
        ("default-slim.png", "slim", (64, 64)),
        ("default-classic.png", "classic", (64, 64)),
        ("default-legacy.png", "classic", (64, 32)),
    ],
)
def test_owner_provided_variants_detected_without_version_choice(name, model, size):
    skin = decode_skin((SKIN_ASSETS / name).read_bytes())
    assert skin.model == model
    assert (skin.width, skin.height) == size


def test_opaque_png_model_is_a_suggestion_and_can_be_corrected():
    # The same opaque PNG can be intended for either model; no detector can
    # infer missing account metadata with certainty.
    data = png()
    assert decode_skin(data).model == "classic"
    assert decode_skin(data, "slim").model == "slim"


def test_skin_provenance_pins_original_owner_files():
    manifest = json.loads((SKIN_ASSETS / "provenance.json").read_text())
    assert manifest["default"] == "default-slim.png"
    for entry in manifest["files"]:
        assert (
            hashlib.sha256((SKIN_ASSETS / entry["file"]).read_bytes()).hexdigest()
            == entry["sha256"]
        )
