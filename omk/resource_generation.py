"""Reviewed DJ2 resource generation edits, made only in an offline copy."""

import hashlib
import json
import re
from pathlib import Path

from omk.profiles import PROJECT_ROOT

PROFILE = PROJECT_ROOT / "profiles/server-defaults/dj2/resource-generation.json"


def _read(root, relative):
    path = Path(root) / relative
    if (
        not path.is_file()
        or path.stat().st_size > 2 * 1024**2
        or any(p.is_symlink() or p.is_junction() for p in (path, *path.parents))
    ):
        raise ValueError("A regular generation config is required: " + relative)
    return path.read_bytes()


def forge_fields(text):  # noqa: PLR0912 - small, explicit Forge parser states
    """Read category-qualified fields without rewriting the Forge file."""
    lines, stack, fields = text.splitlines(keepends=True), [], {}
    index = 0
    while index < len(lines):
        line = lines[index].strip()
        if not line or line.startswith("#"):
            index += 1
            continue
        if not stack and re.fullmatch(r"~CONFIG_VERSION: [0-9.]+", line):
            index += 1
            continue
        if line == "}":
            if not stack:
                raise ValueError("Unbalanced Forge config")
            stack.pop()
        elif match := re.fullmatch(r"([BIDS]):(.+?)\s*(=|<)(.*)", line):
            kind, name, separator, value = match.groups()
            key = (*stack, name.strip().strip('"'))
            if key in fields:
                raise ValueError("Duplicate Forge config field")
            if separator == "=":
                fields[key] = {"kind": kind, "value": value.strip()}
            else:
                if value.strip():
                    raise ValueError("Unknown Forge list format")
                begin = index
                values = []
                while True:
                    index += 1
                    if index >= len(lines):
                        raise ValueError("Unterminated Forge list")
                    item = lines[index].strip()
                    if item == ">":
                        break
                    if item and not item.startswith("#"):
                        values.append(item)
                fields[key] = {
                    "kind": kind,
                    "values": values,
                    "start": begin,
                    "end": index,
                }
        elif line.endswith("{"):
            name = line[:-1].strip().strip('"')
            if not name or len(stack) > 16:
                raise ValueError("Invalid Forge category")
            stack.append(name)
        else:
            raise ValueError("Unknown Forge config syntax")
        index += 1
    if stack:
        raise ValueError("Unbalanced Forge config")
    return lines, fields


def _cfg_patch(raw, rules, dimension):
    text = raw.decode("utf-8")
    lines, fields = forge_fields(text)
    edits, insertions = [], []
    for rule in rules:
        key = tuple(rule["path"])
        field = fields.get(key)
        if field is None or field["kind"] != rule["kind"] or "values" not in field:
            raise ValueError("Missing reviewed generation field: " + ".".join(key))
        values = field["values"]
        if len(values) > 128 or len(values) != len(set(values)):
            raise ValueError("Invalid generation dimension list")
        if rule["kind"] == "I" and any(
            not re.fullmatch(r"-?[0-9]{1,10}", v) or not -(2**31) <= int(v) < 2**31
            for v in values
        ):
            raise ValueError("Invalid generation dimension ID")
        target = str(dimension) if rule["kind"] == "I" else "omk_resource"
        if rule["reference"] not in values:
            raise ValueError("Reviewed Overworld generation rule changed")
        for flag in rule.get("flags", []):
            scalar = fields.get(tuple(flag["path"]))
            if scalar != {"kind": "B", "value": flag["value"]}:
                raise ValueError("Reviewed generation mode changed")
        if target not in values:
            end = field["end"]
            indent = re.match(r"\s*", lines[field["start"]]).group() + "    "
            newline = "\r\n" if lines[end].endswith("\r\n") else "\n"
            insertions.append((end, indent + target + newline))
        edits.append({"path": rule["path"], "mode": rule["mode"], "member": target})
    for end, line in sorted(insertions, reverse=True):
        lines.insert(end, line)
    return "".join(lines).encode("utf-8"), edits


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate generation JSON field")
        result[key] = value
    return result


def _json(raw):
    def invalid(value):
        raise ValueError("Non-finite generation JSON number: " + value)

    return json.loads(raw, object_pairs_hook=_unique, parse_constant=invalid)


# Keep format validation beside the field it constrains.
def additional_generator_patches(source_config, dimension):  # noqa: PLR0912
    if type(dimension) is not int or not -32000 <= dimension <= -2:
        raise ValueError("Invalid resource dimension")
    profile = _json(PROFILE.read_bytes())
    patches, metadata, mirrored = {}, [], set()

    def record(relative, raw, output, edits):
        if output != raw:
            patches[relative] = output
        metadata.append(
            {
                "file": "config/" + relative,
                "source_sha256": hashlib.sha256(raw).hexdigest(),
                "output_sha256": hashlib.sha256(output).hexdigest(),
                "edits": edits,
            }
        )

    for relative in profile["cofh_files"]:
        raw = _read(source_config, relative)
        obj = _json(raw)
        if (
            not isinstance(obj, dict)
            or not isinstance(obj.get("populate"), dict)
            or len(obj["populate"]) > 128
        ):
            raise ValueError("Unknown CoFH generation config")
        edits = []
        for name, feature in obj["populate"].items():
            if not isinstance(feature, dict):
                raise ValueError("Unknown CoFH generation feature")
            restriction = feature.get("dimension", "all")
            if restriction == "all":
                continue
            if not isinstance(restriction, dict) or set(restriction) != {
                "restriction",
                "value",
            }:
                raise ValueError("Unknown CoFH dimension restriction")
            ids = restriction["value"]
            if (
                restriction["restriction"] not in {"whitelist", "blacklist"}
                or not isinstance(ids, list)
                or len(ids) > 128
                or any(type(n) is not int or not -(2**31) <= n < 2**31 for n in ids)
                or len(ids) != len(set(ids))
            ):
                raise ValueError("Invalid CoFH dimension list")
            if 0 in ids:
                mirrored.add(relative + "/" + name)
                if dimension not in ids:
                    ids.append(dimension)
                edits.append(
                    {
                        "feature": name,
                        "mode": restriction["restriction"],
                        "member": dimension,
                    }
                )
            elif dimension in ids:
                raise ValueError("Resource generation diverges from Overworld")
        output = (json.dumps(obj, indent=2) + "\n").encode("utf-8") if edits else raw
        record(relative, raw, output, edits)
    if mirrored != set(profile["cofh_reviewed_memberships"]):
        raise ValueError("Unreviewed CoFH Overworld membership")
    for item in profile["forge_files"]:
        raw = _read(source_config, item["file"])
        output, edits = _cfg_patch(raw, item["rules"], dimension)
        record(item["file"], raw, output, edits)
    return patches, metadata
