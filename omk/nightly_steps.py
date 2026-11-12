"""Small recovery steps for a single nightly transaction, under the owner lock."""

from datetime import datetime, timedelta

from omk import (
    admin_backups as backups,
    admin_maintenance as maintenance,
    ingress,
    nightly_cycle as cycle,
)
from omk.admin import AdminError


def child(config, r, kind, env):
    operation = r["children"][kind]
    if kind == "maintenance":
        path = maintenance.journal(config, operation)
        if not path.exists():
            maintenance.plan(config, r["server"], env, _operation=operation)
        value = maintenance.read_record(config, operation)
        matches = (
            value["target"] == r["target"]
            and value["binding"] == r["binding"]
            and value["settings"] == r["settings"]["maintenance"]
            and value["initial"] == r["initial"]
            and value["runtime"]["runtime_sha256"] == r["disk"]["runtime_sha256"]
            and value["ingress"] == r["gate"]
            and value["operator_root"] == r["operator_root"]
        )
    elif kind == "backup":
        path = backups.journal(config, operation)
        if not path.exists():
            backups.plan(config, r["server"], env, _operation=operation)
        value = backups.read_record(config, operation)
        window = maintenance.read_record(config, r["children"]["maintenance"])
        matches = (
            value["target"] == r["target"]
            and value["settings"] == r["settings"]["backup"]
            and value["operator_root"] == r["operator_root"]
            and value["checkpoint"] == window["checkpoint"]
            and value["source"]["runtime_sha256"] == r["disk"]["runtime_sha256"]
        )
    else:
        wanted = "closed" if kind == "close" else "open"
        path = ingress.journal(config, operation)
        if not path.exists():
            ingress.plan(config, r["server"], wanted, env, _operation=operation)
        value = ingress.read(config, operation)
        matches = (
            value["wanted"] == wanted
            and value["deployment"] == r["gate"]
            and value["lifecycle"] == r["settings"]["maintenance"]
        )
    if (
        not matches
        or value["operation"] != operation
        or value["server"] != r["server"]
        or (
            datetime.fromisoformat(value["created_at"])
            < datetime.fromisoformat(r["created_at"])
        )
    ):
        raise AdminError("Nightly child journal differs from its preallocated scope")
    return value


def gate(config, r, kind, env):
    value = child(config, r, kind, env)
    if value["stage"] == "planned":
        ingress.execute(config, value["operation"], "apply")
    elif value["stage"] in {"applying", "confirmed"}:
        ingress.execute(config, value["operation"], "verify")
    else:
        raise AdminError(
            "Nightly ingress child was cancelled; owner inspection required"
        )


def warnings(config, r, env):
    values = r["settings"]["calendar"]["warnings_seconds"]
    deadline = datetime.fromisoformat(r["deadline"])
    clock = cycle.now()
    if len(r["warned"]) == len(values):
        if clock < deadline:
            return (deadline - clock).total_seconds()
        if (clock - deadline).total_seconds() > r["settings"]["warning_grace_seconds"]:
            raise AdminError(
                "Nightly countdown expired while inactive; cancel and start a fresh warning cycle"
            )
        cycle.running(config, r, env)
        r["admission"] = cycle.admission(config, r, env)
        cycle.save(config, r, "closing")
        return 0
    seconds = values[len(r["warned"])]
    due = deadline - timedelta(seconds=seconds)
    if clock < due:
        return (due - clock).total_seconds()
    if (clock - due).total_seconds() > r["settings"]["warning_grace_seconds"]:
        raise AdminError(
            "Nightly warning was missed; cancel and start a fresh countdown"
        )
    # Waiting has no external effect. Recheck identity/boot/runtime when a
    # notice becomes due, not by rescanning the entire pack every second.
    cycle.running(config, r, env)
    cycle.save(config, r, "warning-requested")
    cycle.console(config, r).warn(r["loaded"]["boot"], r["operation"], seconds)
    # Even a late/replayed acknowledgement cannot shorten the remaining warning.
    r["deadline"] = max(deadline, cycle.now() + timedelta(seconds=seconds)).isoformat()
    r["warned"].append(seconds)
    cycle.save(config, r, "warnings")
    return 0


