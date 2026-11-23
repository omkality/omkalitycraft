"""Manual TUI workflow over the existing cold resource-world operations."""

import re
import subprocess
import time
from contextlib import nullcontext
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import UTC, datetime
from itertools import islice
from pathlib import Path
from traceback import extract_tb

from omk.backups.cold_backup_worker import digest
from omk.deployment import ingress, ingress_config
from omk.deployment.ingress_template import maintenance_message
from omk.owner import (
    admin_backups as backups,
    admin_maintenance as maintenance,
    admin_reset_staging as staging,
)
from omk.owner.admin import (
    AdminError,
    _read_json,
    _require_private,
    load_operator_config,
)
from omk.owner.admin_resource_reset import discover_saved_worlds
from omk.owner.panels import owner_moderation, owner_volumes
from omk.worlds import world_cutover as cutover
from omk.worlds.reset.dimension_reset import RESOURCE, layout, validate_layout
from omk.worlds.reset.resource_reset_inventory import (
    WORLD_CATALOG_LIMIT,
    validate_dimension,
)

STEPS = ("prepare", "apply", "start")
COMMANDS = ("inspect", "run", *STEPS)
_progress = ContextVar("world_reset_progress", default=None)


def _announce(phase):
    if (send := _progress.get()) is not None:
        send(phase)


@dataclass
class State:
    """Represent the current world-reset phase and the evidence needed to proceed."""

    dimension: int | None = None
    stage: str = "unconfigured"
    source: dict | None = None
    target: dict | None = None
    window: dict | None = None
    backup: dict | None = None
    resource: dict | None = None
    installation: dict | None = None
    reset: dict | None = None
    managed: bool = False

    def confirmation(self, server, *, world=None):
        """Return the confirmation details for the next permitted operation."""
        if self.stage not in STEPS:
            return None
        binding = {"server": server, **vars(self)}
        if world is not None:
            binding["world"] = world
        return digest(binding)

    def payload(self, server, *, world=None):
        """Serialize world-reset state for the owner interface."""
        return {
            "dimension": self.dimension,
            "stage": self.stage,
            "confirmation": self.confirmation(server, world=world),
            "maintenance": _operation(self.window),
            "backup": _operation(self.backup),
            "resource": _operation(self.resource),
            "installation": _operation(self.installation),
        }


def _operation(record):
    return record["operation"] if record else None


def _live(config, folder, reader):
    root = config.private / folder
    if not root.exists():
        return []
    records = []
    for index, path in enumerate(root.iterdir()):
        if index >= 1000 or not re.fullmatch(r"[a-f0-9]{32}\.json", path.name):
            raise AdminError("Invalid live owner journal inventory")
        records.append(reader(config, path.stem))
    return records


def _one(records):
    if len(records) > 1:
        raise AdminError("Resolve the ambiguous owner operations")
    return records[0] if records else None


def _backup(config, server, state):
    window = state.window
    if not window or window["stage"] != "stopped":
        return None
    matching = [
        record
        for record in _live(config, "backups", backups.read_record)
        if record["server"] == server
        and record["target"] == state.source
        and record["checkpoint"] == window["checkpoint"]
        and record["stage"] != "cancelled"
    ]
    pending = _one([r for r in matching if r["stage"] != "complete"])
    return pending or max(matching, key=lambda r: r["created_at"], default=None)


def _phase(state):
    if state.installation:
        stage = state.installation["stage"]
        if stage == "planned":
            return "apply"
        if stage in {"installed", "commit-requested"} and state.window["stage"] in {
            "stopped",
            "complete",
        }:
            return "start"
        return "review"
    if state.window and state.window["stage"] not in {"planned", "stopped"}:
        return "review"
    if state.resource:
        if state.resource["stage"] == "runtime-ready":
            return "apply"
        if state.resource["stage"] not in {"planned", "staged", "runtime-planned"}:
            return "review"
    if state.backup and state.backup["stage"] not in {"planned", "complete"}:
        return "review"
    return "prepare"


