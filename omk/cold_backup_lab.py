"""Real Docker/owner CLI faults, with synthetic data only; no Minecraft process."""

import json
import os
import subprocess
import sys
from uuid import uuid4

from omk import admin_backups as owner
from omk.admin import AdminError, load_operator_config
from omk.profiles import PROJECT_ROOT

LABEL = "omkality.cold-backup.lab"
ENV = {
    "OMK_BACKUP_MAX_BYTES": str(128 * 1024**2),
    "OMK_BACKUP_STAGING_BYTES": str(64 * 1024**2),
    "OMK_BACKUP_RESERVE_BYTES": str(16 * 1024**2),
    "OMK_BACKUP_WORLD_MAX_BYTES": str(32 * 1024**2),
    "OMK_BACKUP_MAX_COUNT": "2",
}


class Lab:
    def __init__(self):
        self.run = uuid4().hex[:12]
        self.root = PROJECT_ROOT / ".local" / ("cold-backups-" + self.run)
        self.root.mkdir()
        self.source = "omk-cold-source-" + self.run
        self.data = "omk-cold-data-" + self.run
        self.containers = []
        self.volumes = []
        self.report = {
            "ok": False,
            "checks": [],
            "lab": str(self.root),
            "scope": "real Docker and owner CLI, synthetic world/runtime; not Minecraft",
        }

    def volume(self, kind):
        name = "omk-cold-" + kind + "-" + self.run
        names = owner.docker("volume", "ls", "--format", "{{.Name}}").splitlines()
        if name in names:
            raise RuntimeError("Lab resource already exists")
        owner.docker("volume", "create", "--label", LABEL + "=" + self.run, name)
        self.volumes.append(name)
        return name

    def configure(self, kind, store):
        private = self.root / kind / ".omk-admin"
        private.mkdir(parents=True, mode=0o700)
        cfg = private / "operator.toml"
        cfg.write_text('schema=1\n[servers.dj2]\nroot="../runtime"\n')
        target = {
            "container": self.source,
            "data_volume": self.data,
            "store_volume": store,
            "label": LABEL,
            "source_owner": self.run,
            "store_owner": self.run,
            "world": "world",
            "image": owner.IMAGE,
            "release": "synthetic-v1",
        }
        (private / "backups.toml").write_text(
            "schema=1\n[servers.dj2]\n"
            + "\n".join(k + "=" + json.dumps(v) for k, v in target.items())
        )
        cfg.chmod(0o600)
        (private / "backups.toml").chmod(0o600)
        return load_operator_config(cfg), cfg

    def seed(self):
        self.data = self.volume("data")
        self.containers.append(self.source)
        script = (
            'from pathlib import Path; p=Path("/srv/world"); p.mkdir(exist_ok=True); '
            '(p/"level.dat").write_bytes(b"synthetic-level"); '
            'Path("/srv/server.properties").write_text("fixture=true"); '
            'Path("/srv/server.jar").write_bytes(b"synthetic-runtime"); print("Stopping server",flush=True)'
        )
        owner.docker(
            "run",
            "--name",
            self.source,
            "--network",
            "none",
            "--label",
            LABEL + "=" + self.run,
            "--read-only",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges:true",
            "--memory",
            "128m",
            "--cpus",
            "1",
            "--pids-limit",
            "32",
            "--log-driver",
            "local",
            "--log-opt",
            "max-size=2m",
            "--log-opt",
            "max-file=2",
            "--mount",
            f"type=volume,source={self.data},target=/srv",
            owner.IMAGE,
            "python",
            "-c",
            script,
        )

    def check(self, condition, name):
        if not condition:
            raise RuntimeError(name)
        self.report["checks"].append(name)

    def children(self, cfg, op):
        processes = [
            subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "omk",
                    "admin",
                    "--config",
                    str(cfg),
                    "backups",
                    "run",
                    "--operation",
                    op,
                ],
                env={**os.environ, **ENV},
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            for _ in range(2)
        ]
        values = []
        for process in processes:
            raw, _ = process.communicate(timeout=90)
            values.append(json.loads(raw))
        self.check(
            sum(value["ok"] for value in values) == 1,
            "concurrent_owner_cli_has_one_success",
        )

    def exercise(self):
        self.seed()
        store = self.volume("store")
        config, path = self.configure("positive", store)
        plan = owner.plan(config, "dj2", ENV)
        self.children(path, plan["operation"])
        first = owner._read_json(
            owner.journal(config, plan["operation"]), config.private
        )
        self.check(
            first["stage"] == "complete" and first["result"]["sequence"] == 1,
            "race_publishes_exactly_one_snapshot",
        )
        plan = owner.plan(config, "dj2", ENV)
        script = (
            "import os,sys; from pathlib import Path; from omk import admin_backups as b; "
            "from omk.admin import load_operator_config; c=load_operator_config(Path(sys.argv[1])); "
            'original=b.save\ndef fail(c,r,s):\n if s=="published": os._exit(73)\n '
            "return original(c,r,s)\nb.save=fail; b.run(c,sys.argv[2])"
        )
        child = subprocess.run(
            [sys.executable, "-c", script, str(path), plan["operation"]],
            env={**os.environ, **ENV},
            capture_output=True,
            timeout=90,
            check=False,
        )
        self.check(
            child.returncode == 73 and not child.stdout and not child.stderr,
            "controller_exits_before_publication_acknowledgement",
        )
        record = owner._read_json(
            owner.journal(config, plan["operation"]), config.private
        )
        self.check(
            record["stage"] == "publishing", "uncertain_publication_remains_in_journal"
        )
        try:
            owner.run(config, plan["operation"], environment=ENV)
        except AdminError:
            pass
        else:
            raise RuntimeError("Normal run repeated an uncertain transaction")
        result = owner.run(config, plan["operation"], finish=True, environment=ENV)
        self.check(
            result["snapshot"]["sequence"] == 2,
            "explicit_finish_recovers_committed_snapshot_without_republication",
        )
        plan = owner.plan(config, "dj2", ENV)
        result = owner.run(config, plan["operation"], environment=ENV)
        self.check(
            result["snapshot"]["sequence"] == 3 and result["snapshot"]["retired"] == 1,
            "third_snapshot_rotates_only_oldest",
        )
        self.restart_case()
        self.large_case()

    def large_case(self):
        owner.docker(
            "run",
            "--rm",
            "--network",
            "none",
            "--memory",
            "128m",
            "--cpus",
            "1",
            "--mount",
            f"type=volume,source={self.data},target=/srv",
            owner.IMAGE,
            "python",
            "-c",
            (
                'from pathlib import Path; f=Path("/srv/world/large-fixture.dat").open("wb"); '
                "f.truncate(600*1024**2); f.close()"
            ),
        )
        config, _ = self.configure("large", self.volume("large-store"))
        limits = {
            **ENV,
            "OMK_BACKUP_WORLD_MAX_BYTES": str(1024**3),
            "OMK_BACKUP_STAGING_BYTES": str(2 * 1024**3),
            "OMK_BACKUP_MAX_BYTES": str(4 * 1024**3),
        }
        plan = owner.plan(config, "dj2", limits)
        self.check(
            plan["source"]["expanded_bytes"] > 512 * 1024**2,
            "real_sparse_world_exceeds_old_512m_lab_limit",
        )
        result = owner.run(config, plan["operation"], environment=limits)
        self.check(
            result["stage"] == "complete",
            "configured_expanded_limit_streams_600m_without_large_memory_buffer",
        )

    def restart_case(self):
        store = self.volume("restart-store")
        config, _ = self.configure("restart", store)
        plan = owner.plan(config, "dj2", ENV)
        actual = owner.worker

        def restarting(target, request):
            result = actual(target, request)
            if request["action"] == "prepare":
                owner.docker("start", "--attach", self.source)
            return result

        owner.worker = restarting
        try:
            try:
                owner.run(config, plan["operation"], environment=ENV)
            except AdminError:
                pass
            else:
                raise RuntimeError("Restarted source was published")
        finally:
            owner.worker = actual
        record = owner._read_json(
            owner.journal(config, plan["operation"]), config.private
        )
        value = actual(record["target"], owner.request_for(record, "list"))
        self.check(
            record["stage"] == "incomplete"
            and value["history"] == []
            and value["pending"],
            "source_restart_blocks_publication_and_preserves_staging",
        )
        result = owner.cancel(config, plan["operation"])
        self.check(
            result["previous_history_unchanged"],
            "explicit_cancel_removes_only_unpublished_staging",
        )
        next_plan = owner.plan(config, "dj2", ENV)
        result = owner.run(config, next_plan["operation"], environment=ENV)
        self.check(
            result["snapshot"]["sequence"] == 1,
            "fresh_backup_succeeds_after_safe_cancel",
        )

    def cleanup(self):
        for name in reversed(self.containers):
            rows = json.loads(owner.docker("inspect", "--type", "container", name))
            if rows[0]["Config"]["Labels"].get(LABEL) != self.run:
                return False
            owner.docker("rm", "--force", name)
        for name in reversed(self.volumes):
            row = json.loads(owner.docker("volume", "inspect", name))[0]
            if row["Labels"].get(LABEL) != self.run:
                return False
            owner.docker("volume", "rm", name)
        return True


def run_cold_backup_lab():
    lab = Lab()
    try:
        lab.exercise()
        lab.report["ok"] = True
    except Exception as error:
        lab.report["error_type"] = type(error).__name__
    finally:
        lab.report["cleanup"] = lab.cleanup()
        lab.report["ok"] &= lab.report["cleanup"]
        (lab.root / "report.json").write_text(json.dumps(lab.report, indent=2))
    return lab.report
