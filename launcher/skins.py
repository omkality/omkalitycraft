"""Bounded PNG decoding and an explicit distinction between format and arm model."""

import io
import struct
import warnings
from dataclasses import dataclass

from PIL import Image, UnidentifiedImageError

MAX_SKIN_BYTES = 256 * 1024


class SkinError(ValueError):
    pass


@dataclass(frozen=True)
class Skin:
    png: bytes
    width: int
    height: int
    model: str

    @property
    def legacy(self) -> bool:
        return self.height == 32


def _suggest_model(rgba: Image.Image) -> str:
    if rgba.height == 32:
        return "classic"
    # PNG has no authoritative model field. These unused Slim UV strips
    # provide a suggestion; the upload preview can override it.
    alpha = rgba.getchannel("A")
    unused = ((50, 16, 52, 20), (54, 20, 56, 32), (42, 48, 44, 52), (46, 52, 48, 64))
    return (
        "slim"
        if all(alpha.crop(rect).getextrema()[1] == 0 for rect in unused)
        else "classic"
    )


def decode_skin(data: bytes, model: str | None = None) -> Skin:
    if len(data) > MAX_SKIN_BYTES:
        raise SkinError("Скин слишком большой. Максимальный размер — 256 КБ.")
    if len(data) < 33 or data[:8] != b"\x89PNG\r\n\x1a\n" or data[12:16] != b"IHDR":
        raise SkinError("Выберите PNG-скин, а не архив или другое изображение.")
    width, height = struct.unpack(">II", data[16:24])
    if (width, height) not in {(64, 32), (64, 64)}:
        raise SkinError("Поддерживаются скины 64×64 и старые скины 64×32.")
    if model not in {None, "classic", "slim"}:
        raise SkinError("Неизвестная модель скина.")
    if height == 32 and model == "slim":
        raise SkinError("Скин 64×32 поддерживает только стандартную модель.")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data), formats=["PNG"]) as image:
                if getattr(image, "n_frames", 1) != 1:
                    raise SkinError("Анимированный PNG не подходит для скина.")
                image.verify()
            with Image.open(io.BytesIO(data), formats=["PNG"]) as image:
                rgba = image.convert("RGBA")
                rgba.load()
                if rgba.getchannel("A").getextrema()[1] == 0:
                    raise SkinError("Скин полностью прозрачный.")
                model = model or _suggest_model(rgba)
                # Re-encode pixels only: discard comments, profiles and ancillary data.
                clean = io.BytesIO()
                rgba.save(clean, format="PNG")
    except SkinError:
        raise
    except (
        OSError,
        ValueError,
        SyntaxError,
        UnidentifiedImageError,
        Image.DecompressionBombWarning,
    ):
        raise SkinError(
            "PNG повреждён или не может быть прочитан. Попробуйте другой файл."
        ) from None
    return Skin(clean.getvalue(), width, height, model)
