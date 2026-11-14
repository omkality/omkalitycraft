"""Check cosmetic Mixin targets against the pinned Forge class files before ECJ."""

import io
import json
import re
import zipfile
from pathlib import Path


def verify_book_resources(resources: Path) -> int:
    """Reject legacy pack fallback and accidentally inaccessible helper packages."""
    try:
        for relative in (
            "pack.mcmeta",
            "mixins.omkalityclient.books.json",
            "assets/omkalityclient/lang/en_us.lang",
            "assets/omkalityclient/lang/ru_ru.lang",
        ):
            if b"\r" in (resources / relative).read_bytes():
                raise ValueError("Client book resources require canonical LF bytes")
        metadata = json.loads((resources / "pack.mcmeta").read_bytes())
        if (
            type(metadata["pack"]["pack_format"]) is not int
            or metadata["pack"]["pack_format"] != 3
        ):
            raise ValueError("Client language resources require pack format 3")
        config = json.loads(
            (resources / "mixins.omkalityclient.books.json").read_bytes()
        )
        if config != {
            "required": True,
            "minVersion": "0.8.5",
            "package": "net.omkality.client.mixin.books",
            "compatibilityLevel": "JAVA_8",
            "client": ["ExtraUtilitiesBookLabelsMixin", "PatchouliEditionMixin"],
            "injectors": {"defaultRequire": 1},
        }:
            raise ValueError("Book mixins must have their own package")
        expected = {
            "en_us": (
                "Extra Utilities 2\\nManual\\n(temp GUI stand in)",
                "Table of Contents\\n\\n",
            ),
            "ru_ru": ("Extra Utilities 2\\nРуководство", "Оглавление\\n\\n"),
        }
        for locale, (cover, contents) in expected.items():
            path = resources / "assets/omkalityclient/lang" / (locale + ".lang")
            entries = [
                line.split("=", 1)
                for line in path.read_text(encoding="utf-8").splitlines()
                if line and not line.startswith("#")
            ]
            values = dict(entries)
            wanted = {
                "omkalityclient.books.locale": locale,
                "omkalityclient.books.xu2.cover": cover,
                "omkalityclient.books.xu2.contents": contents,
            }
            if len(entries) != len(values) or values != wanted:
                raise ValueError("Unexpected client book language labels")
    except (OSError, KeyError, TypeError, json.JSONDecodeError) as error:
        raise ValueError("Incomplete client book resource contract") from error
    return 4


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
