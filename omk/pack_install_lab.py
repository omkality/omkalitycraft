"""Owned signed-pack transport regression; never starts Minecraft or uses accounts."""

import contextlib
import json
import shutil
import socket
import threading
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit
from uuid import uuid4

from launcher.client_defaults import prepare_client_defaults
from launcher.install import Installer, ReleaseClient, current_platform
from launcher.mod_policy import clean_extra_mods, verify_mods
from launcher.nbt import Tag, read_nbt, write_nbt
from launcher.releases import (
    MAX_MANIFEST_BYTES,
    ReleaseError,
    inside,
    read_release,
    sha256_file,
)
from omk.profiles import PROJECT_ROOT


class PackDirectory:
    def __init__(self, path, keys):
        self.root = Path(path).resolve()
        with (self.root / "manifest.json").open("rb") as stream:
            self.release = read_release(stream.read(MAX_MANIFEST_BYTES + 1), keys)
        self.files = {f.path: f for f in self.release.files}

    def verify(self):
        for artifact in self.files.values():
            path = inside(self.root / "files", artifact.path)
            if not path.is_file() or sha256_file(path) != artifact.sha256:
                raise ValueError("Invalid source artifact: " + artifact.path)


class PackWire:
    """Only signed allowlisted files, on loopback; one bounded short-body fault."""

    def __init__(self, source):
        self.source = source
        self.drop_path = None
        self.fault_path = None
        self.fault_offsets = []
        self.requests = Counter()
        self.lock = threading.Lock()
        self.pause_path = None
        self.paused = threading.Event()
        self.resume_stream = threading.Event()

    @contextlib.contextmanager
    def serve(self):
        wire = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                pass

            def do_GET(self):
                source = wire.source
                release = source.release
                prefix = f"/releases/{release.pack_id}/{release.platform}/"
                route = unquote(urlsplit(self.path).path)
                if route == prefix + "manifest":
                    body = json.dumps(release.envelope).encode()
                    self.send_response(200)
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
                relative = route.removeprefix(prefix + "files/")
                if (
                    not route.startswith(prefix + "files/")
                    or relative not in source.files
                ):
                    self.send_error(404)
                    return
                artifact = source.files[relative]
                value = self.headers.get("Range", "bytes=0-")
                try:
                    offset = int(value.removeprefix("bytes=").removesuffix("-"))
                    if not value.startswith("bytes=") or not (
                        0 <= offset < artifact.size or offset == artifact.size == 0
                    ):
                        raise ValueError
                except ValueError:
                    self.send_error(416)
                    return
                with wire.lock:
                    wire.requests[relative] += 1
                    if relative == wire.fault_path and len(wire.fault_offsets) < 64:
                        wire.fault_offsets.append(offset)
                self.send_response(206 if offset else 200)
                self.send_header("Content-Length", str(artifact.size - offset))
                if offset:
                    self.send_header(
                        "Content-Range",
                        f"bytes {offset}-{artifact.size - 1}/{artifact.size}",
                    )
                self.end_headers()
                remaining = (
                    min(128 * 1024, artifact.size - offset)
                    if relative == wire.drop_path
                    else artifact.size - offset
                )
                try:
                    with inside(source.root / "files", relative).open("rb") as stream:
                        stream.seek(offset)
                        while remaining:
                            chunk = stream.read(min(256 * 1024, remaining))
                            if not chunk:
                                break
                            self.wfile.write(chunk)
                            remaining -= len(chunk)
                            if relative == wire.pause_path and not wire.paused.is_set():
                                self.wfile.flush()
                                wire.paused.set()
                                wire.resume_stream.wait(120)
                    self.wfile.flush()
                except ConnectionError:
                    pass
                finally:
                    self.close_connection = True

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        server.daemon_threads = True
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield f"http://127.0.0.1:{server.server_port}"
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


