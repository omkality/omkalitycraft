"""Parser for the project's canonical key=value server properties."""

import re

MAX_PROPERTIES_BYTES = 1024**2


def parse_properties(data):
    """Return source lines and values; refuse ambiguous Java escape syntax."""
    if not isinstance(data, bytes) or len(data) > MAX_PROPERTIES_BYTES or b"\0" in data:
        raise ValueError("Invalid canonical server properties")
    try:
        lines, values = [], {}
        for line in data.decode("utf-8").splitlines():
            if not line.strip() or line.lstrip().startswith(("#", "!")):
                lines.append((None, line))
                continue
            key, separator, value = line.partition("=")
            if (
                not separator
                or not re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", key)
                or key in values
                or (len(line) - len(line.rstrip("\\"))) % 2
            ):
                raise ValueError("Invalid canonical server properties")
            values[key] = value
            lines.append((key, line))
    except UnicodeError:
        raise ValueError("Invalid canonical server properties") from None
    return lines, values
