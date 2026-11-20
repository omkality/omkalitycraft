"""Reviewed Forge 1.12/FTB5.4 authority on a selected stopped release copy.

No auth restore, Docker lifecycle or promotion. The owner serializes operations,
mounts export/current sources read-only and exclusively owns the staged target.
"""

import copy
import json
import re
import shutil
import tarfile
from pathlib import PurePosixPath

from omk.backups.backup_store import _directory
from omk.owner.storage import project_stage as raw
from omk.shared.fs import resolved
from omk.worlds import linux_restore_policy as shared

ADAPTER = "dj2-ftb54-current-v1"
PLAN = ".omk-project-policy-plan.json"
DONE = ".omk-project-policy-staged.json"
WRITING = ".omk-project-policy-writing"
PROTECTED = (
    "online-mode",
    "white-list",
    "server-ip",
    "server-port",
    "enable-rcon",
    "rcon.port",
    "rcon.password",
    "pvp",
    "difficulty",
    "max-players",
)
FLAGS = {
    "quarantine_required": True,
    "ready_for_players": False,
    "boot_allowed": False,
    "current_policy_reconciled": True,
}
write_record = shared._write_record


def _properties(data):
    if not isinstance(data, bytes) or len(data) > shared.MAX_FILE or b"\0" in data:
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


def protected_properties(current, historical, world):
    """Accept canonical key=value files only, never guess Java escape semantics."""
    _lines, values = _properties(current)
    lines, old = _properties(historical)
    if (
        set(PROTECTED) - values.keys()
        or values.get("level-name") != world
        or old.get("level-name") != world
        or any(values[k] != values[k].strip() for k in PROTECTED)
        or values["online-mode"] != "true"
        or values["enable-rcon"] != "true"
        or values["server-ip"] != ""
        or values["white-list"] not in {"true", "false"}
        or values["pvp"] != "true"
        or values["difficulty"] != "3"
        or not 16 <= len(values["rcon.password"]) <= 1024
        or any(
            ord(c) < 33 or ord(c) > 126 or c == "\\" for c in values["rcon.password"]
        )
    ):
        raise ValueError("Unreviewed current server access properties")
    for key in ("server-port", "rcon.port", "max-players"):
        value = values[key]
        if not re.fullmatch(r"[0-9]{1,5}", value) or not (
            1 if key == "max-players" else 1024
        ) <= int(value) <= (10000 if key == "max-players" else 65535):
            raise ValueError("Invalid current server access properties")
    if int(values["server-port"]) == int(values["rcon.port"]):
        raise ValueError("Current game and RCON ports must differ")
    return (
        "\n".join(
            [line for key, line in lines if key not in PROTECTED]
            + [key + "=" + values[key] for key in PROTECTED]
        )
        + "\n"
    ).encode()


def _fresh(target):
    if any(
        (target / key).exists() or (target / key).is_symlink()
        for key in (PLAN, DONE, WRITING)
    ):
        raise ValueError(
            "Project policy already attempted; never repeat partial changes"
        )


def _record(source, target, current, raw_expected, adapter):
    if adapter != ADAPTER:
        raise ValueError("Unreviewed project policy adapter")
    base, runtime, modes, world_files = raw._bound(source, target, raw_expected)
    _directory(current)
    if (
        not current.is_absolute()
        or resolved(current) != current.absolute()
        or any(
            current.is_relative_to(p) or p.is_relative_to(current)
            for p in (source, target)
        )
    ):
        raise ValueError("Current authority requires a separate unlinked source")
    if raw._digest(raw._read(target / raw.PLAN, target)) != raw._digest(
        base
    ) or raw._digest(raw._read(target / raw.DONE, target)) != raw._digest(
        {**base, **raw._FLAGS}
    ):
        raise ValueError("Project policy lost its original raw receipt")
    game, world = target / raw.GAME, base["world"]
    shared.ftb.check_runtime(current)
    shared.ftb.check_runtime(game)
    data, records, summary = shared._current(current, world)
    if json.loads(data["ops.json"]):
        raise ValueError("Current project policy must not contain game operators")
    historical = shared.ftb.read_zip(
        source / "world.zip",
        world_name=world,
        path_policy="linux-server",
        max_expanded_bytes=base["settings"]["world_bytes"],
    )
    if (
        "server.properties" not in runtime
        or runtime["server.properties"]["bytes"] > shared.MAX_FILE
    ):
        raise ValueError("Selected runtime has no bounded server properties")
    with tarfile.open(source / "runtime.tar", "r:") as incoming:
        reader = raw._RuntimeReader(incoming, runtime, modes)
        with reader.open("server.properties") as stream:
            old_props = stream.read(shared.MAX_FILE + 1)
    current_props = shared._read(current, "server.properties")
    if shared.digest(current_props) != summary["properties_sha256"]:
        raise ValueError("Current properties changed during policy planning")
    props = protected_properties(current_props, old_props, world)
    payload, world_after = shared.compose_payload(
        data, records, historical, world, world_files, props
    )
    after, after_modes = copy.deepcopy(runtime), dict(modes)
    for name, value in payload.items():
        if name.startswith(world + "/"):
            continue
        after[name] = {"bytes": len(value), "sha256": shared.digest(value)}
        after_modes[name] = 0o600
    before = {
        name: (runtime | world_files).get(name, {}).get("sha256") for name in payload
    }
    binding = {
        "schema": 1,
        "operation": base["operation"],
        "adapter": adapter,
        "source": str(source),
        "target": str(target),
        "current_source": str(current),
        "raw_plan_sha256": raw._digest(base),
        "raw_receipt_sha256": raw.archive.digest(target / raw.DONE),
        "current": summary,
        "before": before,
        "after": {name: shared.digest(value) for name, value in payload.items()},
        "runtime_after_sha256": raw._digest({"files": after, "modes": after_modes}),
        "world_after_sha256": raw._digest(world_after),
    }
    return binding, payload, after, after_modes, world_after


