"""Build the reviewed DJ2 border configuration in a fresh staging directory."""

import hashlib
import json
import re
from pathlib import Path

from omk.shared.fs import regular
from omk.shared.profiles import PROJECT_ROOT

PROFILE = PROJECT_ROOT / "profiles/server-defaults/dj2/world-borders.json"
JED = "justenoughdimensions/justenoughdimensions.cfg"
DIMENSIONS = "justenoughdimensions/dimensions.json"
RESOURCE = "omkalitycore-resource.properties"
PRIMER = "worldprimer.cfg"
OPTIONS = "worldborder/main.cfg"
BORDERS = "worldborder/borders.cfg"


def border_plan(world_name: str) -> dict:
    """Return widths for existing dimensions and the default for new ones."""
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", world_name) or re.fullmatch(
        r"DIM-?\d+", world_name, re.IGNORECASE
    ):
        raise ValueError("Invalid or ambiguous Overworld directory name")
    profile = json.loads(PROFILE.read_bytes())
    dimensions = profile["dimensions"]
    if (
        profile["schema"] != 1
        or len(set(dimensions)) != len(dimensions)
        or 0 not in dimensions
        or set(profile["overrides"]) - {str(dim) for dim in dimensions}
        or any(
            type(width) is not int or width % 2 or not 16 <= width <= 60_000_000
            for width in [profile["width"], *profile["overrides"].values()]
        )
    ):
        raise ValueError("Invalid reviewed DJ2 border profile")
    return {
        "world": world_name,
        "default_width": profile["width"],
        "overrides": profile["overrides"],
        "dimensions": {
            str(dim): profile["overrides"].get(str(dim), profile["width"])
            for dim in dimensions
        },
        "artifacts": profile["artifacts"],
    }


def _read_bytes(config: Path, name: str) -> bytes:
    path = config / name
    if not regular(path, config) or path.stat().st_size > 256 * 1024:
        raise ValueError("Missing, linked or oversized border configuration: " + name)
    return path.read_bytes()


def _read(config: Path, name: str) -> str:
    return _read_bytes(config, name).decode("utf-8").replace("\r\n", "\n")


def _setting(text: str, kind: str, key: str, value: str) -> str:
    pattern = r"(?m)^( +)" + re.escape(f"{kind}:{key}=") + r"[^\n]*$"
    result, count = re.subn(pattern, lambda m: f"{m[1]}{kind}:{key}={value}", text)
    if count != 1:
        raise ValueError("Expected exactly one border setting: " + key)
    return result


def _commands(text: str, key: str, commands: list[str]) -> str:
    pattern = r"(?m)^( +)S:" + re.escape(key) + r" <\n([\s\S]*?)^ +> *$"
    matches = list(re.finditer(pattern, text))
    if len(matches) != 1:
        raise ValueError("Expected exactly one World Primer list: " + key)
    match = matches[0]
    existing = [row.strip() for row in match[2].splitlines() if row.strip()]
    if existing and existing != commands:
        raise ValueError("Review existing World Primer commands before staging " + key)
    return (
        text[: match.start(2)]
        + "".join(f"{match[1]}    {command}\n" for command in commands)
        + text[match.end(2) :]
    )


def _options(text: str) -> str:
    if not re.search(r"(?m)^    S:bypass-list-uuids <\n +> *$", text):
        raise ValueError("WorldBorder bypass list must be empty")
    for key, value in {
        "deny-enderpearl": "true",
        "prevent-block-place": "true",
        "prevent-mob-spawn": "true",
        "player-killed-bad-spawn": "false",
        "round-border": "false",
    }.items():
        text = _setting(text, "B", key, value)
    return text


def _jed(text: str) -> str:
    for key, value in {
        "enableSeparateWorldBorders": "true",
        "enableSeparateWorldInfo": "true",
        "usePerWorldMainConfig": "false",
    }.items():
        text = _setting(text, "B", key, value)
    return text