def _personal_files(folder, release):
    """Synthetic sentinels, explicitly not a real world or real player session."""
    prepare_client_defaults(release, folder)
    options = folder / "options.txt"
    existing = options.read_bytes() if options.exists() else b""
    options.write_bytes(existing + b"renderDistance:7\nfov:0.4\n")
    for config in release.launch.get("client_defaults", {}).get("initial_configs", []):
        path = folder / config["path"]
        data = json.loads(path.read_text(encoding="utf-8"))
        data.update(shape="Circle", showGrid="true")
        path.write_text(json.dumps(data), encoding="utf-8")
    for relative in [
        "saves/lab-sentinel/data.txt",
        "screenshots/lab-sentinel.txt",
        "journeymap/data/lab-sentinel.txt",
    ]:
        path = folder / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"Synthetic user data; not a Minecraft world")
    servers = folder / "servers.dat"
    name, root = read_nbt(servers.read_bytes()) if servers.exists() else ("", {})
    entries = root.get("servers", Tag(9, (10, []))).value[1]
    entries.append(
        Tag(
            10,
            {
                "name": Tag(8, "Personal lab sentinel"),
                "ip": Tag(8, "friend.invalid:25565"),
            },
        )
    )
    root["servers"] = Tag(9, (10, entries))
    servers.write_bytes(write_nbt(name, root))
    paths = [
        "options.txt",
        "saves/lab-sentinel/data.txt",
        "screenshots/lab-sentinel.txt",
        "journeymap/data/lab-sentinel.txt",
    ]
    paths.extend(
        c["path"]
        for c in release.launch.get("client_defaults", {}).get("initial_configs", [])
    )
    return {name: sha256_file(folder / name) for name in paths}


def _all_files_match(folder, release):
    return all(
        (folder / f.path).is_file() and sha256_file(folder / f.path) == f.sha256
        for f in release.files
    )


