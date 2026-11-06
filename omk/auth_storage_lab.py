"""Real persistent Drasl Docker acceptance, using only newly owned resources."""

import hashlib
import json
import os
import re
import secrets
import socket
import stat
import subprocess
import time
from urllib.error import URLError
from urllib.parse import urlencode
from uuid import uuid4

from omk.auth_config import render_config
from omk.drasl import DraslClient
from omk.lab import _expect_denied, skin_fixture
from omk.profiles import PROJECT_ROOT

HELPER = "python:3.14.2-slim@sha256:1a3c6dbfd2173971abba880c3cc2ec4643690901f6ad6742d0827bae6cefc925"
IMAGE = "omkalitycraft-drasl:4.0.0-omk.2"
LABEL = "omkality.auth.storage-lab"


class StorageLab:
    def __init__(self):
        self.run = uuid4().hex[:12]
        self.project = "omk-auth-storage-" + self.run
        self.root = PROJECT_ROOT / ".local" / ("auth-storage-" + self.run)
        self.root.mkdir(parents=True)
        (self.root / "backup").mkdir(mode=0o700)
        self.volumes = []
        self.projects = []
        self.report = {"ok": False, "checks": [], "lab": str(self.root)}
        with socket.socket() as port:
            port.bind(("127.0.0.1", 0))
            self.port = port.getsockname()[1]
        self.origin = f"http://127.0.0.1:{self.port}"
        self.client = DraslClient(self.origin)
        self.config = self.root / "config.toml"
        self.config.write_text(
            render_config(
                {"OMK_AUTH_URL": self.origin, "OMK_AUTH_ADMIN": "omk_lab_admin"}
            ),
            encoding="utf-8",
        )
        self.environment = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith(("OMK_AUTH_", "COMPOSE_"))
        }
        self.environment.update(
            OMK_AUTH_CONFIG=str(self.config), OMK_AUTH_HTTP_PORT=str(self.port)
        )

    def docker(self, *args, stdin=None, check=True):
        result = subprocess.run(
            ["docker", *args],
            input=stdin,
            text=True,
            capture_output=True,
            timeout=90,
            env=self.environment,
            check=False,
        )
        if check and result.returncode:
            raise RuntimeError("Owned auth storage Docker operation failed: " + args[0])
        return result

    def compose(self, project, file, *args):
        return self.docker(
            "compose", "--project-name", project, "--file", str(file), *args
        )

    def check(self, condition, name):
        if not condition:
            raise RuntimeError("Auth storage check failed: " + name)
        self.report["checks"].append(name)

    def volume(self, suffix):
        name = self.project + "-" + suffix
        # Never adopt any existing name, even one with a matching label.
        if self.docker("volume", "inspect", name, check=False).returncode == 0:
            raise RuntimeError("Lab volume already exists")
        self.docker("volume", "create", "--label", LABEL + "=" + self.run, name)
        self.volumes.append(name)
        return name

    def owned_volume(self, name):
        data = json.loads(self.docker("volume", "inspect", name).stdout)[0]
        if data.get("Labels", {}).get(LABEL) != self.run:
            raise RuntimeError("Refusing an unowned volume")

    def entrypoint(self, suffix, volume, *, staging=False):
        self.owned_volume(volume)
        name = self.project + "-" + suffix
        service = (
            PROJECT_ROOT
            / "deploy/auth"
            / ("service.yaml" if staging else "compose.yaml")
        )
        spec = {
            "services": {
                "drasl": {
                    "extends": {"file": str(service), "service": "drasl"},
                    "labels": {LABEL: self.run},
                }
            },
            "volumes": {"drasl-state": {"external": True, "name": volume}},
        }
        if staging:
            spec["services"]["drasl"]["volumes"] = [
                {
                    "type": "bind",
                    "source": str(self.config),
                    "target": "/etc/drasl/config.toml",
                    "read_only": True,
                }
            ]
        file = self.root / (suffix + ".json")
        file.write_text(json.dumps(spec), encoding="utf-8")
        self.projects.append((name, file))
        return name, file

    def start(self, scope, *, staging=False):
        self.compose(*scope, "up", "--detach", "--no-build", "--pull", "never")
        cid = self.compose(*scope, "ps", "-q", "drasl").stdout.strip()
        data = json.loads(self.docker("inspect", cid).stdout)[0]
        self.check(data["Config"]["Labels"].get(LABEL) == self.run, "owned_" + scope[0])
        mounts = [m for m in data["Mounts"] if m["Destination"] == "/var/lib/drasl"]
        self.check(
            len(mounts) == 1 and mounts[0]["Type"] == "volume",
            "persistent_mount_" + scope[0],
        )
        self.check(
            data["HostConfig"]["ReadonlyRootfs"]
            and data["HostConfig"]["Memory"] == 384 * 1024**2
            and not data["Config"]["Env"].count("DRASL_DEBUG=false"),
            "runtime_limits_" + scope[0],
        )
        if staging:
            self.check(
                not data["HostConfig"].get("PortBindings"),
                "restore_has_no_published_ports",
            )
        else:
            for _ in range(80):
                try:
                    self.client.request("GET", "/authlib-injector")
                    break
                except URLError, TimeoutError, ConnectionError:
                    time.sleep(0.25)
            else:
                raise RuntimeError("Owned auth service not ready")
        if self.report.get("drasl_image_id", data["Image"]) != data["Image"]:
            raise RuntimeError("Drasl image changed during the acceptance run")
        self.report["drasl_image_id"] = data["Image"]
        self.report["drasl_image_tag"] = IMAGE
        return cid

    def stop(self, scope):
        self.compose(*scope, "stop", "--timeout", "20")
        cid = self.compose(*scope, "ps", "-aq", "drasl").stdout.strip()
        data = json.loads(self.docker("inspect", cid).stdout)[0]
        self.check(
            not data["State"]["Running"]
            and data["State"]["ExitCode"] == 0
            and not data["State"]["OOMKilled"],
            "clean_stop_" + scope[0],
        )

    def helper(self, volume, module, action):
        self.owned_volume(volume)
        if self.docker("ps", "-q", "--filter", "volume=" + volume).stdout.strip():
            raise RuntimeError(
                "Offline helper refuses a volume used by a running container"
            )
        result = self.docker(
            "run",
            "--rm",
            "--pull",
            "never",
            "--network",
            "none",
            "--label",
            LABEL + "=" + self.run,
            "--memory",
            "256m",
            "--cpus",
            "1",
            "--read-only",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges:true",
            "--mount",
            f"type=volume,source={volume},target=/state",
            "--mount",
            f"type=volume,source={self.backup_volume},target=/backup",
            "--mount",
            f"type=bind,source={PROJECT_ROOT / 'omk'},target=/src/omk,readonly",
            "--workdir",
            "/src",
            "--env",
            "PYTHONDONTWRITEBYTECODE=1",
            HELPER,
            "python",
            "-m",
            module,
            action,
        )
        return json.loads(result.stdout)

    def export_backup(self):
        self.owned_volume(self.backup_volume)
        name = self.project + "-export"
        self.docker(
            "create",
            "--name",
            name,
            "--network",
            "none",
            "--label",
            LABEL + "=" + self.run,
            "--mount",
            f"type=volume,source={self.backup_volume},target=/backup,readonly",
            HELPER,
        )
        try:
            data = json.loads(self.docker("inspect", name).stdout)[0]
            if (
                data["Config"]["Labels"].get(LABEL) != self.run
                or data["State"]["Running"]
            ):
                raise RuntimeError("Refusing an unowned or running export container")
            # Docker client writes as the invoking host user. No privileged helper
            # needs access to the host's mode-0700, non-root-owned private folder.
            for file in ("state.tar", "state.json"):
                self.docker(
                    "cp", name + ":/backup/" + file, str(self.root / "backup" / file)
                )
                if os.name == "posix":
                    exported = (self.root / "backup" / file).stat()
                    if (
                        exported.st_uid != os.getuid()
                        or stat.S_IMODE(exported.st_mode) != 0o600
                    ):
                        raise RuntimeError(
                            "Exported backup ownership or permissions are unsafe"
                        )
            from omk.auth_state_archive import digest  # noqa: PLC0415

            self.check(
                digest(self.root / "backup/state.tar")
                == self.report["snapshot"]["sha256"],
                "exported_backup_matches_snapshot",
            )
        finally:
            self.docker("rm", name)

    def cleanup(self):
        clean = True
        for scope in reversed(self.projects):
            try:
                self.compose(*scope, "down", "--timeout", "20")
            except RuntimeError:
                clean = False
        if clean:
            for volume in self.volumes:
                self.owned_volume(volume)
                clean &= (
                    self.docker("volume", "rm", volume, check=False).returncode == 0
                )
        return clean


