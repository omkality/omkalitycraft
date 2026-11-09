"""Check cosmetic Mixin targets against the pinned Forge class files before ECJ."""

import io
import re
import zipfile
from pathlib import Path


def methods(data):
    stream = io.BytesIO(data)
    if stream.read(4) != b"\xca\xfe\xba\xbe":
        raise ValueError("Invalid Java class")
    stream.read(4)

    def number(size):
        raw = stream.read(size)
        if len(raw) != size:
            raise ValueError("Truncated Java class")
        return int.from_bytes(raw, "big")

    pool, count, index = {}, number(2), 1
    while index < count:
        tag = number(1)
        if tag == 1:
            pool[index] = stream.read(number(2)).decode("utf-8", errors="replace")
        elif tag in {3, 4, 9, 10, 11, 12, 17, 18}:
            stream.read(4)
        elif tag in {5, 6}:
            stream.read(8)
            index += 1
        elif tag in {7, 8, 16, 19, 20}:
            stream.read(2)
        elif tag == 15:
            stream.read(3)
        else:
            raise ValueError("Unsupported Java constant")
        index += 1
    stream.read(6)
    stream.read(number(2) * 2)

    def members():
        found = set()
        for _ in range(number(2)):
            number(2)
            name, descriptor = number(2), number(2)
            found.add(pool[name] + pool[descriptor])
            for _ in range(number(2)):
                number(2)
                stream.read(number(4))
        return found

    members()  # Fields have the same framing, but are not method targets.
    return members(), pool.values()


def verify(forge: Path, sources: Path | None = None):
    sources = sources or Path(__file__).parent / "src/net/omkality/client/mixin"
    expected = {
        "ForgeSplashLogoMixin.java": {"start()V"},
        "ForgeSplashTintMixin.java": {"run()V", "setColor(I)V"},
    }
    with zipfile.ZipFile(forge) as archive:
        for filename, required in expected.items():
            source = (sources / filename).read_text(encoding="utf-8")
            match = re.search(r'@Mixin\(targets="([^"]+)"', source)
            if match is None:
                raise ValueError("Missing cosmetic Mixin target")
            found, constants = methods(
                archive.read(match[1].replace(".", "/") + ".class")
            )
            if not required <= found:
                raise ValueError(
                    "Cosmetic Mixin methods do not match pinned Forge: " + filename
                )
            if (
                filename == "ForgeSplashLogoMixin.java"
                and "textures/gui/title/mojang.png" not in constants
            ):
                raise ValueError("Missing reviewed splash logo resource constant")
    return len(expected)