def stopping(config, r, env):
    cycle.frozen(config, r, env, closed=True)
    value = child(config, r, "maintenance", env)
    if value["stage"] == "planned":
        fresh(r)
        cycle.running(config, r, env, closed=True)
        maintenance.execute(config, value["operation"], "stop", environment=env)
    elif value["stage"] == "stop-requested":
        maintenance.execute(config, value["operation"], "reconcile", environment=env)
    elif value["stage"] != "stopped":
        raise AdminError("Nightly maintenance child is not a recoverable stop")
    cycle.stopped(config, r, env)
    cycle.save(config, r, "backing-up")


def backing_up(config, r, env):
    cycle.stopped(config, r, env)
    r["admission"] = cycle.admission(config, r, env)
    value = child(config, r, "backup", env)
    if value["stage"] == "planned":
        backups.run(config, value["operation"], environment=env)
    elif (
        value["stage"] in {"publishing", "published", "acknowledging", "incomplete"}
        and "prepared" in value
    ):
        backups.run(config, value["operation"], finish=True, environment=env)
    elif value["stage"] != "complete":
        raise AdminError(
            "Nightly backup has no safe publication to recover; inspect its retained staging"
        )
    cycle.save(config, r, "starting")


def starting(config, r, env):
    cycle.frozen(config, r, env, closed=True)
    value = child(config, r, "maintenance", env)
    backup = child(config, r, "backup", env)
    if backup["stage"] != "complete":
        raise AdminError("Nightly backup is not complete")
    if value["stage"] == "stopped":
        cycle.stopped(config, r, env)
        maintenance.execute(
            config,
            value["operation"],
            "start",
            backup_operation=backup["operation"],
            environment=env,
        )
    elif value["stage"] == "start-requested":
        maintenance.execute(config, value["operation"], "reconcile", environment=env)
    elif value["stage"] != "complete":
        raise AdminError("Nightly maintenance has no recoverable start")
    value = child(config, r, "maintenance", env)
    source, _ = cycle.frozen(config, r, env, closed=True)
    loaded = cycle.console(config, r).ready(r["disk"]["adapter"])
    if (
        value["backup_operation"] != backup["operation"]
        or source != value["resumed"]
        or loaded["boot"] == r["loaded"]["boot"]
    ):
        raise AdminError(
            "Nightly resumed source or loaded boot differs from its completed maintenance"
        )
    cycle.disk(config, r, post_start=True)
    r["resumed"] = {"source": source, "loaded": loaded}
    cycle.save(config, r, "opening")


def fresh(r):
    if (cycle.now() - datetime.fromisoformat(r["deadline"])).total_seconds() > r[
        "settings"
    ]["warning_grace_seconds"]:
        raise AdminError(
            "Nightly countdown is stale; cancel before stop and start a fresh warning cycle"
        )


def advance(config, r, environment=None):
    _settings, env = cycle.policy(environment)
    if r["stage"] == "created":
        cycle.running(config, r, env)
        value = child(config, r, "maintenance", env)
        if value["stage"] != "planned":
            raise AdminError("Nightly initial maintenance was already attempted")
        r["deadline"] = (
            cycle.now()
            + timedelta(seconds=r["settings"]["calendar"]["warnings_seconds"][0])
        ).isoformat()
        cycle.save(config, r, "warnings")
    elif r["stage"] in {"warnings", "warning-requested"}:
        return warnings(config, r, env)
    elif r["stage"] == "closing":
        cycle.running(config, r, env)
        path = ingress.journal(config, r["children"]["close"])
        if not path.exists() or ingress.read(config, path.stem)["stage"] == "planned":
            fresh(r)
        gate(config, r, "close", env)
        cycle.save(config, r, "stopping")
    elif r["stage"] == "stopping":
        stopping(config, r, env)
    elif r["stage"] == "backing-up":
        backing_up(config, r, env)
    elif r["stage"] == "starting":
        starting(config, r, env)
    elif r["stage"] == "opening":
        cycle.running(config, r, env, resumed=True)
        gate(config, r, "open", env)
        cycle.running(config, r, env, resumed=True)
        cycle.save(config, r, "complete")
    else:
        raise AdminError("Unsupported nightly stage")
    return 0