def _fixture(lab):
    logs = lab.compose(*lab.original, "logs", "--no-color", "drasl").stdout
    invite = re.search(r"invite=([A-Za-z0-9_-]+)", logs)
    if invite is None:
        raise RuntimeError("No bootstrap invitation")
    admin = lab.client.register("omk_lab_admin", secrets.token_urlsafe(32), invite[1])
    token = admin["apiToken"]
    invite = lab.client.request("POST", "/drasl/api/v3/invites", {}, token)["code"]
    password = secrets.token_urlsafe(32)
    user = lab.client.register("omk_storage", password, invite)
    # Retain an unused invitation to test rollback of admission revocations too.
    unused = lab.client.request("POST", "/drasl/api/v3/invites", {}, token)["code"]
    player = user["user"]["players"][0]["uuid"]
    lab.client.upload_skin(player, user["apiToken"], skin_fixture(), "slim")
    game = lab.client.authenticate("omk_storage", password, uuid4().hex)
    server = secrets.token_hex(20)
    lab.client.request(
        "POST",
        "/session/minecraft/join",
        {
            "accessToken": game["accessToken"],
            "selectedProfile": game["selectedProfile"]["id"],
            "serverId": server,
        },
    )
    return {
        "admin": admin,
        "user": user,
        "password": password,
        "unused": unused,
        "game": game,
        "server": server,
        "player": player,
    }


