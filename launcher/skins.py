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


def decode_skin(data: bytes, model: str = "classic") -> Skin:
    if len(data) > MAX_SKIN_BYTES:
        raise SkinError("Скин слишком большой. Максимальный размер — 256 КБ.")
    if len(data) < 33 or data[:8] != b"\x89PNG\r\n\x1a\n" or data[12:16] != b"IHDR":
        raise SkinError("Выберите PNG-скин, а не архив или другое изображение.")
    width, height = struct.unpack(">II", data[16:24])
    if (width, height) not in {(64, 32), (64, 64)}:
        raise SkinError("Поддерживаются скины 64×64 и старые скины 64×32.")
    if model not in {"classic", "slim"}:
        raise SkinError("Выберите модель Steve или Alex.")
    if height == 32 and model == "slim":
        raise SkinError(
            "Скин 64×32 использует модель Steve. Для Alex нужен формат 64×64."
        )
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
