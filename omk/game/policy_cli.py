"""Owner policy preparation commands; no running-server operations."""

from pathlib import Path

from omk.game.territory_policy import territory_plan, write_territory_policy
from omk.worlds.border_policy import border_plan, prepare_borders
from omk.worlds.resource_policy import (
    prepare_resource_bundle,
    resource_generator_bundle,
    resource_plan,
)


def add_policy_commands(sub):
    actions = sub.add_parser(
        "policy", help="Prepare new offline server policies"
    ).add_subparsers(dest="policy_action", required=True)
    territories = actions.add_parser(
        "dj2-territories", help="FTB territories per team member"
    )
    territories.add_argument(
        "--config-directory",
        type=Path,
        help="Create only a new file in this staging directory",
    )
    resource = actions.add_parser(
        "dj2-resource", help="Prepare an isolated resource-world configuration bundle"
    )
    resource.add_argument(
        "--output",
        type=Path,
        help="Create a new bundle directory; existing paths are refused",
    )
    resource.add_argument(
        "--source-config",
        type=Path,
        help="Read DJ2 config to include a validated generator config copy",
    )
    borders = actions.add_parser(
        "dj2-borders", help="Prepare the reviewed DJ2 world border configuration"
    )
    borders.add_argument("--world-name", required=True)
    borders.add_argument("--output", type=Path)
    borders.add_argument("--source-config", type=Path)
    borders.add_argument("--mods-directory", type=Path)


def run_policy(args):
    if args.policy_action == "dj2-borders":
        if args.output is None:
            if args.source_config is not None or args.mods_directory is not None:
                raise ValueError("Border configuration inputs require --output")
            return {"ok": True, "policy": border_plan(args.world_name), "writes": False}
        if args.source_config is None or args.mods_directory is None:
            raise ValueError(
                "Border staging requires --source-config and --mods-directory"
            )
        return {
            "ok": True,
            "bundle": prepare_borders(
                args.output, args.source_config, args.mods_directory, args.world_name
            ),
            "output": str(args.output),
        }
    if args.policy_action == "dj2-resource":
        if args.output is None:
            plan = resource_plan()
            if args.source_config is not None:
                resource_generator_bundle(args.source_config, plan)
            return {"ok": True, "policy": plan, "writes": False}
        return {
            "ok": True,
            "bundle": prepare_resource_bundle(
                args.output, source_config=args.source_config
            ),
            "output": str(args.output),
        }
    if args.policy_action != "dj2-territories":
        raise ValueError("Unknown policy")
    if args.config_directory is None:
        return {"ok": True, "policy": territory_plan(), "writes": False}
    return {
        "ok": True,
        "policy": write_territory_policy(args.config_directory),
        "file": str(args.config_directory / "omkalitycore-territories.properties"),
        "exclusive_create": True,
    }
