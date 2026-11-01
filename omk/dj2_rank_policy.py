"""Render the owner's numeric limits into a NEW, offline DJ2 rank file."""

import os
import re

FIELDS = {
    "OMK_DJ2_CLAIMS_PER_PLAYER": ("ftbutilities.claims.max_chunks", 50, 30000),
    "OMK_DJ2_HOMES_PER_PLAYER": ("ftbutilities.homes.max", 3, 1000),
}


def apply_player_limits(path, environ=None):
    environment = os.environ if environ is None else environ
    values = {}
    for key, (node, default, maximum) in FIELDS.items():
        raw = environment.get(key, str(default))
        if not re.fullmatch(r"[0-9]{1,5}", raw) or not 1 <= int(raw) <= maximum:
            raise ValueError("Invalid DJ2 player limit: " + key)
        values[node] = int(raw)
    if path.is_symlink() or not path.is_file():
        raise ValueError("Expected a regular staged ranks file")
    with path.open("rb") as source:
        raw = source.read(65537)
    sections = list(re.finditer(rb"(?ms)^\[player\]\r?\n(.*?)(?=^\[|\Z)", raw))
    if len(raw) > 65536 or len(sections) != 1:
        raise ValueError("Expected exactly one supported player rank section")
    match = sections[0]
    body = match[1]
    for node, value in values.items():
        pattern = rb"(?m)^(" + re.escape(node.encode()) + rb":[ \t]*)[0-9]+(\r?)$"
        if len(re.findall(pattern, body)) != 1:
            raise ValueError("Missing or ambiguous staged player limit: " + node)
        body = re.sub(
            pattern, lambda m, limit=value: m[1] + str(limit).encode() + m[2], body
        )
    updated = raw[: match.start(1)] + body + raw[match.end(1) :]
    if updated != raw:
        path.write_bytes(updated)
    return values