def _installed_reset(state, rftools):
    selected = state.resource.get("reset")
    if (
        rftools is None
        or not state.installation
        or state.installation["stage"] == "planned"
        or state.installation["resource_operation"] != _operation(state.resource)
        or state.resource["dimension"] != state.dimension
        or not selected
        or "rftools_identity" not in selected
    ):
        return state.reset
    # An installed candidate has a new seed and may not yet have terrain.
    # The cutover's sealed receipt, not the new live registry, binds it.
    validate_layout(state.dimension, selected)
    return selected


def _state(config, server, selection=None, *, managed=False, rftools=None):
    if server not in config.servers:
        raise AdminError("Server is not in the operator allowlist")
    filename = "resource-resets.toml"
    path = config.private / filename
    if not path.exists() and not path.is_symlink():
        return State(
            dimension=selection,
            stage="unsupported" if selection is not None else "unconfigured",
        )
    _require_private(path)
    entry = owner_volumes.document(config, filename).get(server)
    if entry is None:
        return State(
            dimension=selection,
            stage="unsupported" if selection is not None else "unconfigured",
        )
    owner_volumes.validate_entry(entry, filename)
    dimension = entry["dimension"] if selection is None else selection
    if selection is None and dimension != validate_dimension(dimension)["dimension"]:
        return State(dimension=dimension, stage="unsupported")
    if not ingress_config.configured(config):
        return State(dimension=dimension, stage="no-ingress")
    source = backups.target_for(config, server)
    target = owner_volumes.target_for(config, server, source, filename)
    rftools_identity = rftools["rftools_identity"] if rftools is not None else None
    state = State(
        dimension=dimension,
        source=source,
        target=target,
        reset=(
            layout(
                dimension,
                all_worlds=managed and dimension == 0,
                rftools_identity=rftools_identity,
            )
            if selection is not None and (rftools is None or rftools_identity)
            else None
        ),
        managed=managed,
    )
    state.installation = _one(
        [
            r
            for r in cutover.records(config)
            if r["server"] == server and r["stage"] not in cutover.TERMINAL
        ]
    )
    resources = staging.records(config)
    state.resource = _one(
        [
            r
            for r in resources
            if r["server"] == server
            and r["stage"] != "abandoned"
            and not cutover.consumed(config, r)
        ]
    )
    if state.resource:
        state.reset = _installed_reset(state, rftools)
        state.window = maintenance.read_record(
            config, state.resource["maintenance_operation"]
        )
        state.backup = backups.read_record(config, state.resource["backup_operation"])
        if (
            not staging.matches_target(config, state.resource)
            or state.resource["dimension"] != dimension
            or state.resource.get("reset") != state.reset
            or state.resource["source"] != source
            or state.window["server"] != server
        ):
            state.stage = "review"
            return state
    else:
        if state.installation:
            raise AdminError("World installation has no matching candidate")
        if rftools is not None and state.reset is None:
            state.stage = "unsupported"
            return state
        if not managed and any(
            r["stage"] != "abandoned"
            and r["target"]["data_volume"] == target["data_volume"]
            for r in resources
        ):
            state.stage = "used-target"
            return state
        state.window = _one(
            [
                r
                for r in _live(config, "maintenance", maintenance.read_record)
                if r["server"] == server and r["stage"] not in maintenance.TERMINAL
            ]
        )
        state.backup = _backup(config, server, state)
    if state.installation and state.installation["resource_operation"] != _operation(
        state.resource
    ):
        raise AdminError("World installation and candidate differ")
    state.stage = _phase(state)
    return state


def _require_drained(config, server, window):
    if window:
        cutover.drained(config, server, window)
    else:
        _, observed = ingress.capture(config, server, closed=True)
        if observed["sessions"]:
            raise AdminError("Ingress still has active players")