def _dimension_info(raw: bytes, plan: dict) -> str:
    document = json.loads(raw)
    rows = document["dimensions"]
    lookup = {}
    for row in rows:
        dim = row["dim"]
        if type(dim) is not int or dim in lookup:
            raise ValueError("Duplicate or invalid JED dimension")
        lookup[dim] = row
    for dim, width in plan["dimensions"].items():
        row = lookup.get(int(dim))
        if row is None:
            row = {"dim": int(dim)}
            rows.append(row)
        if row["dim"] != 0 and not {"worldinfo", "worldinfo_onetime"} & row.keys():
            # JED would otherwise generate terrain to locate a spawn on first load.
            # Providers such as Emptiness can still be initializing their structures.
            jed = row.setdefault("jed", {})
            if not isinstance(jed, dict):
                raise ValueError("Unsupported JED dimension options")
            jed.setdefault("SpawnPointSearchType", {"type": "none"})
        info = row.setdefault("worldinfo", {})
        if not isinstance(info, dict):
            raise ValueError("Unsupported JED world info")
        for key, value in {
            "BorderCenterX": 0.0,
            "BorderCenterZ": 0.0,
            "BorderSize": float(width),
            "BorderSizeLerpTarget": float(width),
            "BorderSizeLerpTime": 0,
        }.items():
            info[key] = value
    return json.dumps(document, indent=2, ensure_ascii=False) + "\n"


def _primer(text: str, plan: dict) -> str:
    commands = [f"jed worldborder {{DIMENSION}} set {plan['default_width']}"]
    commands.extend(
        f"worldprimer-dim-command {dim} jed worldborder {dim} set {width}"
        for dim, width in plan["overrides"].items()
    )
    text = _commands(text, "dimensionLoadingCommands", commands)
    text = _commands(
        text,
        "postWorldLoadingCommands",
        [f"jed worldborder 0 set {plan['dimensions']['0']}"],
    )
    for key in ("enableDimensionLoadingCommands", "enablePostWorldLoadingCommands"):
        text = _setting(text, "B", key, "true")
    return text


def _borders(plan: dict) -> str:
    widths = {
        (plan["world"] if dim == "0" else "DIM" + dim): width
        for dim, width in plan["dimensions"].items()
    }
    # WorldBorder rewrites this file through Forge Configuration at shutdown.
    # Match the saved bytes so a routine stop preserves the runtime fingerprint.
    blocks = ["# Configuration file\n\n"]
    for name, width in sorted(widths.items()):
        radius = width // 2
        blocks.append(
            f"{name} {{\n    I:radiusX={radius}\n    I:radiusZ={radius}\n"
            "    B:wrapping=false\n    D:x=0.0\n    D:z=0.0\n}\n\n\n"
        )
    return "".join(blocks)


def prepare_borders(output: Path, config: Path, mods: Path, world_name: str) -> dict:
    """Verify the server JARs, then write an offline copy of the border files."""
    plan = border_plan(world_name)
    for name, expected in plan["artifacts"].items():
        path = mods / name
        if not regular(path, mods) or path.stat().st_size > 16 * 1024**2:
            raise ValueError("Missing or unreviewed world border artifact: " + name)
        with path.open("rb") as stream:
            if hashlib.file_digest(stream, "sha256").hexdigest() != expected:
                raise ValueError("Unreviewed world border artifact: " + name)
    previous = _read_bytes(config, DIMENSIONS)
    dimensions = _dimension_info(previous, plan)
    files = {
        JED: _jed(_read(config, JED)),
        DIMENSIONS: dimensions,
        PRIMER: _primer(_read(config, PRIMER), plan),
        OPTIONS: _options(_read(config, OPTIONS)),
        BORDERS: _borders(plan),
    }
    resource_path = config / RESOURCE
    if resource_path.exists() or resource_path.is_symlink():
        props = _read(config, RESOURCE)
        old = hashlib.sha256(previous).hexdigest()
        if re.findall(r"(?m)^jed_config_sha256=(\w+)$", props) != [old]:
            raise ValueError("Resource policy does not match the existing JED file")
        new = hashlib.sha256(dimensions.encode()).hexdigest()
        files[RESOURCE] = props.replace(
            "jed_config_sha256=" + old, "jed_config_sha256=" + new
        )
    output.mkdir(parents=True, exist_ok=False)
    for name, contents in files.items():
        path = output / "config" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(contents, encoding="utf-8", newline="\n")
    return {**plan, "files": sorted("config/" + name for name in files)}
