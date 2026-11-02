from PIL import Image

from scripts.build_launcher import packaging_icon


def test_rectangular_icon_is_padded_without_stretching_or_changing_rgba(tmp_path):
    source = tmp_path / "original.png"
    original = Image.new("RGBA", (114, 126), (32, 64, 96, 127))
    original.putpixel((113, 125), (100, 110, 120, 255))
    original.save(source)
    source_bytes = source.read_bytes()
    output = packaging_icon(source, tmp_path)
    with Image.open(output) as padded:
        assert padded.size == (128, 128)
        assert padded.crop((7, 1, 121, 127)).tobytes() == original.tobytes()
        assert padded.getpixel((0, 0))[3] == 0
        assert padded.getpixel((127, 127))[3] == 0
    assert source.read_bytes() == source_bytes
