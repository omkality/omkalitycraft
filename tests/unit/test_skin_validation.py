import io

import pytest
from PIL import Image, PngImagePlugin

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