def _same(actual, expected):
    if raw._digest(actual) != raw._digest(expected):
        raise ValueError("Project authority source or saved policy plan changed")


def plan(source, target, current, *, raw_expected, adapter):
    _fresh(target)
    raw.verify(source, target, expected=raw_expected)
    binding, payload, _runtime, _modes, _world = _record(
        source, target, current, raw_expected, adapter
    )
    _space(target, payload, raw_expected)
    return binding


def _space(target, payload, raw_expected):
    if (
        shutil.disk_usage(target).free
        < sum(map(len, payload.values()))
        + 65536
        + raw_expected["settings"]["reserve_bytes"]
    ):
        raise OSError("Project policy free-space reserve would be violated")


def _verify_files(target, payload, runtime, modes, world, raw_expected):
    raw._check_files(target, runtime, modes, world, raw_expected["settings"])
    for name, value in payload.items():
        if shared._read(target / raw.GAME, name, limit=shared.ftb.MAX_BYTES) != value:
            raise ValueError("Project authority payload differs from current policy")


def stage(source, target, current, *, raw_expected, expected):
    _fresh(target)
    raw.verify(source, target, expected=raw_expected)
    binding, payload, runtime, modes, world = _record(
        source, target, current, raw_expected, expected.get("adapter")
    )
    _same(binding, expected)
    _space(target, payload, raw_expected)
    write_record(target / PLAN, binding)
    shared.write_payload(
        target / raw.GAME,
        target / WRITING,
        payload,
        binding["before"],
        binding["after"],
    )
    _verify_files(target, payload, runtime, modes, world, raw_expected)
    _same(
        _record(source, target, current, raw_expected, expected["adapter"])[0], binding
    )
    _same(raw._read(target / PLAN, target), binding)
    _layout(target, payload, complete=False)
    write_record(
        target / DONE,
        {"plan_sha256": raw.archive.digest(target / PLAN), "binding": binding, **FLAGS},
    )
    return {"policy_staged": True, **FLAGS}


def verify(source, target, current, *, raw_expected, expected):
    binding, payload, runtime, modes, world = _record(
        source, target, current, raw_expected, expected.get("adapter")
    )
    _same(binding, expected)
    _layout(target, payload, complete=True)
    _same(raw._read(target / PLAN, target), binding)
    _same(
        raw._read(target / DONE, target),
        {"plan_sha256": raw.archive.digest(target / PLAN), "binding": binding, **FLAGS},
    )
    _verify_files(target, payload, runtime, modes, world, raw_expected)
    return {"verified": True, **FLAGS}


def _layout(target, payload, *, complete):
    expected = {raw.PLAN, raw.DONE, raw.GAME, PLAN, WRITING}
    if complete:
        expected.add(DONE)
    if {p.name for p in target.iterdir()} != expected:
        raise ValueError("Incomplete project policy layout")
    allowed = {
        str(p) for name in payload for p in PurePosixPath(name).parents if str(p) != "."
    }
    _directory(target / WRITING)
    for path in (target / WRITING).rglob("*"):
        if (
            path.is_symlink()
            or path.is_junction()
            or not path.is_dir()
            or path.relative_to(target / WRITING).as_posix() not in allowed
        ):
            raise ValueError("Project policy staging is not empty and reviewed")
