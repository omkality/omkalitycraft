"""Real Minecraft crash -> offline queue -> real Drasl/API -> private operator export."""

import contextlib
import hashlib
import io
import json
import time
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

from launcher.releases import inside
from omk.client_crash_fixture import (
    CANARY,
    COMPILER_SHA256,
    COMPILER_SOURCE,
    CrashLabRunner,
    build_crash_agent,
)
from omk.dj2_commands_lab import FIRST
from omk.dj2_lab import _accounts, _copy_server, _stop_game, _wait_server, approved_mods
from omk.dj2_linux_lab import LinuxServer, clone_client
from omk.operator_lab import _cleanup, _denied, _start_api, _stop_api
from omk.profiles import PROJECT_ROOT
from omk.report_store import ReportStore


def add_client_crash_lab(parser):
    for name in (
        "server-source",
        "agent",
        "core",
        "mods-json",
        "client-source",
        "manifest",
        "compiler",
    ):
        parser.add_argument("--" + name, type=Path, required=True)


class ClientCrashLab:
    def __init__(self, args):
        self.args = args
        self.lab = PROJECT_ROOT / ".local" / ("client-crash-lab-" + uuid4().hex[:10])
        self.lab.mkdir()
        self.private = self.lab / ".omk-admin"
        self.private.mkdir(mode=0o700)
        self.project = "omk-client-crash-" + uuid4().hex[:10]
        self.compose = [
            "docker",
            "compose",
            "--project-name",
            self.project,
            "-f",
            str(PROJECT_ROOT / "deploy/auth-lab/compose.yaml"),
        ]
        self.server = LinuxServer(self.lab, uuid4().hex[:10], self.project + "_default")
        self.api_process = self.api_stream = self.game = None
        self.report = {
            "ok": False,
            "checks": [],
            "lab_folder": str(self.lab.relative_to(PROJECT_ROOT)),
            "crash_source": (
                "real graphical DJ2 client, controlled lab-only agent requests a Minecraft crash; "
                "not a spontaneous mod failure"
            ),
        }

    def state(self, phase):
        (PROJECT_ROOT / ".local/client-crash-status.json").write_text(
            json.dumps({"phase": phase, "report": self.report}), encoding="utf-8"
        )

    def checked(self, name, condition=True):
        if not condition:
            raise RuntimeError(name)
        self.report["checks"].append(name)
        self.state(name)

    def start_api(self, *, port=None):
        self.api_process, self.api_stream, self.api = _start_api(
            self.lab, self.private, port=port
        )
        for _ in range(150):
            if self.api_process.poll() is not None:
                raise RuntimeError("Owned incident API exited")
            try:
                self.api.request("GET", "/health")
                return
            except Exception:
                time.sleep(0.2)
        raise RuntimeError("Owned incident API readiness timed out")

    def prepare(self):
        approved_mods(self.args.mods_json)
        self.state("verifying_and_cloning_signed_client")
        self.root, self.folder, self.release = clone_client(self.args, self.lab)
        self.checked("fresh_client_files_match_signed_release")
        self.fixture = build_crash_agent(
            inside(self.folder, self.release.launch["java"]),
            self.args.compiler,
            self.lab,
        )
        self.report["fixture"] = {
            "compiler_sha256": COMPILER_SHA256,
            "compiler_source": COMPILER_SOURCE,
            "agent_sha256": hashlib.sha256(self.fixture.read_bytes()).hexdigest(),
            "source_sha256": hashlib.sha256(
                (PROJECT_ROOT / "tests/fixtures/ClientCrashAgent.java").read_bytes()
            ).hexdigest(),
        }
        self.client, self.service, self.session, _ = _accounts(self.compose, self.lab)
        config = self.private / "operator.toml"
        config.write_text(
            'schema=1\n[auth]\norigin="http://127.0.0.1:25586"\n[reports]\nroot="client-reports"\n',
            encoding="utf-8",
        )
        self.start_api()
        self.report_url = self.api.base_url
        dest, _ = _copy_server(self.args, self.lab)
        self.report["linux_java_runtime"] = self.server.prepare(
            dest, self.args, self.client
        )
        _wait_server(self.server.start(), self.server.log, self.state)
        self.checked("full_linux_dj2_server_ready")

    def launch(self):
        self.marker = self.lab / "request-client-crash"
        self.runner = CrashLabRunner(
            self.root,
            fixture=self.fixture,
            marker=self.marker,
            reports_url=self.report_url,
        )
        mark = self.server.log.stat().st_size
        self.session = self.service.renew_for_game()
        self.game = self.runner.start(
            self.release,
            self.folder,
            self.session,
            server=("127.0.0.1", 25576),
        )
        self.state("real_graphical_client_loading")
        deadline = time.monotonic() + 900
        while time.monotonic() < deadline:
            if self.game.poll() is not None:
                raise RuntimeError("Client exited before controlled crash")
            with self.server.log.open("rb") as log:
                log.seek(mark)
                if FIRST + " joined the game" in log.read().decode(
                    "utf-8", errors="replace"
                ):
                    self.checked("real_windows_dj2_client_joined_linux_server")
                    return
            time.sleep(1)
        raise RuntimeError("Real graphical client join timed out")

    def crash_offline(self):
        _stop_api(self.api_process)
        self.api_stream.close()
        self.checked("owned_incident_api_stopped_before_game_crash")
        self.marker.write_text(
            "controlled lab-only Minecraft crash\n", encoding="ascii"
        )
        self.state("awaiting_real_minecraft_crash_report")
        deadline = time.monotonic() + 60
        paths = []
        while time.monotonic() < deadline and self.game.poll() is None:
            paths = list((self.root / "userdata/client-incidents").glob("*.json"))
            if paths:
                break
            time.sleep(0.5)
        self.checked(
            "recoverable_minecraft_crash_did_not_exit_the_game",
            self.game.poll() is None,
        )
        self.checked(
            "automatic_report_was_captured_while_game_still_running", bool(paths)
        )
        self.checked(
            "game_stdout_collection_did_not_fail", not self.game.logging_failed.is_set()
        )
        self.checked("offline_crash_saved_exactly_one_pending_report", len(paths) == 1)
        self.pending = paths[0]
        value = json.loads(self.pending.read_text(encoding="utf-8"))
        self.checked(
            "live_report_does_not_invent_an_exit_code",
            value["schema"] == 2
            and value["process_state"] == "running"
            and value["exit_code"] is None,
        )
        self.report_id = value["id"]
        self.verify_report(value, "queued")
        self.checked(
            "offline_report_kind_is_minecraft_crash", value["kind"] == "minecraft_crash"
        )
        crashes = list((self.folder / "crash-reports").glob("crash-*.txt"))
        self.checked("minecraft_itself_created_a_raw_crash_report", bool(crashes))
        self.report["raw_crash_sha256"] = hashlib.sha256(
            crashes[0].read_bytes()
        ).hexdigest()

    def verify_report(self, value, prefix):
        text = json.dumps(value)
        self.checked(
            prefix + "_controlled_exception_and_stack_preserved",
            "ControlledClientCrash" in value["detail"]
            and "ClientCrashAgent" in value["detail"],
        )
        self.checked(
            prefix + "_canary_tokens_paths_and_system_dump_not_exported",
            all(
                s not in text
                for s in (
                    CANARY,
                    self.session.access_token,
                    self.session.client_token,
                    str(self.root),
                    "-- System Details --",
                )
            ),
        )

    def deliver(self):
        self.start_api(port=urlsplit(self.report_url).port)
        self.checked(
            "incident_api_restarted_at_same_origin",
            self.api.base_url == self.report_url,
        )
        (self.lab / "request-client-exit").write_text(
            "normal controlled lab shutdown\n", encoding="ascii"
        )
        self.game.process.wait(timeout=60)
        self.report["client_exit_code"] = self.game.poll()
        self.checked(
            "real_client_closes_cleanly_after_recoverable_crash", self.game.poll() == 0
        )
        self.checked(
            "game_runner_completed_exit_diagnostics_and_retry",
            self.game.diagnostics_done.wait(30),
        )
        self.checked(
            "queued_report_removed_only_after_real_http_ack", not self.pending.exists()
        )
        store = ReportStore(self.private / "client-reports")
        saved = store.get(self.report_id)
        self.checked(
            "real_drasl_verified_account_for_received_crash",
            saved["verified_name"] == self.session.player_name,
        )
        self.verify_report(saved, "received")
        self.runner.send_reports(self.session, background=False)
        self.checked(
            "repeated_delivery_does_not_duplicate_report", len(store.list()) == 1
        )
        _denied(
            lambda: self.api.request(
                "GET", "/reports/client", token=self.session.access_token
            ),
            {404, 405},
        )
        self.checked("player_game_token_cannot_read_the_inbox")
        self.operator_export()

    def operator_export(self):
        from omk.cli import main  # noqa: PLC0415

        for action in ("list", "export"):
            args = [
                "admin",
                "--config",
                str(self.private / "operator.toml"),
                "reports",
                action,
            ]
            if action == "export":
                args += ["--id", self.report_id]
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                status = main(args)
            result = json.loads(output.getvalue())
            self.checked("private_operator_" + action + "_succeeds", status == 0)
            self.checked(
                "operator_stdout_contains_paths_only_" + action,
                "detail" not in result
                and "ControlledClientCrash" not in output.getvalue(),
            )
        exported = json.loads(
            (self.private / "report-exports" / (self.report_id + ".json")).read_text(
                encoding="utf-8"
            )
        )
        self.checked(
            "operator_export_contains_the_real_client_crash",
            exported["id"] == self.report_id
            and "ControlledClientCrash" in exported["detail"],
        )

    def run(self):
        try:
            self.prepare()
            self.launch()
            self.crash_offline()
            self.deliver()
            self.report["ok"] = True
        except Exception as error:
            self.report["error_type"] = type(error).__name__
            self.report["error"] = (
                str(error)[:300]
                if type(error) is RuntimeError
                else "Inspect the isolated lab state"
            )
        finally:
            _stop_game(self.game)
            self.server.close(self.report)
            self.report["temporary_api_and_auth_removed"] = _cleanup(
                self.api_process, self.api_stream, self.compose
            )
            self.report["ok"] = (
                self.report["ok"]
                and self.report["temporary_api_and_auth_removed"]
                and self.report.get("owned_game_clean_exit", False)
            )
            (self.lab / "report.json").write_text(
                json.dumps(self.report, indent=2), encoding="utf-8"
            )
            self.state("complete" if self.report["ok"] else "failed")
        return self.report


def run_client_crash_lab(args):
    return ClientCrashLab(args).run()