def run_pack_install_lab(  # noqa: PLR0915 -- ordered regression in owned folders
    source, target, keys, *, target_cdn=None, lab_parent=None
):
    before, after = PackDirectory(source, keys), PackDirectory(target, keys)
    old, new = before.release, after.release
    if (
        old.pack_id != new.pack_id
        or old.platform != new.platform
        or new.platform != current_platform()
    ):
        raise ValueError("Lab requires the same pack and current platform")
    if target_cdn and urlsplit(target_cdn).hostname not in {
        "127.0.0.1",
        "localhost",
        "::1",
    }:
        raise ValueError("The lab accepts only a loopback CDN")
    before.verify()
    after.verify()
    parent = (lab_parent or PROJECT_ROOT / ".local").resolve()
    parent.mkdir(parents=True, exist_ok=True)
    lab = parent / ("pack-install-" + uuid4().hex[:12])
    lab.mkdir()
    (lab / ".omk-owned-pack-install-lab").write_text(
        "Fresh install test only; no accounts or existing worlds", encoding="utf-8"
    )
    checks = []
    report = {
        "ok": False,
        "accepted_player_release": False,
        "minecraft_started": False,
        "checks": checks,
        "lab": str(lab),
        "source_version": old.version,
        "target_version": new.version,
        "source_digest": old.digest,
        "target_digest": new.digest,
        "target_files": len(new.files),
        "target_bytes": new.total_size,
        "fresh_target_cdn": (
            "external_loopback" if target_cdn else "owned_fault_fixture"
        ),
    }

    def expect(condition, name):
        if not condition:
            raise AssertionError(name)
        checks.append(name)
        (lab / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")

    wire = PackWire(before)
    try:
        if (
            shutil.disk_usage(lab).free
            < old.total_size + 2 * new.total_size + 512 * 1024**2
        ):
            raise ValueError("Insufficient free space for isolated client lab")
        with wire.serve() as origin:
            upgrade = Installer(lab / "upgrade", ReleaseClient(origin, keys))
            folder = upgrade.install(upgrade.client.fetch(old.pack_id), lambda _p: None)
            expect(
                _all_files_match(folder, old),
                "source_signed_payload_installed_and_hash_verified",
            )
            personal = _personal_files(folder, old)
            userdata = lab / "upgrade/userdata/lab-sentinel.txt"
            userdata.parent.mkdir(parents=True)
            userdata.write_bytes(b"Synthetic launcher data, no token")
            userdata_hash = sha256_file(userdata)
            changed = [
                f
                for f in new.files
                if f.path not in before.files or f.sha256 != before.files[f.path].sha256
            ]
            fault = max(changed, key=lambda f: f.size)
            if fault.size <= 3 * 128 * 1024:
                raise ValueError(
                    "Need a changed artifact larger than 384 KiB for three short-body attempts"
                )
            retained = {x.path.casefold() for x in new.files}
            obsolete = [f.path for f in old.files if f.path.casefold() not in retained]
            wire.source = after
            wire.fault_path = wire.drop_path = fault.path
            candidate = upgrade.client.fetch(new.pack_id)
            try:
                upgrade.install(candidate, lambda _p: None)
            except ReleaseError as error:
                report["interruption_error"] = str(error)
            else:
                raise AssertionError("Short-body update unexpectedly completed")
            state = upgrade.local_state(new.pack_id)
            expect(state["state"] == "incomplete", "interrupted_upgrade_is_not_ready")
            expect(
                any(v.digest == old.digest for v in state["history"]),
                "interrupted_upgrade_keeps_signed_source_history",
            )
            expect(
                all((folder / path).is_file() for path in obsolete),
                "interruption_does_not_delete_obsolete_source_files",
            )
            partial = upgrade.root / f"cache/downloads/{fault.sha256}.part"
            expect(
                partial.is_file() and partial.stat().st_size > 0,
                "short_body_partial_is_preserved",
            )
            report["interrupted_partial_bytes"] = partial.stat().st_size
            wire.drop_path = None
            resumed = Installer(upgrade.root, ReleaseClient(origin, keys))
            resumed.install(resumed.client.fetch(new.pack_id), lambda _p: None)
            expect(
                any(offset > 0 for offset in wire.fault_offsets[3:]),
                "new_installer_resumes_actual_http_range",
            )
            report["fault_offsets"] = wire.fault_offsets[:16]
            expect(
                _all_files_match(folder, new), "updated_complete_payload_hashes_match"
            )
            expect(
                resumed.local_state(new.pack_id)["state"] == "installed",
                "resumed_upgrade_is_ready",
            )
            expect(
                all(not (folder / path).exists() for path in obsolete),
                "obsolete_signed_source_files_removed_after_success",
            )
            prepare_client_defaults(new, folder)
            expect(
                all(
                    sha256_file(folder / name) == digest
                    for name, digest in personal.items()
                ),
                "options_maps_saves_and_screenshots_preserved",
            )
            expect(
                sha256_file(userdata) == userdata_hash, "launcher_userdata_preserved"
            )
            _, root = read_nbt((folder / "servers.dat").read_bytes())
            names = [row.value["name"].value for row in root["servers"].value[1]]
            expected_servers = new.launch.get("client_defaults", {}).get("servers", [])
            expect(
                "Personal lab sentinel" in names
                and all(s["name"] in names for s in expected_servers),
                "managed_server_updated_and_personal_entry_preserved",
            )
            extra = folder / "mods/UnexpectedLabMod.jar"
            extra.parent.mkdir(parents=True, exist_ok=True)
            extra.write_bytes(b"Not an executable mod; owned policy sentinel")
            clean_extra_mods(new, folder)
            verify_mods(new, folder)
            expect(not extra.exists(), "normal_prelaunch_policy_removes_unsigned_extra")
            # Damage only owned test copies; no changes to the release sources.
            repair = [
                f
                for f in new.files
                if f.path.startswith("mods/") and f.path.endswith(".jar")
            ][:2]
            if len(repair) != 2:
                raise ValueError("Two signed mod JARs are needed for repair control")
            (folder / repair[0].path).unlink()
            path = folder / repair[1].path
            with path.open("r+b") as stream:
                byte = stream.read(1)
                stream.seek(0)
                stream.write(bytes([byte[0] ^ 1]))
            mark = sum(wire.requests.values())
            resumed.install(candidate, lambda _p: None)
            prepare_client_defaults(new, folder)
            expect(
                sum(wire.requests.values()) - mark == 2,
                "repair_downloads_only_deleted_and_same_size_corrupt_mods",
            )
            expect(
                _all_files_match(folder, new), "repaired_complete_payload_hashes_match"
            )
            expect(
                all(
                    sha256_file(folder / name) == digest
                    for name, digest in personal.items()
                ),
                "repair_does_not_reset_personal_settings",
            )
            mark = sum(wire.requests.values())
            resumed.install(candidate, lambda _p: None)
            expect(
                sum(wire.requests.values()) == mark, "healthy_recheck_downloads_nothing"
            )
            fresh = Installer(lab / "fresh", ReleaseClient(target_cdn or origin, keys))
            remote = fresh.client.fetch(new.pack_id)
            expect(
                remote.digest == new.digest, "fresh_cdn_serves_exact_signed_candidate"
            )
            fresh_folder = fresh.install(remote, lambda _p: None)
            expect(
                _all_files_match(fresh_folder, new),
                "fresh_complete_payload_hashes_match",
            )
            prepare_client_defaults(remote, fresh_folder)
            expect(
                fresh.local_state(new.pack_id)["state"] == "installed",
                "fresh_install_ready",
            )
            report["obsolete_source_files"] = len(obsolete)
        # A bound non-listening socket cannot be reused by another local service.
        with socket.socket() as offline:
            offline.bind(("127.0.0.1", 0))
            disconnected = ReleaseClient(
                f"http://127.0.0.1:{offline.getsockname()[1]}", keys
            )
            try:
                disconnected.fetch(new.pack_id)
            except (OSError, ReleaseError) as error:
                report["offline_error"] = str(error)
                expect(
                    True,
                    "offline_manifest_fetch_fails_instead_of_returning_stale_release",
                )
            else:
                raise AssertionError("Offline manifest fetch unexpectedly succeeded")
        expect(
            resumed.local_state(new.pack_id)["state"] == "installed",
            "offline_fetch_does_not_damage_last_complete_install",
        )
        report["ok"] = True
    except (OSError, ValueError, ReleaseError, AssertionError) as error:
        report.update(error_type=type(error).__name__, error=str(error)[:500])
    (lab / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def add_pack_install_lab(parser):
    parser.add_argument(
        "--hard-kill",
        action="store_true",
        help="Kill and restart a real installer child process",
    )
    parser.add_argument("--source-release", type=Path, required=True)
    parser.add_argument("--target-release", type=Path, required=True)
    parser.add_argument("--public-keys", type=Path, required=True)
    parser.add_argument(
        "--target-cdn",
        help="Optional real, loopback-only API for fresh-install control",
    )


def run_pack_install_args(args):
    try:
        keys = json.loads(args.public_keys.read_text(encoding="utf-8"))
        if args.hard_kill:
            if args.target_cdn:
                raise ValueError("Hard-kill control uses its own loopback server")
            from omk.pack_process_lab import run_pack_process_lab  # noqa: PLC0415

            return run_pack_process_lab(args.source_release, args.target_release, keys)
        return run_pack_install_lab(
            args.source_release, args.target_release, keys, target_cdn=args.target_cdn
        )
    except OSError, ValueError, ReleaseError:
        return {
            "ok": False,
            "accepted_player_release": False,
            "error": "Invalid signed pack input or lab configuration",
        }