def _identity(lab, fixture):
    user = lab.client.user(fixture["user"]["apiToken"])
    skin = lab.client.skin_profile(fixture["player"])
    return {
        "account": user["uuid"],
        "profile": user["players"][0]["uuid"],
        "skin": hashlib.sha256(skin[0]).hexdigest(),
        "model": skin[1],
        "public_key": lab.client.request("GET", "/authlib-injector")[
            "signaturePublickey"
        ],
    }


def _quarantine(lab, scope, cid, fixture):
    new_password = secrets.token_urlsafe(32)
    # Same isolated container namespace; no host port and no password on disk/argv/env.
    request = json.dumps(
        {
            "origin": "http://127.0.0.1:25585",
            "token": fixture["admin"]["apiToken"],
            "password": new_password,
        }
    )
    result = lab.docker(
        "run",
        "--rm",
        "--pull",
        "never",
        "-i",
        "--network",
        "container:" + cid,
        "--label",
        LABEL + "=" + lab.run,
        "--read-only",
        "--memory",
        "256m",
        "--cpus",
        "1",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges:true",
        "--mount",
        f"type=bind,source={PROJECT_ROOT / 'omk'},target=/src/omk,readonly",
        "--workdir",
        "/src",
        "--env",
        "PYTHONDONTWRITEBYTECODE=1",
        HELPER,
        "python",
        "-m",
        "omk.auth_restore_quarantine",
        stdin=request,
    )
    lab.report["quarantine"] = json.loads(result.stdout)
    lab.stop(scope)
    return new_password


def _exercise(lab):
    source, target = lab.volume("original"), lab.volume("restored")
    lab.backup_volume = lab.volume("backup")
    lab.original = lab.entrypoint("original", source)
    lab.start(lab.original)
    fixture = _fixture(lab)
    before = _identity(lab, fixture)
    lab.stop(lab.original)
    lab.compose(*lab.original, "down", "--timeout", "20")  # Deliberately no -v.
    lab.owned_volume(source)
    lab.start(lab.original)
    lab.check(
        _identity(lab, fixture) == before,
        "recreate_preserves_uuid_skin_model_signing_key",
    )
    lab.client.request(
        "POST",
        "/auth/validate",
        {key: fixture["game"][key] for key in ("accessToken", "clientToken")},
    )
    lab.check(True, "recreate_preserves_remembered_game_session")
    lab.client.login("omk_storage", fixture["password"])
    lab.check(True, "recreate_preserves_password_hash")
    cid = lab.compose(*lab.original, "ps", "-q", "drasl").stdout.strip()
    lab.docker("kill", "--signal", "KILL", cid)
    data = json.loads(lab.docker("inspect", cid).stdout)[0]
    lab.check(
        data["State"]["ExitCode"] == 137 and not data["State"]["OOMKilled"],
        "owned_sigkill_is_injected_not_oom",
    )
    lab.start(lab.original)
    lab.check(
        _identity(lab, fixture) == before, "sigkill_preserves_identity_skin_and_key"
    )
    fixture["game"] = lab.client.refresh(
        fixture["game"]["accessToken"], fixture["game"]["clientToken"]
    )
    lab.check(True, "sigkill_preserves_remembered_session")
    lab.stop(lab.original)
    lab.report["snapshot"] = lab.helper(source, "omk.auth_state_archive", "snapshot")
    lab.export_backup()
    lab.report["restore"] = lab.helper(target, "omk.auth_state_archive", "restore")
    # Simulate a revocation AFTER the backup. A blind restore would undo it.
    lab.start(lab.original)
    lab.client.request(
        "PATCH",
        "/drasl/api/v3/users/" + fixture["user"]["user"]["uuid"],
        {"isLocked": True},
        fixture["admin"]["apiToken"],
    )
    lab.stop(lab.original)
    stage = lab.entrypoint("quarantine", target, staging=True)
    cid = lab.start(stage, staging=True)
    new_owner_password = _quarantine(lab, stage, cid, fixture)
    lab.compose(*stage, "down", "--timeout", "20")
    lab.report["browser_sessions"] = lab.helper(
        target, "omk.auth_state_browser", "clear"
    )
    cutover = lab.entrypoint("restored", target)
    lab.start(cutover)
    _accept_restore(lab, fixture, before, new_owner_password)


