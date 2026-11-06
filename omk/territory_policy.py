"""Prepare an exclusive, offline Core/FTB territory policy from owner environment."""

import os
import re
from pathlib import Path

POLICY_FILE = "omkalitycore-territories.properties"
FIELDS = {
    "OMK_DJ2_TERRITORIES_PER_MEMBER": ("regions_per_member", 3, 1, 50),
    "OMK_DJ2_CLAIM_REQUEST_CHUNKS": ("max_request_chunks", 1024, 1, 4096),
    "OMK_DJ2_TERRITORY_GRAPH_CHUNKS": ("max_graph_chunks", 20000, 50, 100000),
}


def territory_plan(environ=None):
    environment = os.environ if environ is None else environ
    result = {"schema": 1}
    for key, (field, default, low, high) in FIELDS.items():
        raw = environment.get(key, str(default))
        if not isinstance(raw, str) or not re.fullmatch(r"[0-9]{1,6}", raw):
            raise ValueError("Invalid territory policy setting: " + key)
        value = int(raw)
        if not low <= value <= high:
            raise ValueError("Territory policy setting out of range: " + key)
        result[field] = value
    return result


def write_territory_policy(config_directory: Path, environ=None):
    """Create a new file only. Existing policies and worlds are never modified."""
    plan = territory_plan(environ)
    directory = Path(config_directory)
    if not directory.is_dir() or any(
        p.is_symlink() or p.is_junction() for p in (directory, *directory.parents)
    ):
        raise ValueError("A real offline config directory is required")
    with (directory / POLICY_FILE).open("x", encoding="ascii", newline="\n") as file:
        file.write("# Offline staging only. FTB owns claims and permissions.\n")
        for key, value in plan.items():
            file.write(f"{key}={value}\n")
    return plan


def add_policy_commands(sub):
    policy = sub.add_parser("policy", help="Prepare new offline server policy files")
    actions = policy.add_subparsers(dest="policy_action", required=True)
    territories = actions.add_parser(
        "dj2-territories", help="FTB territories per team member"
    )
    territories.add_argument(
        "--config-directory",
        type=Path,
        help="Write exclusively into this existing staging directory",
    )


def run_policy(args):
    if args.policy_action != "dj2-territories":
        raise ValueError("Unknown policy")
    if args.config_directory is None:
        return {"ok": True, "policy": territory_plan(), "writes": False}
    return {
        "ok": True,
        "policy": write_territory_policy(args.config_directory),
        "file": str(args.config_directory / POLICY_FILE),
        "exclusive_create": True,
    }
