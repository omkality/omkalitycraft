"""Display the controls saved by a Forge 1.12 installation."""

from pathlib import Path

from launcher.files import local_file

MAX_OPTIONS_BYTES = 1024 * 1024

# LWJGL 2 identifies physical keys. Include both legends for the grave key.
KEYS = {
    **dict(enumerate("1234567890", 2)),
    **dict(enumerate("QWERTYUIOP", 16)),
    **dict(enumerate("ASDFGHJKL", 30)),
    **dict(enumerate("ZXCVBNM", 44)),
    **{code: f"F{code - 58}" for code in range(59, 69)},
    1: "Esc",
    12: "-",
    13: "=",
    14: "Backspace",
    15: "Tab",
    26: "[",
    27: "]",
    28: "Enter",
    29: "Левый Ctrl",
    39: ";",
    40: "'",
    41: "Ё / `",
    42: "Левый Shift",
    43: "\\",
    51: ",",
    52: ".",
    53: "/",
    54: "Правый Shift",
    55: "Num *",
    56: "Левый Alt",
    57: "Пробел",
    58: "Caps Lock",
    69: "Num Lock",
    70: "Scroll Lock",
    71: "Num 7",
    72: "Num 8",
    73: "Num 9",
    74: "Num -",
    75: "Num 4",
    76: "Num 5",
    77: "Num 6",
    78: "Num +",
    79: "Num 1",
    80: "Num 2",
    81: "Num 3",
    82: "Num 0",
    83: "Num .",
    87: "F11",
    88: "F12",
    100: "F13",
    101: "F14",
    102: "F15",
    103: "F16",
    104: "F17",
    105: "F18",
    113: "F19",
    141: "Num =",
    156: "Num Enter",
    157: "Правый Ctrl",
    179: "Num ,",
    181: "Num /",
    183: "Print Screen",
    184: "Правый Alt",
    197: "Pause",
    199: "Home",
    200: "↑",
    201: "Page Up",
    203: "←",
    205: "→",
    207: "End",
    208: "↓",
    209: "Page Down",
    210: "Insert",
    211: "Delete",
    219: "Левый Win / ⌘",
    220: "Правый Win / ⌘",
    221: "Menu",
}
MODIFIERS = {"NONE": "", "SHIFT": "Shift", "CONTROL": "Ctrl", "ALT": "Alt"}


def _key_label(value: str) -> str | None:
    elements = value.split(":")
    if len(elements) > 2:
        return None
    try:
        key = int(elements[0])
    except ValueError:
        return None
    modifier = MODIFIERS.get(elements[-1] if len(elements) == 2 else "NONE")
    if modifier is None:
        return None
    label = KEYS.get(key)
    if -100 <= key <= -69:
        label = {-100: "ЛКМ", -99: "ПКМ", -98: "СКМ"}.get(
            key, f"Кнопка мыши {key + 101}"
        )
    elif 256 < key <= 256 + 0xFFFF and chr(key - 256).isprintable():
        label = chr(key - 256).upper()
    if label and modifier:
        return f"{modifier} + {label}"
    return label


def saved_legacy_key_labels(folder: Path, *bindings: str) -> dict[str, str]:
    """Read current key labels from options.txt without changing the installation."""
    try:
        with local_file(folder, "options.txt").open("rb") as source:
            raw = source.read(MAX_OPTIONS_BYTES + 1)
        if len(raw) > MAX_OPTIONS_BYTES:
            return {}
        lines = raw.decode("utf-8-sig").splitlines()
    except OSError, ValueError:
        return {}
    options = dict(line.split(":", 1) for line in lines if ":" in line)
    return {
        binding: label
        for binding in bindings
        if (label := _key_label(options.get("key_" + binding, "")))
    }