def _accept_restore(lab, fixture, before, owner_password):
    for token in (fixture["admin"]["apiToken"], fixture["user"]["apiToken"]):
        _expect_denied(lambda token=token: lab.client.user(token), {401, 403})
    _expect_denied(
        lambda: lab.client.request(
            "POST",
            "/auth/validate",
            {key: fixture["game"][key] for key in ("accessToken", "clientToken")},
        ),
        {400, 401, 403},
    )
    _expect_denied(
        lambda: lab.client.request(
            "GET",
            "/session/minecraft/hasJoined?"
            + urlencode({"username": "omk_storage", "serverId": fixture["server"]}),
        ),
        {400, 401, 403, 404},
    )
    _expect_denied(
        lambda: lab.client.login("omk_storage", fixture["password"]), {400, 401, 403}
    )
    lab.check(True, "restore_cannot_revive_old_api_game_join_or_password_access")
    admin = lab.client.login("omk_lab_admin", owner_password)["apiToken"]
    invites = lab.client.request("GET", "/drasl/api/v3/invites", token=admin)
    lab.check(not invites, "restore_cannot_revive_unused_invitation")
    _expect_denied(
        lambda: lab.client.register(
            "omk_old_invite", secrets.token_urlsafe(32), fixture["unused"]
        ),
        {400, 403},
    )
    user = lab.client.request(
        "GET", "/drasl/api/v3/users/" + before["account"], token=admin
    )
    lab.check(
        user["isLocked"] is True and user["players"][0]["uuid"] == before["profile"],
        "restored_player_retains_identity_and_stays_locked",
    )
    password = secrets.token_urlsafe(32)
    lab.client.request(
        "PATCH",
        "/drasl/api/v3/users/" + user["uuid"],
        {"password": password, "isLocked": False},
        admin,
    )
    fresh = lab.client.login("omk_storage", password)
    previous_api = fixture["user"]["apiToken"]
    fixture["user"] = fresh
    lab.check(
        _identity(lab, fixture) == before,
        "safe_restore_preserves_uuid_skin_and_signing_key",
    )
    game = lab.client.authenticate("omk_storage", password, uuid4().hex)
    lab.check(
        game["selectedProfile"]["id"].replace("-", "")
        == fixture["player"].replace("-", ""),
        "owner_can_restore_access_to_same_player",
    )
    lab.client.request(
        "POST",
        "/auth/validate",
        {key: game[key] for key in ("accessToken", "clientToken")},
    )
    _expect_denied(
        lambda: lab.client.refresh(
            fixture["game"]["accessToken"], fixture["game"]["clientToken"]
        ),
        {400, 401, 403},
    )
    _expect_denied(
        lambda: lab.client.login("omk_storage", fixture["password"]), {400, 401, 403}
    )
    _expect_denied(lambda: lab.client.user(previous_api), {401, 403})
    lab.check(True, "old_credentials_remain_invalid_after_player_unlock")


def run_auth_storage_lab():
    lab = StorageLab()
    try:
        _exercise(lab)
        lab.report["ok"] = True
    except Exception as error:
        lab.report["error"] = type(error).__name__  # No credentials or HTTP bodies.
    finally:
        lab.report["cleanup"] = lab.cleanup()
        lab.report["ok"] &= lab.report["cleanup"]
        (lab.root / "report.json").write_text(
            json.dumps(lab.report, indent=2), encoding="utf-8"
        )
    return lab.report
