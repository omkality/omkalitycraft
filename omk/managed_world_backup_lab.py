"""Linux-volume adapter for managed snapshots of fresh Forge recovery labs."""

import hashlib
import json
from uuid import uuid4

from omk.backup_store import BackupStore
from omk.dj2_linux_lab import LABEL, docker, inspect_owned
from omk.profiles import PROJECT_ROOT
from omk.stopped_world_backup import LAB_POLICY

IMAGE = "python:3.14.2-slim@sha256:1a3c6dbfd2173971abba880c3cc2ec4643690901f6ad6742d0827bae6cefc925"


class ManagedWorldBackups:
    def __init__(self, lab):
        self.lab, self.run = lab, uuid4().hex[:12]
        self.volume = "omk-managed-backups-" + self.run
        self.records = {}
        if docker("volume", "inspect", self.volume, check=False).returncode == 0:
            raise ValueError("A new backup volume is required")
        docker("volume", "create", "--label", LABEL + "=" + self.run, self.volume)

    def verify_source(self, recovery):
        server = recovery.server
        if (
            server.process is None
            or server.process.poll() != 0
            or recovery.checkpoint_export is None
        ):
            raise ValueError(
                "Managed snapshot requires verified stopped Forge checkpoint"
            )
        if inspect_owned("volume", server.volume, server.run_id) is None:
            raise ValueError("Missing owned source volume")
        if docker("ps", "-q", "--filter", "volume=" + server.volume).stdout.strip():
            raise ValueError("Source volume is still in use by a running container")
        if inspect_owned("volume", self.volume, self.run) is None:
            raise ValueError("Missing owned backup volume")

    def helper(self, recovery, action):
        self.verify_source(recovery)
        result = docker(
            "run",
            "--rm",
            "--pull",
            "never",
            "--network",
            "none",
            "--name",
            self.volume + "-helper",
            "--label",
            LABEL + "=" + self.run,
            "--memory",
            "512m",
            "--cpus",
            "1",
            "--pids-limit",
            "32",
            "--read-only",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges:true",
            "--mount",
            f"type=volume,source={recovery.server.volume},target=/server,readonly",
            "--mount",
            f"type=volume,source={self.volume},target=/backup",
            "--mount",
            f"type=bind,source={PROJECT_ROOT / 'omk'},target=/src/omk,readonly",
            "--workdir",
            "/src",
            "--env",
            "PYTHONDONTWRITEBYTECODE=1",
            IMAGE,
            "python",
            "-m",
            "omk.stopped_world_backup",
            action,
            timeout=180,
        )
        return json.loads(result.stdout)

    def publish(self, recovery, name):
        if name in self.records:
            raise ValueError("Checkpoint already published")
        result = self.helper(recovery, "publish")
        self.records[name] = result
        return result

    def copy_from_store(self, relative, destination):
        if destination.exists():
            raise ValueError("Managed export must not overwrite existing evidence")
        if inspect_owned("volume", self.volume, self.run) is None:
            raise ValueError(
                "Missing owned backup volume; never create one during export"
            )
        name = self.volume + "-export"
        docker(
            "create",
            "--name",
            name,
            "--network",
            "none",
            "--label",
            LABEL + "=" + self.run,
            "--mount",
            f"type=volume,source={self.volume},target=/backup,readonly",
            IMAGE,
        )
        try:
            if inspect_owned("container", name, self.run) is None:
                raise ValueError("Export container missing")
            docker("cp", name + ":/backup/" + relative, str(destination), timeout=180)
        finally:
            if inspect_owned("container", name, self.run) is not None:
                docker("rm", name)

    def restore_source(self, recovery):
        verified = self.helper(recovery, "inspect")["snapshots"]
        record = self.records["before-grief"]
        if not any(row["id"] == record["id"] for row in verified):
            raise ValueError("Requested managed backup is no longer retained")
        path = self.lab / "backups/managed-full-return.zip"
        self.copy_from_store("store/" + record["id"] + "/archive.zip", path)
        self.copy_from_store(
            "store/" + record["id"] + "/manifest.json", path.with_suffix(".json")
        )
        with path.open("rb") as file:
            if hashlib.file_digest(file, "sha256").hexdigest() != record["sha256"]:
                raise ValueError("Managed restore source hash mismatch")
        return path, record["sha256"]

    def finish(self, recovery):
        result = self.helper(recovery, "finish")
        self.copy_from_store("store", self.lab / "managed-store")
        verified = BackupStore(self.lab / "managed-store", LAB_POLICY).inspect()
        if verified != result["history"]:
            raise ValueError("Host backup export differs from Linux store")
        return {**result, "host_export_verified": True}

    def close(self, report):
        try:
            if report.get("ok") and report.get("managed_backup_final", {}).get(
                "host_export_verified"
            ):
                inspect_owned("volume", self.volume, self.run)
                docker("volume", "rm", self.volume)
                report["managed_backup_volume_removed_after_export"] = True
            else:
                report["managed_backup_volume_retained"] = self.volume
        except Exception as error:
            report["ok"] = False
            report["managed_backup_cleanup_error"] = type(error).__name__
            report["managed_backup_volume_retained"] = self.volume
