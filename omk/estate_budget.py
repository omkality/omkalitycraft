"""Conservative observations against a declared project budget, never a quota."""

BUCKET = {
    "active_world": "worlds",
    "retained_world_generations": "staging",
    "game_logs": "logs",
    "crash_reports": "logs",
    "pack_backups": "backups",
    "runtime_and_other": "system",
    "store": "backups",
    "reset": "staging",
    "restore": "staging",
    "auth": "system",
    "content": "content",
    "reports": "logs",
    "exports": "staging",
}


def declared_limits(plan, operation_policy, server_count):
    """Compare this invocation's declared caps, without inferring old store policy."""
    backups = plan["budgets_gib"]["backups"] * 1024**3
    worlds = plan["budgets_gib"]["worlds"] * 1024**3
    staging = plan["budgets_gib"]["staging"] * 1024**3
    checks = {
        "backup_caps_fit_project": server_count * operation_policy["max_bytes"]
        <= backups,
        "world_caps_fit_project": server_count * operation_policy["world_max_bytes"]
        <= worlds,
        "single_operation_staging_fits_project": operation_policy["staging_bytes"]
        <= staging,
    }
    return {
        "server_count": server_count,
        "per_server_backup_cap_bytes": operation_policy["max_bytes"],
        "sum_backup_caps_bytes": server_count * operation_policy["max_bytes"],
        "sum_world_caps_bytes": server_count * operation_policy["world_max_bytes"],
        "single_operation_staging_bytes": operation_policy["staging_bytes"],
        "checks": checks,
        "compatible": all(checks.values()),
        "scope": "current-invocation-environment",
        "existing_store_policy_read": False,
    }


def assess(report, plan):
    if not plan.get("ok"):
        raise ValueError("Project budget is invalid")
    categories = {
        key: {
            "apparent_bytes": 0,
            "allocated_bytes": 0,
            "charged_bytes": 0,
            "unattributed_charge_bytes": 0,
            "limit_bytes": value * 1024**3,
        }
        for key, value in plan["budgets_gib"].items()
        if key != "reserve"
    }
    by_id = {}
    for resource in report["resources"]:
        allocated = 0
        for name, value in resource["categories"].items():
            bucket = categories[BUCKET[name]]
            apparent, actual = value["apparent_bytes"], value["allocated_bytes"]
            if any(type(n) is not int or n < 0 for n in [apparent, actual]):
                raise ValueError("Invalid project volume accounting")
            bucket["apparent_bytes"] += apparent
            bucket["allocated_bytes"] += actual
            bucket["charged_bytes"] += max(apparent, actual)
            allocated += actual
        if resource["id"] in by_id:
            raise ValueError("Duplicate project resource")
        by_id[resource["id"]] = allocated
    reserve = plan["budgets_gib"]["reserve"] * 1024**3
    filesystems, observed = [], set()
    for entry in report["filesystems"]:
        identifiers = entry["resources"]
        if (
            not identifiers
            or set(identifiers) - set(by_id)
            or observed & set(identifiers)
            or len(set(identifiers)) != len(identifiers)
        ):
            raise ValueError("Project filesystem inventory is ambiguous")
        observed.update(identifiers)
        filesystems.append(
            {
                **entry,
                "reserve_bytes": reserve,
                "below_reserve": entry["available_bytes"] < reserve,
                "unattributed_or_reserved_bytes": max(
                    0,
                    entry["total_bytes"]
                    - entry["available_bytes"]
                    - sum(by_id[i] for i in identifiers),
                ),
            }
        )
    if observed != set(by_id):
        raise ValueError("Project filesystem inventory is incomplete")
    # Unclassified host usage and filesystem-reserved blocks still occupy this
    # disk. Charge them conservatively without claiming to have classified them.
    unknown = sum(f["unattributed_or_reserved_bytes"] for f in filesystems)
    categories["system"]["unattributed_charge_bytes"] = unknown
    categories["system"]["charged_bytes"] += unknown
    for bucket in categories.values():
        bucket["over_budget"] = bucket["charged_bytes"] > bucket["limit_bytes"]
    evaluable = len(filesystems) == 1
    disk_exceeded = (
        evaluable and plan["disk_gib"] * 1024**3 > filesystems[0]["total_bytes"]
    )
    return {
        "categories": categories,
        "filesystems": filesystems,
        "single_filesystem_budget_evaluable": evaluable,
        "planned_disk_exceeds_observed_filesystem": disk_exceeded,
        "observed_within_limits": evaluable
        and not disk_exceeded
        and not any(v["over_budget"] for v in categories.values())
        and not any(v["below_reserve"] for v in filesystems),
        "declared_disk_bytes": plan["disk_gib"] * 1024**3,
        "enforced": False,
        "admission_approved": False,
        "host_disk_complete": False,
    }
