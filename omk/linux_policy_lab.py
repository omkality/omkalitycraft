"""Real Linux history/current-policy integration, with a reserved-name account."""

import time
from contextlib import ExitStack
from uuid import uuid4

from omk import admin_backups as owner
from omk.backup_store import BackupStore
from omk.dj2_commands_lab import _place, _response
from omk.dj2_lab import _accounts, _copy_server
from omk.dj2_linux_lab import LinuxServer, docker, inspect_owned
from omk.forge_player import LabPlayer
from omk.forge_probe import probe_login
from omk.linux_paths_lab import (
    Lab as PathsLab,
    run_linux_paths_lab,
)
from omk.managed_world_backup_lab import ManagedWorldBackups
from omk.stopped_world_backup import LAB_POLICY

FIRST, SECOND = "CON", "omk_other_test"
POLICY_FILES = (
    "ops.json banned-players.json banned-ips.json whitelist.json "
    "server.properties local/ftbutilities/ranks.txt"
)


class PolicyLab(PathsLab):
    PREFIX = "linux-policy-lab-"
    STATUS = "linux-policy-status.json"

    def start(self, server):
        if server is self.target:
            self.report["policy_prestart"] = self.restore_helper(
                "verify-policy", current_policy=True
            )
            self.check(
                self.report["policy_prestart"]["policy_verified"],
                "full_current_policy_verified_immediately_before_forge_start",
            )
        return super().start(server)

    def exercise(self):
        self.report["scope"] = (
            "historical Linux world plus current access/ranks/FTB, current Drasl unchanged; no production cutover"
        )
        dest, self.mods = _copy_server(self.args, self.root)
        self.client, _, self.session, self.guest = _accounts(
            self.compose, self.root, first_username=FIRST
        )
        self.source = LinuxServer(
            self.root, uuid4().hex[:10], self.compose[3] + "_default"
        )
        self.source.prepare(dest, self.args, self.client)
        self.seed_history(self.start(self.source))
        checkpoint = self.checkpoint()
        self.backups = ManagedWorldBackups(self.root)
        self.backups.enable_operator(checkpoint)
        self.snapshot = self.backups.publish(checkpoint, "before-grief")
        self.check(
            self.snapshot["verified"],
            "historical_owner_backup_verified_before_current_policy_changes",
        )
        inspect_owned("container", self.source.name, self.source.run_id)
        docker("rm", self.source.name)
        self.seed_current(self.start(self.source))
        current = self.checkpoint(name="current-checkpoint")
        exported = self.root / "current-policy-source"
        exported.mkdir()
        self.source.helper(
            "tar -C /srv -cf /export/policy.tar " + POLICY_FILES,
            export=exported,
            readonly_volume=True,
        )
        self.report["current_snapshot"] = self.backups.publish(
            current, "before-restore"
        )
        self.source_checkpoint = owner.checkpoint(
            owner.target_for(self.backups.operator, "dj2")
        )
        self.backups.copy_from_store("store", self.root / "backup-store")
        history = BackupStore(
            self.root / "backup-store", LAB_POLICY, path_policy="linux-server"
        ).inspect()
        self.check(
            len(history) == 2,
            "historical_and_latest_current_world_backups_exported_verified",
        )
        self.report["managed_backup_final"] = {"host_export_verified": True}
        self.report["snapshot"] = self.snapshot
        self.restore_and_play()

    def seed_history(self, console):
        console("op " + FIRST)
        console("gamemode 1 " + FIRST)
        with ExitStack() as stack:
            first, guest = [
                stack.enter_context(LabPlayer(self.client, session, 25576, self.mods))
                for session in (self.session, self.guest)
            ]
            _place(first, FIRST, (128.5, 241, 128.5), console)
            _response(first, "/team create policytest", "ftblib.lang.team.created")
            _response(
                first, "/team status " + SECOND + " ally", "commands.team.status.set"
            )
            first.command("/chunks claim")
            _response(first, "/sethome old", "ftbutilities.lang.homes.set")
            console("replaceitem entity CON slot.hotbar.8 minecraft:emerald 7")
            console("gamemode 1 " + SECOND)
            _place(guest, SECOND, (140.5, 241, 132.5), console)
            console("setblock 139 241 132 minecraft:stone")
            guest.dig(139, 241, 132)
            time.sleep(0.5)
            self.check(
                "Successfully found"
                in console("testforblock 139 241 132 minecraft:air"),
                "historical_ally_can_really_edit_claim",
            )

    def seed_current(self, console):
        with LabPlayer(self.client, self.session, 25576, self.mods) as first:
            _response(
                first, "/team status " + SECOND + " none", "commands.team.status.set"
            )
            _response(first, "/delhome old", "ftbutilities.lang.homes.del")
            console("replaceitem entity CON slot.hotbar.8 minecraft:emerald 1")
        for command in (
            "ranks setp player ftbutilities.homes.max 1",
            "deop CON",
            "whitelist add CON",
            "whitelist add " + SECOND,
            "whitelist on",
            "ban " + SECOND + " policy_fixture",
        ):
            console(command)
        self.check(True, "current_revoke_ban_whitelist_deop_and_home_quota_seeded")

    def restore_and_play(self):
        root = self.root / "replacement"
        root.mkdir()
        dest, _ = _copy_server(self.args, root)
        self.target = LinuxServer(root, uuid4().hex[:10], self.source.network)
        self.target.prepare(dest, self.args, self.client)
        self.operation = uuid4().hex
        self.restore_helper("initialize")
        self.report["stage"] = self.restore_helper("stage")
        self.report["policy_stage"] = self.restore_helper(
            "stage-policy", current_policy=True
        )
        # Capture the closed prestart target as opaque TAR, without NTFS extraction.
        exported = self.root / "policy-before-start"
        exported.mkdir()
        self.target.helper(
            "tar -C /srv -cf /export/policy.tar "
            + POLICY_FILES
            + " .omk-current-policy-plan.json .omk-current-policy-staged.json",
            export=exported,
            readonly_volume=True,
        )
        self.verify_game(self.start(self.target))

    def verify_game(self, console):
        self.check(
            not probe_login(self.client, self.guest, "127.0.0.1", 25576).authenticated,
            "current_ban_rejects_same_valid_drasl_session_after_restore",
        )
        with LabPlayer(self.client, self.session, 25576, self.mods) as first:
            _response(first, "/whitelist list", "commands.generic.permission")
            self.check(True, "historical_op_is_not_revived")
            _response(first, "/sethome extra", "ftbutilities.lang.homes.limit")
            self.check(True, "current_one_home_rank_applies_to_historical_saved_home")
            self.check(
                "Found "
                in console(
                    'testfor CON {Inventory:[{Slot:8b,id:"minecraft:emerald",Count:7}]}'
                ),
                "historical_inventory_restored_instead_of_current_one_emerald",
            )
            _place(first, FIRST, (140.5, 241, 140.5), console)
            first.command("/home old")
            first.wait(lambda: abs(first.position[0] - 128.5) < 1)
            self.check(True, "historical_home_really_teleports_with_current_policy")
        console("pardon " + SECOND)
        with LabPlayer(self.client, self.guest, 25576, self.mods):
            self.check(
                True, "explicit_pardon_allows_same_guest_session_positive_control"
            )
        console("whitelist remove " + SECOND)
        self.check(
            not probe_login(self.client, self.guest, "127.0.0.1", 25576).authenticated,
            "current_whitelist_enforced_after_restore",
        )
        console("whitelist add " + SECOND)
        self.verify_claim(console)
        console("ban " + SECOND + " policy_fixture")

    def verify_claim(self, console):
        with ExitStack() as stack:
            first, guest = [
                stack.enter_context(LabPlayer(self.client, session, 25576, self.mods))
                for session in (self.session, self.guest)
            ]
            for actor, name in ((first, FIRST), (guest, SECOND)):
                console("gamemode 1 " + name)
                _place(actor, name, (140.5, 241, 132.5), console)
            for x in (139, 144):
                console(f"setblock {x} 241 132 minecraft:stone")
            guest.dig(144, 241, 132)
            time.sleep(0.5)
            self.check(
                "Successfully found"
                in console("testforblock 144 241 132 minecraft:air"),
                "guest_can_edit_unclaimed_positive_control",
            )
            guest.dig(139, 241, 132)
            time.sleep(0.5)
            self.check(
                "Successfully found"
                in console("testforblock 139 241 132 minecraft:stone"),
                "revoked_ally_cannot_edit_historical_claim",
            )
            first.dig(139, 241, 132)
            time.sleep(0.5)
            self.check(
                "Successfully found"
                in console("testforblock 139 241 132 minecraft:air"),
                "non_op_owner_keeps_claim_access",
            )


def run_linux_policy_lab(args):
    return run_linux_paths_lab(args, lab_class=PolicyLab)
