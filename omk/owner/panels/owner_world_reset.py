"""Manual TUI workflow over the existing cold resource-world operations."""

import re
import subprocess
from contextlib import nullcontext
from dataclasses import dataclass

from omk.backups.cold_backup_worker import digest
from omk.deployment import ingress, ingress_config
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
from omk.owner.panels import owner_volumes
from omk.worlds import world_cutover as cutover
from omk.worlds.reset.dimension_reset import RESOURCE, layout
from omk.worlds.reset.resource_reset_inventory import validate_dimension

COMMANDS = ("inspect", "prepare", "apply", "start")


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

    def confirmation(self, server, *, world=None):
        """Return the confirmation details for the next permitted operation."""
        if self.stage not in COMMANDS[1:]:
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


def _state(config, server, selection=None):
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
    state = State(
        dimension=dimension,
        source=source,
        target=target,
        reset=layout(dimension) if selection is not None else None,
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
        state.window = maintenance.read_record(
            config, state.resource["maintenance_operation"]
        )
        state.backup = backups.read_record(config, state.resource["backup_operation"])
        if (
            state.resource["target"] != target
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
        if any(
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
    if state.resource is None:
        owner_volumes.destination(state.target, unused=True)
    if window is None:
        window_id = maintenance.plan(config, server)["operation"]
        window = maintenance.read_record(config, window_id)
    window_id = window["operation"]
    _require_drained(config, server, window)
    if window["stage"] == "planned":
        result = maintenance.execute(config, window_id, "stop")
        if result["stage"] != "stopped":
            raise AdminError("Clean maintenance stop is unconfirmed")
    if state.resource:
        resource = staging.status(state.resource)
    else:
        backup_id = _operation(state.backup)
        if backup_id is None:
            backup_id = backups.plan(config, server)["operation"]
        if state.backup is None or state.backup["stage"] == "planned":
            backups.run(config, backup_id)
        resource = staging.plan(
            config,
            server,
            state.dimension,
            window_id,
            backup_id,
            **({"selected_world": True} if state.reset is not None else {}),
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
    operation = _operation(state.installation)
    if operation is None:
        operation = cutover.plan(config, state.resource["operation"])["operation"]
    result = cutover.execute(config, operation, "apply")
    if result["stage"] != "installed":
        raise AdminError("World installation requires inspection")


def _start(config, state):
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
    if not isinstance(entries, list) or len(entries) > 64:
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


def _selected_state(config, server, worlds, dimension):
    if dimension is None:
        state = _state(config, server)
        if worlds and state.dimension is None:
            return _selected_state(config, server, worlds, next(iter(worlds)))
        return state
    if dimension not in worlds:
        raise AdminError("World is not in the operator catalog")
    if dimension == RESOURCE:
        state = _state(config, server)
        if state.dimension == dimension:
            return state
        return State(dimension=dimension, stage="unsupported")
    path = config.private / "resource-resets.toml"
    if not path.exists() and not path.is_symlink():
        return State(dimension=dimension, stage="unsupported")
    return _state(config, server, dimension)


def run(path, server, action, confirmation, *, catalog=False, dimension=None):
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
                result["worlds"] = list(worlds.values())
            state = _selected_state(config, server, worlds, dimension)
            world = worlds.get(state.dimension)
            result.update(state.payload(server, world=world))
            if action != "inspect":
                if action != state.stage or confirmation != state.confirmation(
                    server, world=world
                ):
                    result["error"] = "state_changed"
                    return result
                try:
                    _require_drained(config, server, state.window)
                except AdminError, OSError, subprocess.SubprocessError:
                    result["error"] = "ingress_not_drained"
                    return result
                result["effect"] = "unknown"
                if action == "prepare":
                    _prepare(config, server, state)
                elif action == "apply":
                    _apply(config, state)
                else:
                    _start(config, state)
                result.update(
                    _selected_state(config, server, worlds, dimension).payload(
                        server, world=world
                    )
                    if action != "start"
                    else {"stage": "complete", "confirmation": None}
                )
                result["effect"] = "applied"
            result["ok"] = True
    except backups.OwnerBusy:
        result["error"] = "owner_busy"
    except (
        AdminError,
        KeyError,
        OSError,
        TypeError,
        ValueError,
        subprocess.SubprocessError,
    ):
        result["error"] = "operation_rejected"
    return result