def _prepare(config, server, state):
    window = state.window
    if state.resource is None and not state.managed:
        owner_volumes.destination(state.target, unused=True)
    if window is None:
        window_id = maintenance.plan(config, server)["operation"]
        window = maintenance.read_record(config, window_id)
    window_id = window["operation"]
    _require_drained(config, server, window)
    if window["stage"] == "planned":
        _announce("stopping")
        result = maintenance.execute(config, window_id, "stop")
        if result["stage"] != "stopped":
            raise AdminError("Clean maintenance stop is unconfirmed")
    if state.resource:
        resource = staging.status(state.resource)
    else:
        _announce("backup")
        backup_id = _operation(state.backup)
        if backup_id is None:
            backup_id = backups.plan(config, server)["operation"]
        if state.backup is None or state.backup["stage"] == "planned":
            backups.run(config, backup_id)
        _announce("preparing")
        resource = staging.plan(
            config,
            server,
            state.dimension,
            window_id,
            backup_id,
            **({"selected_world": True} if state.reset is not None else {}),
            **({"managed": True} if state.managed else {}),
            **(
                {"rftools_identity": state.reset["rftools_identity"]}
                if state.reset and "rftools_identity" in state.reset
                else {}
            ),
        )
    for before, action in (
        ("planned", "stage"),
        ("staged", "runtime-plan"),
        ("runtime-planned", "runtime-stage"),
    ):
        if resource["stage"] == before:
            resource = staging.execute(config, resource["operation"], action)
    sealed = staging.execute(config, resource["operation"], "runtime-verify")
    if sealed["stage"] != "runtime-ready":
        raise AdminError("Resource candidate did not seal")


def _apply(config, state):
    _announce("installing")
    operation = _operation(state.installation)
    if operation is None:
        operation = cutover.plan(config, state.resource["operation"])["operation"]
    result = cutover.execute(config, operation, "apply")
    if result["stage"] != "installed":
        raise AdminError("World installation requires inspection")


def _start(config, state):
    _announce("starting")
    if state.window["stage"] == "stopped":
        result = maintenance.execute(
            config,
            state.window["operation"],
            "start",
            backup_operation=state.backup["operation"],
        )
        if result["stage"] != "complete":
            raise AdminError("World start requires inspection")
    result = cutover.execute(config, state.installation["operation"], "commit")
    if result["stage"] != "committed":
        raise AdminError("World installation acknowledgement is unconfirmed")


def _set_ingress(config, server, wanted, *, reason=None):
    operation = ingress.plan(
        config, server, wanted, **({"reason": reason} if reason else {})
    )["operation"]
    if ingress.execute(config, operation, "apply")["stage"] != "confirmed":
        raise AdminError("Game admission change was not confirmed")


def _catalog(config, server):
    path = config.private / "world-catalog.json"
    if not path.exists() and not path.is_symlink():
        return {}
    document = _read_json(path, config.private)
    servers = document.get("servers")
    if (
        set(document) != {"schema", "servers"}
        or type(document["schema"]) is not int
        or document["schema"] != 1
        or not isinstance(servers, dict)
        or set(servers) - config.servers.keys()
    ):
        raise AdminError("Invalid world catalog")
    entries = servers.get(server, [])
    if not isinstance(entries, list) or len(entries) > WORLD_CATALOG_LIMIT:
        raise AdminError("Invalid world list")
    worlds = {}
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != {
            "dimension",
            "name",
            "description",
        }:
            raise AdminError("Invalid world catalog entry")
        dimension = entry["dimension"]
        if (
            type(dimension) is not int
            or not -(2**31) <= dimension < 2**31
            or dimension in worlds
            or not all(
                isinstance(entry[key], str)
                and 1 <= len(entry[key]) <= limit
                and entry[key].strip() == entry[key]
                and entry[key].isprintable()
                for key, limit in (("name", 64), ("description", 240))
            )
        ):
            raise AdminError("Invalid world catalog entry")
        worlds[dimension] = entry
    return worlds


