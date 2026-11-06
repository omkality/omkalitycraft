"""Real owner CLI over the reserved-name Linux DJ2 current-policy scenario."""

import json
import os
import subprocess
import sys
from uuid import uuid4

from omk import admin_backups
from omk.dj2_lab import _copy_server
from omk.dj2_linux_lab import JAVA_IMAGE, LABEL, LinuxServer
from omk.linux_paths_lab import (
    Lab as PathsLab,
    run_linux_paths_lab,
)
from omk.linux_policy_lab import POLICY_FILES, PolicyLab


class OwnerRestoreLab(PolicyLab):
    PREFIX = "owner-restore-lab-"
    STATUS = "owner-restore-status.json"
    PRESERVE_FAILED_SOURCE = True

    def runtime_artifacts(self):
        script = (
            "import json; from pathlib import Path; from omk.cold_backup_worker import runtime_files; "
            "a=runtime_files(Path('/current')); b=runtime_files(Path('/restore')); "
            "names={n for n in a.keys()|b.keys() if n.endswith('.jar')}; "
            "print(json.dumps({n:{'source':a.get(n),'target':b.get(n)} for n in names if a.get(n)!=b.get(n)}))"
        )
        result = admin_backups.docker(
            "run",
            "--rm",
            "--pull",
            "never",
            "--network",
            "none",
            "--read-only",
            "--memory",
            "512m",
            "--cpus",
            "1",
            "--cap-drop",
            "ALL",
            "--mount",
            f"type=volume,source={self.source.volume},target=/current,readonly",
            "--mount",
            f"type=volume,source={self.target.volume},target=/restore,readonly",
            "--mount",
            f"type=bind,source={self.root.parent.parent/'omk'},target=/src/omk,readonly",
            "--workdir",
            "/src",
            "--env",
            "PYTHONDONTWRITEBYTECODE=1",
            admin_backups.IMAGE,
            "python",
            "-c",
            script,
            timeout=180,
        )
        self.report["runtime_artifact_diff"] = json.loads(result)
        self.state("runtime_artifact_inventory_before_owner_plan")

    def cli(self, action, *, success=True):
        args = (
            ["--server", "dj2", "--snapshot", self.snapshot["id"]]
            if action == "plan"
            else ["--operation", self.operation]
        )
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "omk",
                "admin",
                "--config",
                str(self.backups.operator.private / "operator.toml"),
                "restores",
                action,
                *args,
            ],
            env={**os.environ, **self.backups.operator_environment},
            capture_output=True,
            text=True,
            timeout=1800,
            check=False,
        )
        value = json.loads(result.stdout)
        if value.get("ok") is not success:
            raise ValueError(
                "Owner restore CLI outcome differs: "
                + action
                + " "
                + str(value.get("error", ""))
            )
        return value

    def start(self, server):
        if server is self.target:
            self.report["owner_prestart"] = self.cli("verify")
            self.check(
                self.report["owner_prestart"]["staged"]
                and not self.report["owner_prestart"]["promoted"],
                "owner_cli_full_verify_immediately_before_forge_start",
            )
        return PathsLab.start(self, server)

    def restore_and_play(self):
        self.report["scope"] = (
            "owner CLI stages historical Linux world with current rights; no production cutover or GUI"
        )
        root = self.root / "replacement"
        root.mkdir()
        dest, _ = _copy_server(self.args, root)
        self.target = LinuxServer(root, uuid4().hex[:10], self.source.network)
        self.target.prepare(dest, self.args, self.client)
        self.runtime_artifacts()
        entry = {
            "data_volume": self.target.volume,
            "owner": self.target.run_id,
            "label": LABEL,
            "image": JAVA_IMAGE,
            "release": "dj2-2.23.4-candidate",
        }
        path = self.backups.operator.private / "restores.toml"
        path.write_text(
            "schema=1\n[servers.dj2]\n"
            + "\n".join(k + "=" + json.dumps(v) for k, v in entry.items())
        )
        path.chmod(0o600)
        self.report["owner_plan"] = self.cli("plan")
        self.operation = self.report["owner_plan"]["operation"]
        self.check(
            self.report["owner_plan"]["expected"]["current_snapshot"]
            == self.report["current_snapshot"]["id"],
            "owner_plan_requires_latest_backup_of_actual_current_world",
        )
        self.report["owner_apply"] = self.cli("apply")
        self.check(
            self.report["owner_apply"]["staged"],
            "real_owner_cli_apply_stages_historical_world_and_current_rights",
        )
        self.cli("apply", success=False)
        self.check(True, "second_owner_cli_apply_refused_without_retry")
        self.check(
            self.cli("status")["stage"] == "staged",
            "owner_cli_status_remains_staged_after_refused_repeat",
        )
        exported = self.root / "policy-before-start"
        exported.mkdir()
        self.target.helper(
            "tar -C /srv -cf /export/policy.tar "
            + POLICY_FILES
            + " .omk-current-policy-plan.json .omk-current-policy-staged.json"
            + " .omk-owner-restore-plan.json .omk-owner-restore-staged.json",
            export=exported,
            readonly_volume=True,
        )
        self.verify_game(self.start(self.target))


def run_owner_restore_lab(args):
    return run_linux_paths_lab(args, lab_class=OwnerRestoreLab)
