import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_guide_color_profile_is_shared_and_preserves_the_accepted_plain_text():
    server = ROOT / "profiles/server-defaults/dj2/omkalitycore-welcome.properties"
    client = ROOT / (
        "mods/forge-1.12.2/client/resources/assets/omkalityclient/"
        "guides/dj2-2.23.4.properties"
    )
    raw = server.read_bytes()
    assert raw == client.read_bytes() and len(raw) < 16384
    text = raw.decode("utf-8")
    fields = dict(line.split("=", 1) for line in text.splitlines())
    assert fields.pop("schema") == "1"
    plain = [
        re.sub("§[0-9a-fk-or]", "", value, flags=re.I) for value in fields.values()
    ]
    assert list(fields) == [f"line.{i}" for i in range(1, 7)]
    assert plain == [
        "OmkalityCraft · Короткая памятка",
        "/sethome <имя> — сохранить дом; /home <имя> — вернуться домой.",
        "/spawn — спавн; /resource — ресурсный мир.",
        "/rtp — случайная точка в текущем мире, если RTP здесь разрешён.",
        "На игрока: 3 дома и 50 чанков привата. Приваты — через карту FTB.",
        "/guide — показать эту памятку снова.",
    ]
    assert set(re.findall("§(.)", text)) == {"3", "7", "8", "f"}
    assert all(len(value.encode("utf-16-le")) // 2 <= 240 for value in fields.values())