def _inspect_other_worlds(config, server, worlds):
    room = WORLD_CATALOG_LIMIT - len(worlds)
    if not worlds or not room:
        return {}
    try:
        discovered = discover_saved_worlds(config, server)
    except AdminError, OSError, KeyError, TypeError, ValueError:
        # Live WorldSavedData can change during a save. Keep the configured catalog.
        return {}
    available = ((dim, entry) for dim, entry in discovered.items() if dim not in worlds)
    return dict(islice(available, room))


def _selected_state(config, server, worlds, dimension):
    if dimension is None:
        state = _state(config, server, **({"managed": True} if worlds else {}))
        if worlds and state.dimension is None:
            return _selected_state(config, server, worlds, next(iter(worlds)))
        return state
    if dimension not in worlds:
        raise AdminError("World is not in the operator catalog")
    entry = worlds[dimension]
    if "rftools_identity" in entry:
        return _state(config, server, dimension, managed=True, rftools=entry)
    if dimension == RESOURCE:
        state = _state(config, server, managed=True)
        if state.dimension == dimension:
            return state
        return State(dimension=dimension, stage="unsupported")
    path = config.private / "resource-resets.toml"
    if not path.exists() and not path.is_symlink():
        return State(dimension=dimension, stage="unsupported")
    return _state(config, server, dimension, managed=True)


def _close_and_drain(config, server, result):
    _announce("closing")
    binding, observed = ingress.capture(config, server)
    result["effect"] = "unknown"
    world = next(
        (
            world["name"]
            for world in result.get("worlds", ())
            if world["dimension"] == result.get("dimension")
        ),
        None,
    )
    reason = "wipe:" + world if world else "wipe"
    if not observed["closed"] or binding.get("spec", {}).get("maintenance_messages"):
        _set_ingress(config, server, "closed", reason=reason)
    _announce("disconnecting")
    owner_moderation.kick_for_maintenance(config, server, maintenance_message(reason))
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        value, observed = ingress.capture(config, server, closed=True)
        if value != binding:
            raise AdminError("Game admission changed during player disconnect")
        if observed["sessions"] == 0:
            _announce("drained")
            return
        time.sleep(0.2)
    # Pending handshakes have no player identity. Disconnect only the closed
    # gameplay route, after authenticated players have received the reason.
    if ingress.worker(config, binding, "drain")["sessions"]:
        raise AdminError("Game connections did not close before the wipe")
    _announce("drained")


def _execute_stage(config, server, action, state, result):
    try:
        if (
            state.managed
            and action == "prepare"
            and (state.window is None or state.window["stage"] == "planned")
        ):
            _close_and_drain(config, server, result)
        _require_drained(config, server, state.window)
    except (RuntimeError, OSError, subprocess.SubprocessError) as error:
        result["error"] = "ingress_not_drained"
        result["diagnostic"] = _diagnostic(error)
        return False
    result["effect"] = "unknown"
    if action == "prepare":
        _prepare(config, server, state)
    elif action == "apply":
        _apply(config, state)
    else:
        _start(config, state)
        if state.managed:
            result.update(stage="complete", confirmation=None)
            try:
                _announce("opening")
                _set_ingress(config, server, "open")
            except (AdminError, OSError, subprocess.SubprocessError) as error:
                result["error"] = "join_closed"
                result["diagnostic"] = _diagnostic(error)
                return False
    return True


def _diagnostic(error: Exception) -> str:
    """Summarize the failed check without arguments, locals, or raw CLI output."""
    # AdminError is reserved for operator-safe messages. Other exception messages
    # can contain private paths or the input/output of a failed subprocess.
    detail = type(error).__name__
    if isinstance(error, AdminError):
        message = "".join(char for char in str(error) if char.isprintable())[:500]
        detail = f"{detail}: {message}"
    trace = extract_tb(error.__traceback__)[-8:]
    lines = [
        f"{Path(frame.filename).name}:{frame.lineno} ({frame.name})" for frame in trace
    ]
    return "\n".join([datetime.now(UTC).isoformat(timespec="seconds"), detail, *lines])


