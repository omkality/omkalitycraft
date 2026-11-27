"""Search selected Minecraft effects through the owner CLI."""

import re
from datetime import timedelta
from uuid import UUID

from omk.owner.admin import AdminError, _private_path, _write_private
from omk.owner.private_journal import JournalScan, _integer, parse_time

_ACTIONS = (
    "place",
    "multi_place",
    "break",
    "activate",
    "piston",
    "book_edit",
    "book_sign",
    "sign_edit",
    "craft",
    "drop",
    "pickup",
)
_PLACEMENT = {"place", "multi_place"}
_TRANSFER = {"drop", "pickup"}
_REGISTRY = re.compile(r"[a-z0-9_.-]+:[a-z0-9_/.-]+")
_NAME = re.compile(r"[A-Za-z0-9_]{1,32}")
_HEADER = {"schema", "kind", "at_ms", "server", "profile", "core_version", "boot"}
_BASICS = {
    "sequence",
    "action",
    "actor",
    "dimension",
    "x",
    "y",
    "z",
    "registry",
    "outcome",
}
_WORLD_LIMIT = 30_000_000


def add_action_parser(actions):
    parser = actions.add_parser(
        "action-history", help="Search the private journal of server-observed actions"
    )
    parser.add_argument("--server", required=True)
    parser.add_argument("--dimension", type=int, required=True)
    parser.add_argument("--from", dest="since", required=True)
    parser.add_argument("--until", required=True)
    parser.add_argument(
        "--area",
        type=int,
        nargs=6,
        required=True,
        metavar=("XMIN", "YMIN", "ZMIN", "XMAX", "YMAX", "ZMAX"),
    )
    parser.add_argument("--player", type=UUID, help="Exact account UUID")
    parser.add_argument("--action", choices=_ACTIONS)
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument("--export", action="store_true")
    parser.add_argument("--evidence", metavar="CASE")
    parser.add_argument("--incident", metavar="PRIVATE_JSON")
    parser.add_argument("--backup-operation", metavar="ID")
    parser.add_argument("--snapshot", metavar="PRIVATE_SNAPSHOT_FOLDER")


def _uuid(value):
    try:
        return isinstance(value, str) and str(UUID(value)) == value
    except ValueError:
        return False


def _actor(value):
    if not isinstance(value, dict):
        return False
    if value.get("kind") in ("automation", "fake_player", "unassigned"):
        return set(value) == {"kind"}
    return (
        value.get("kind") == "player"
        and set(value) == {"kind", "uuid", "name"}
        and isinstance(value["name"], str)
        and bool(_NAME.fullmatch(value["name"]))
        and _uuid(value["uuid"])
    )


def _registry(value):
    return isinstance(value, str) and len(value) <= 200 and _REGISTRY.fullmatch(value)


def _within(point, area):
    return all(
        low <= value <= high
        for value, low, high in zip(point, area[:3], area[3:], strict=True)
    )


def _validate_action(row):
    action = row.get("action")
    if action not in _ACTIONS:
        raise ValueError("Unknown private action")
    extra = set()
    if action in _PLACEMENT:
        extra.update(("previous", "placement"))
        if not (_registry(row.get("previous")) and _integer(row.get("placement"), 1)):
            raise ValueError("Invalid placement metadata")
    if action in _TRANSFER | {"craft"}:
        extra.add("count")
        if not _integer(row.get("count"), 1, 2**31 - 1):
            raise ValueError("Invalid item count")
    if action in _TRANSFER:
        extra.add("item_entity")
        if not _uuid(row.get("item_entity")):
            raise ValueError("Invalid dropped entity identity")
    outcomes = (
        ("changed", "observed", "cancelled")
        if action in _PLACEMENT | {"break"}
        else (("observed", "cancelled") if action == "drop" else ("accepted",))
    )
    if not (
        set(row) == _HEADER | _BASICS | extra
        and _actor(row["actor"])
        and (row["actor"]["kind"] == "automation") == (action == "piston")
        and _registry(row["registry"])
        and row["outcome"] in outcomes
        and _integer(row["dimension"], -(2**31), 2**31 - 1)
        and all(_integer(row[key], -_WORLD_LIMIT, _WORLD_LIMIT) for key in "xyz")
    ):
        raise ValueError("Invalid private action record")


def _window(config, args):
    if args.server not in config.servers:
        raise AdminError("Server is outside the owner allowlist")
    start, end = parse_time(args.since), parse_time(args.until)
    if not timedelta(0) < end - start <= timedelta(days=90):
        raise AdminError("Choose an action history interval up to 90 days")
    start, end = round(start.timestamp() * 1000), round(end.timestamp() * 1000)
    if not 1 <= args.limit <= 1000:
        raise AdminError("Choose between 1 and 1000 action matches")
    if not (
        _integer(args.dimension, -(2**31), 2**31 - 1)
        and all(
            -_WORLD_LIMIT <= low <= high <= _WORLD_LIMIT
            for low, high in zip(args.area[:3], args.area[3:], strict=True)
        )
    ):
        raise AdminError(
            "Specify ordered bounds within the Minecraft coordinate limits"
        )
    if args.evidence:
        if (
            not all((args.incident, args.snapshot, args.backup_operation))
            or args.export
        ):
            raise AdminError(
                "An evidence case requires incident, backup operation and snapshot inputs"
            )
        if args.player or args.action:
            raise AdminError("Save incident evidence with the full area history")
    elif any((args.incident, args.snapshot, args.backup_operation)):
        raise AdminError("Use --evidence to bind incident inputs to a case")
    return start, end


def run_actions(config, args):
    """Search one area and period, with coverage even when the selection is empty."""
    start, end = _window(config, args)
    directory = _private_path(config.private, f"action-history/{args.server}")
    scan = JournalScan(directory, "action", "action", args.server, _validate_action)
    events = []
    matches = 0
    player = str(args.player) if args.player else None
    for row in scan.records(start, end):
        if (
            row["dimension"] == args.dimension
            and _within([row[k] for k in "xyz"], args.area)
            and (player is None or row["actor"].get("uuid") == player)
            and (args.action is None or row["action"] == args.action)
        ):
            matches += 1
            if len(events) < args.limit:
                events.append(row)
    result = {
        "ok": True,
        "server": args.server,
        "dimension": args.dimension,
        "area": args.area,
        "matches": matches,
        "more_matches": matches > len(events),
        "coverage": scan.coverage(start, end),
        "entries": events,
    }
    if args.export:
        destination = config.private / "action-export.json"
        _write_private(destination, config.private, result)
        result["export"] = str(destination)
    if args.evidence:
        from omk.owner.action_evidence import preserve_case  # noqa: PLC0415

        result["evidence"] = str(preserve_case(config, args, result))
    return result
