"""Disposable Drasl + real HTTP incident inbox; no existing accounts, services or worlds."""

import contextlib
import io
import json
import os
import re
import secrets
import socket
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import psutil

from launcher.accounts import AccountService
from launcher.storage import FileSessionStore
from omk.admin import AdminError, load_operator_config, operator_login
from omk.diagnostics import BoundedLog, PipeLog
from omk.drasl import DraslClient, DraslError
from omk.incidents import capture_incident, submit_pending
from omk.profiles import PROJECT_ROOT
from omk.report_store import ReportStore


def _stop_api(process):
    if process is None or process.poll() is not None:
        return
    parent = psutil.Process(process.pid)
    children = parent.children(recursive=True)
    for child in children:
        with contextlib.suppress(psutil.Error):
            child.terminate()
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)
    _gone, alive = psutil.wait_procs(children, timeout=5)
    for child in alive:
        with contextlib.suppress(psutil.Error):
            child.kill()
    _gone, remaining = psutil.wait_procs(alive, timeout=5)
    if remaining:
        raise OSError("Owned API worker did not stop")


def _cleanup(api_process, stream, compose):
    clean = True
    try:
        _stop_api(api_process)
    except OSError, psutil.Error, subprocess.SubprocessError:
        clean = False
    try:
        if stream is not None:
            stream.close()
    except OSError:
        clean = False
    try:
        result = subprocess.run(
            [*compose, "down", "--timeout", "5"],
            capture_output=True,
            timeout=30,
            check=False,
        )
        return clean and result.returncode == 0
    except OSError, subprocess.SubprocessError:
        return False


def _start_api(lab, private, *, port=None):
    if port is None:
        with socket.socket() as reservation:
            reservation.bind(("127.0.0.1", 0))
            port = reservation.getsockname()[1]
    elif type(port) is not int or not 1024 <= port <= 65535:
        raise ValueError("Invalid owned API lab port")
    log = BoundedLog(lab / "api.log")
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "granian",
            "--interface",
            "asgi",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "api.app:app",
        ],
        cwd=lab,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        env={
            **os.environ,
            "PYTHONPATH": str(PROJECT_ROOT),
            "CONTENT_ROOT": str(lab / "empty-cdn"),
            "CLIENT_REPORTS_ROOT": str(private / "client-reports"),
            "CLIENT_REPORTS_AUTH_URL": "http://127.0.0.1:25586",
        },
    )
    return (
        process,
        PipeLog(process.stdout, log),
        DraslClient(f"http://127.0.0.1:{port}"),
    )


def _denied(operation, statuses):
    try:
        operation()
    except DraslError as error:
        if error.status in statuses:
            return
        raise RuntimeError("Unexpected rejection status") from None
    raise RuntimeError("An operation requiring rejection was accepted")


def _register_client(lab, config, client, admin_password, command, checked):
    operator_login(config, "omk_lab_admin", admin_password)
    checked("separate_operator_login_saves_no_password")
    result = command("access", "invite")
    invitation = json.loads(Path(result["invitation_file"]).read_text())["code"]
    portable = lab / "portable"
    service = AccountService(
        client, FileSessionStore(portable / "userdata/session.json")
    )
    registration = service.prepare_registration("omk_report_user", invitation)
    session = service.register(registration).session
    checked("operator_cli_invitation_registers_normal_player")
    _denied(
        lambda: client.register(
            "omk_reuse_user", secrets.token_urlsafe(24), invitation
        ),
        {400, 403},
    )
    checked("registration_invitation_is_single_use")
    _denied(
        lambda: client.request(
            "POST", "/drasl/api/v3/invites", {}, session.access_token
        ),
        {401, 403},
    )
    checked("game_token_cannot_issue_invitations")
    try:
        operator_login(config, "omk_report_user", registration.password)
    except AdminError:
        checked("normal_account_cannot_become_operator")
    else:
        raise RuntimeError("Normal account became an operator")
    return portable, session


