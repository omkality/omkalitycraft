"""A real reserved-name Drasl/Forge account and Linux-only backup round trip."""

import hashlib
import json
import subprocess
import tarfile
import traceback
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from omk.backup_store import BackupStore
from omk.dj2_commands_lab import _place, _response
from omk.dj2_lab import _accounts, _cleanup, _console_sender, _copy_server, _wait_server
from omk.dj2_linux_lab import LABEL, LinuxServer, docker, inspect_owned
from omk.forge_player import LabPlayer
from omk.managed_world_backup_lab import IMAGE, ManagedWorldBackups
from omk.profiles import PROJECT_ROOT
from omk.stopped_world_backup import LAB_POLICY


def add_linux_paths_lab(parser):
    for flag in ("server-source", "agent", "core", "mods-json"):
        parser.add_argument("--" + flag, type=Path, required=True)


class Lab:
    PREFIX = "linux-paths-lab-"
    STATUS = "linux-paths-status.json"

    def __init__(self, args):
        self.args = args
        self.root = PROJECT_ROOT / ".local" / (self.PREFIX + uuid4().hex[:10])
        self.root.mkdir()
        self.report = {
            "ok": False,
            "checks": [],
            "lab": str(self.root),
            "scope": "real CON account, Linux Forge and owner cold backup; no GUI or live data",
        }
        self.compose = [
            "docker",
            "compose",
            "--project-name",
            "omk-linux-paths-" + uuid4().hex[:8],
            "-f",
            str(PROJECT_ROOT / "deploy/auth-lab/compose.yaml"),
        ]
        self.source = self.target = self.backups = None

    def state(self, label):
        (PROJECT_ROOT / ".local" / self.STATUS).write_text(
            json.dumps({"phase": label, "report": self.report}), encoding="utf-8"
        )

    def check(self, condition, name):
        if not condition:
            raise ValueError(name)
        self.report["checks"].append(name)
        self.state(name)

    def start(self, server):
        process = server.start()
        _wait_server(process, server.log, self.state)
        return _console_sender(process, server.log)

    def checkpoint(self, *, name="source-checkpoint"):
        self.source.process.stdin.write(b"stop\n")
        self.source.process.stdin.flush()
        self.source.process.wait(timeout=60)
        self.source.collector.close()
        data = inspect_owned("container", self.source.name, self.source.run_id)
        self.check(
            data["State"]["ExitCode"] == 0 and not data["State"]["OOMKilled"],
            "source_clean_exit_without_oom",
        )
        export = self.root / name
        export.mkdir()
        self.source.helper(
            "tar -C /srv -cf /export/world.tar lab-world",
            export=export,
            readonly_volume=True,
        )
        with tarfile.open(export / "world.tar") as tar:
            entry = tar.getmember("lab-world/data/ftb_lib/players/con.dat")
            self.check(
                entry.isfile() and entry.size > 0, "real_ftb_con_dat_persisted_on_linux"
            )
        return SimpleNamespace(
            server=self.source,
            checkpoint_export=(
                export / "world.tar",
                hashlib.sha256((export / "world.tar").read_bytes()).hexdigest(),
            ),
        )

    def restore_helper(self, action, *, current_policy=False):
        for name, owner in (
            (self.target.volume, self.target.run_id),
            (self.backups.volume, self.backups.run),
        ):
            if inspect_owned("volume", name, owner) is None:
                raise ValueError("Missing owned restore volume")
        if (
            self.target.volume in {self.source.volume, self.backups.volume}
            or docker(
                "ps", "-q", "--filter", "volume=" + self.target.volume
            ).stdout.strip()
        ):
            raise ValueError("Restore target is active or aliases a source")
        request = {
            "action": action,
            "operation": self.operation,
            "world": "lab-world",
            "snapshot": self.snapshot["id"],
            "archive_sha256": self.snapshot["sha256"],
            "world_max_bytes": 512 * 1024**2,
            "policy": vars(LAB_POLICY),
        }
        mounts = []
        if current_policy:
            from omk import admin_backups as owner  # noqa: PLC0415

            if (
                self.source.process.poll() != 0
                or owner.checkpoint(owner.target_for(self.backups.operator, "dj2"))
                != self.source_checkpoint
            ):
                raise ValueError("Current source lifecycle changed before policy stage")
            mounts = [
                "--mount",
                f"type=volume,source={self.source.volume},target=/current,readonly",
            ]
            for filename in ("__init__.py", "nbt.py"):
                mounts += [
                    "--mount",
                    f"type=bind,source={PROJECT_ROOT/'launcher'/filename},target=/src/launcher/{filename},readonly",
                ]
        command = [
            "docker",
            "run",
            "--rm",
            "--pull",
            "never",
            "-i",
            "--name",
            "omk-linux-path-stage-" + uuid4().hex[:10],
            "--label",
            LABEL + "=" + self.target.run_id,
            "--network",
            "none",
            "--read-only",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges:true",
            "--memory",
            "512m",
            "--cpus",
            "1",
            "--pids-limit",
            "32",
            "--mount",
            f"type=volume,source={self.backups.volume},target=/backup,readonly",
            "--mount",
            f"type=volume,source={self.target.volume},target=/restore",
            "--mount",
            f"type=bind,source={PROJECT_ROOT/'omk'},target=/src/omk,readonly",
            *mounts,
            "--workdir",
            "/src",
            "--env",
            "PYTHONDONTWRITEBYTECODE=1",
            IMAGE,
            "python",
            "-m",
            "omk.linux_restore_policy" if current_policy else "omk.linux_world_restore",
        ]
        result = subprocess.run(
            command,
            input=json.dumps(request),
            text=True,
            capture_output=True,
            timeout=180,
            check=False,
        )
        value = json.loads(result.stdout)
        if result.returncode != 0 or value.get("ok") is not True:
            raise ValueError(
                "Linux restore helper refused: "
                + str(value.get("error_type", "InvalidResponse"))
            )
        if (
            current_policy
            and owner.checkpoint(owner.target_for(self.backups.operator, "dj2"))
            != self.source_checkpoint
        ):
            raise ValueError("Current source lifecycle changed during policy stage")
        return value

    def exercise(self):
        self.state("preparing_owned_linux_path_lab")
        dest, self.mods = _copy_server(self.args, self.root)
        self.client, _, self.session, _ = _accounts(
            self.compose, self.root, first_username="CON"
        )
        self.check(
            self.session.player_name.casefold() == "con",
            "real_drasl_registration_accepts_CON",
        )
        self.source = LinuxServer(
            self.root, uuid4().hex[:10], self.compose[3] + "_default"
        )
        self.source.prepare(dest, self.args, self.client)
        console = self.start(self.source)
        with LabPlayer(self.client, self.session, 25576, self.mods) as player:
            console("op CON")
            _place(player, "CON", (128.5, 241, 128.5), console)
            _response(player, "/sethome reserved", "ftbutilities.lang.homes.set")
            console("replaceitem entity CON slot.hotbar.8 minecraft:emerald 7")
            self.check(
                "Found "
                in console(
                    'testfor CON {Inventory:[{Slot:8b,id:"minecraft:emerald",Count:7}]}'
                ),
                "real_CON_forge_login_inventory_and_home_seeded",
            )
        recovery = self.checkpoint()
        self.backups = ManagedWorldBackups(self.root)
        self.backups.enable_operator(recovery)
        self.snapshot = self.backups.publish(recovery, "before-grief")
        self.check(
            self.snapshot["verified"], "owner_plan_run_backs_up_real_reserved_name"
        )
        self.backups.copy_from_store("store", self.root / "backup-store")
        history = BackupStore(
            self.root / "backup-store", LAB_POLICY, path_policy="linux-server"
        ).inspect()
        self.check(
            len(history) == 1 and history[0]["id"] == self.snapshot["id"],
            "opaque_linux_store_export_verifies_on_host_without_extracting_CON",
        )
        self.report["managed_backup_final"] = {"host_export_verified": True}
        self.report["snapshot"] = self.snapshot
        self.restore_and_play()

    def restore_and_play(self):
        root = self.root / "replacement"
        root.mkdir()
        dest, _ = _copy_server(self.args, root)
        self.target = LinuxServer(root, uuid4().hex[:10], self.source.network)
        self.target.prepare(dest, self.args, self.client)
        self.operation = uuid4().hex
        self.restore_helper("initialize")
        self.report["stage"] = self.restore_helper("stage")
        self.report["prestart"] = self.restore_helper("verify")
        self.check(
            self.report["prestart"]["verified"],
            "full_world_staged_and_reverified_inside_new_linux_volume",
        )
        console = self.start(self.target)
        with LabPlayer(self.client, self.session, 25576, self.mods) as player:
            self.check(
                "Found "
                in console(
                    'testfor CON {Inventory:[{Slot:8b,id:"minecraft:emerald",Count:7}]}'
                ),
                "CON_inventory_survives_linux_restore_and_rejoin",
            )
            _place(player, "CON", (140.5, 241, 140.5), console)
            player.command("/home reserved")
            player.wait(lambda: abs(player.position[0] - 128.5) < 1)
            self.check(True, "FTB_reads_restored_con_dat_and_home_really_teleports")

    def close(self):
        for key, server in (("source", self.source), ("replacement", self.target)):
            if server:
                result = self.report.setdefault(key, {"ok": True})
                server.close(result)
                self.report["ok"] &= result.get(
                    "owned_game_clean_exit", False
                ) and result.get("owned_volume_removed_after_export", False)
        if self.backups:
            self.backups.close(self.report)
        _cleanup(None, None, self.compose, self.report)


def run_linux_paths_lab(args, *, lab_class=Lab):
    for path in (args.core, args.agent, args.mods_json):
        if not path.is_file():
            raise ValueError("Required Linux paths lab artifact missing")
    lab = lab_class(args)
    try:
        lab.exercise()
        lab.report["ok"] = True
    except Exception as error:
        lab.report["error"] = type(error).__name__ + ": " + str(error)[:1000]
        lab.report["trace"] = [
            {"function": row.name, "line": row.lineno}
            for row in traceback.extract_tb(error.__traceback__)
        ]
    finally:
        lab.close()
        (lab.root / "report.json").write_text(
            json.dumps(lab.report, indent=2), encoding="utf-8"
        )
        lab.state("complete" if lab.report["ok"] else "failed")
    return lab.report