def _record_current_stage(config, server, worlds, dimension, result):
    """Include current journal references when an attempted step fails."""
    if result["effect"] != "unknown":
        return
    try:
        state = _selected_state(config, server, worlds, dimension)
    except (
        AdminError,
        KeyError,
        OSError,
        TypeError,
        ValueError,
        subprocess.SubprocessError,
    ):
        return
    for field in ("maintenance", "backup", "resource", "installation"):
        operation = _operation(
            getattr(state, "window" if field == "maintenance" else field)
        )
        if operation is not None:
            result[field] = operation


def _run_steps(config, server, action, state, worlds, dimension, world, result):
    steps = STEPS[STEPS.index(state.stage) :] if action == "run" else (action,)
    for step in steps:
        if state.stage != step:
            raise AdminError("World reset reached an unexpected state")
        if not _execute_stage(config, server, step, state, result):
            return False
        if step == "start":
            result.update(stage="complete", confirmation=None)
        else:
            state = _selected_state(config, server, worlds, dimension)
            result.update(state.payload(server, world=world))
    result["effect"] = "applied"
    return True


def run(
    path, server, action, confirmation, *, catalog=False, dimension=None, progress=None
):
    """Inspect or execute an owner-confirmed operation on a configured world."""
    result = {
        "schema_version": 1,
        "action": "owner.world-reset",
        "server_id": server,
        "command": action,
        "ok": False,
        "effect": "none",
        "error": None,
        **State().payload(server),
    }
    try:
        if (
            action not in COMMANDS
            or (action == "inspect" and confirmation)
            or (dimension is not None and not catalog)
        ):
            result["error"] = "invalid_request"
            return result
        config = load_operator_config(path)
        with backups.locked(config) if action != "inspect" else nullcontext():
            worlds = _catalog(config, server) if catalog else {}
            if catalog:
                if action == "inspect" or (
                    dimension is not None and dimension not in worlds
                ):
                    worlds = {**worlds, **_inspect_other_worlds(config, server, worlds)}
                result["worlds"] = [
                    {key: entry[key] for key in ("dimension", "name", "description")}
                    for entry in worlds.values()
                ]
            state = _selected_state(config, server, worlds, dimension)
            world = worlds.get(state.dimension)
            result.update(state.payload(server, world=world))
            if action == "inspect" and state.stage == "review":
                result["diagnostic"] = (
                    "\n".join(
                        f"{name}: {record['stage']}"
                        for name, record in (
                            ("Maintenance", state.window),
                            ("Backup", state.backup),
                            ("Staging", state.resource),
                            ("Installation", state.installation),
                        )
                        if record is not None
                    )
                    or "Current reset bindings require inspection"
                )
            if action != "inspect":
                if (
                    (state.stage not in STEPS or not state.managed)
                    if action == "run"
                    else action != state.stage
                ) or confirmation != state.confirmation(server, world=world):
                    result["error"] = "state_changed"
                    return result
                world_name = world["name"] if world else "Мир"
                scope = _progress.set(
                    (lambda phase: progress(phase, world_name)) if progress else None
                )
                try:
                    if not _run_steps(
                        config, server, action, state, worlds, dimension, world, result
                    ):
                        _record_current_stage(config, server, worlds, dimension, result)
                        return result
                except (
                    AdminError,
                    KeyError,
                    OSError,
                    TypeError,
                    ValueError,
                    subprocess.SubprocessError,
                ):
                    _record_current_stage(config, server, worlds, dimension, result)
                    raise
                finally:
                    _progress.reset(scope)
            result["ok"] = True
    except backups.OwnerBusy as error:
        result["error"] = "owner_busy"
        result["diagnostic"] = _diagnostic(error)
    except (
        AdminError,
        KeyError,
        OSError,
        TypeError,
        ValueError,
        subprocess.SubprocessError,
    ) as error:
        result["error"] = "operation_rejected"
        result["diagnostic"] = _diagnostic(error)
    return result