def _exercise(lab, config, client, api, admin_password, checked):
    from omk.cli import main  # noqa: PLC0415

    def command(*args):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            status = main(
                ["admin", "--config", str(lab / ".omk-admin/operator.toml"), *args]
            )
        result = json.loads(output.getvalue())
        if status != 0:
            raise RuntimeError("Operator CLI lab action failed: " + args[0])
        return result

    portable, session = _register_client(
        lab, config, client, admin_password, command, checked
    )
    folder = portable / "instances/dj2"
    (folder / "crash-reports").mkdir(parents=True)
    (folder / "crash-reports/crash-lab.txt").write_text(
        "Fixture java.lang.TestException "
        + session.access_token
        + "\n at lab.Fixture.main(Fixture.java:1)\n"
        "-- System Details --\nprivate-system-sentinel",
        encoding="utf-8",
    )
    release = SimpleNamespace(
        pack_id="dj2", version="lab-fixture", minecraft="1.12.2", platform="windows-x64"
    )
    capture_incident(
        portable,
        folder,
        release,
        session,
        run_id=uuid4().hex,
        started_at=0,
        exit_code=1,
        memory_mb=6144,
        launcher="lab",
    )
    pending = next((portable / "userdata/client-incidents").glob("*.json"))
    report = json.loads(pending.read_text())
    operator_token = json.loads(config.auth_file.read_text())["api_token"]
    _denied(
        lambda: api.request("POST", "/reports/client", report, operator_token), {401}
    )
    checked("operator_api_key_is_not_accepted_as_a_game_token")
    submit_pending(portable, api.base_url, session)
    if pending.exists():
        raise RuntimeError("Client incident was not acknowledged")
    checked("automatic_queue_delivers_real_http_report_with_real_game_token")
    store = ReportStore(config.reports_root)
    saved = store.get(report["id"])
    if saved.get("verified_name") != session.player_name:
        raise RuntimeError("Verified client profile name is missing")
    if session.access_token in json.dumps(
        saved
    ) or "private-system-sentinel" in json.dumps(saved):
        raise RuntimeError("Client incident redaction failed")
    checked("stored_report_excludes_game_token_and_system_dump")
    _denied(
        lambda: api.request("GET", "/reports/client", token=session.access_token),
        {404, 405},
    )
    _denied(
        lambda: api.request(
            "GET", "/reports/client/" + report["id"], token=session.access_token
        ),
        {404, 405},
    )
    checked("players_cannot_list_or_read_client_reports_over_http")
    _denied(
        lambda: api.request(
            "POST",
            "/reports/client",
            {**report, "id": uuid4().hex, "player": uuid4().hex},
            session.access_token,
        ),
        {409},
    )
    checked("game_token_cannot_submit_report_under_another_uuid")
    listing = command("reports", "list")
    exported = command("reports", "export", "--id", report["id"])
    if (
        listing["count"] != 1
        or json.loads(Path(exported["report_file"]).read_text())["id"] != report["id"]
    ):
        raise RuntimeError("Operator report export failed")
    checked("operator_cli_reads_private_inbox_without_public_read_api")
    client.request(
        "POST",
        "/auth/invalidate",
        {"accessToken": session.access_token, "clientToken": session.client_token},
    )
    _denied(
        lambda: api.request(
            "POST",
            "/reports/client",
            {**report, "id": uuid4().hex},
            session.access_token,
        ),
        {401},
    )
    checked("revoked_game_token_cannot_upload_client_report")
    invite = command("access", "invite")
    code = json.loads(Path(invite["invitation_file"]).read_text())["code"]
    command("access", "revoke-invite", "--invitation-file", invite["invitation_file"])
    _denied(
        lambda: client.register("omk_revoked_user", secrets.token_urlsafe(24), code),
        {400, 403},
    )
    checked("operator_cli_revocation_blocks_registration")


def operator_smoke():
    lab = PROJECT_ROOT / ".local" / ("operator-lab-" + uuid4().hex[:8])
    private = lab / ".omk-admin"
    private.mkdir(parents=True, mode=0o700)
    auth_url = "http://127.0.0.1:25586"
    path = private / "operator.toml"
    path.write_text('schema=1\n[auth]\norigin="' + auth_url + '"\n', encoding="utf-8")
    config = load_operator_config(path)
    compose = [
        "docker",
        "compose",
        "--project-name",
        "omk-operator-lab-" + uuid4().hex[:10],
        "-f",
        str(PROJECT_ROOT / "deploy/auth-lab/compose.yaml"),
    ]
    report = {
        "ok": False,
        "checks": [],
        "cleanup": False,
        "lab_folder": str(lab.relative_to(PROJECT_ROOT)),
        "crash_source": "synthetic crash-report fixture; real HTTP and Drasl",
    }
    api_process = stream = None

    def checked(name):
        report["checks"].append(name)

    try:
        subprocess.run(
            [*compose, "up", "--detach", "--pull", "never"],
            capture_output=True,
            check=True,
            timeout=60,
        )
        client = DraslClient(auth_url)
        for _ in range(100):
            try:
                client.request("GET", "/authlib-injector")
                break
            except Exception:
                time.sleep(0.2)
        logs = subprocess.check_output(
            [*compose, "logs", "--no-color", "drasl"], text=True
        )
        bootstrap = re.search(r"invite=([A-Za-z0-9_-]+)", logs)[1]
        admin_password = secrets.token_urlsafe(24)
        client.register("omk_lab_admin", admin_password, bootstrap)
        api_process, stream, api = _start_api(lab, private)
        for _ in range(150):
            if api_process.poll() is not None:
                raise RuntimeError("Owned API process exited")
            try:
                api.request("GET", "/health")
                break
            except Exception:
                time.sleep(0.2)
        _exercise(lab, config, client, api, admin_password, checked)
        report["ok"] = True
    except Exception as error:
        report["error_type"] = type(error).__name__
        report["error"] = (
            str(error)
            if type(error) is RuntimeError
            else "Operator lab failed; inspect isolated state"
        )
    finally:
        report["cleanup"] = _cleanup(api_process, stream, compose)
        report["ok"] = report["ok"] and report["cleanup"]
        (lab / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report
