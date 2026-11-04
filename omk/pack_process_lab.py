"""Kill only an owned installer child; source data and existing installs are read-only."""

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

from launcher.client_defaults import prepare_client_defaults
from launcher.install import Installer, ReleaseClient, current_platform
from launcher.releases import MAX_MANIFEST_BYTES, ReleaseError, sha256_file
from omk.pack_install_lab import (
    PackDirectory,
    PackWire,
    _all_files_match,
    _personal_files,
)
from omk.profiles import PROJECT_ROOT


def _worker(plan_path):
    plan_path = plan_path.resolve()
    lab = plan_path.parent
    if not (lab / ".omk-owned-pack-process-lab").is_file():
        raise ValueError("Owned lab marker required")
    with plan_path.open("rb") as stream:
        plan = json.loads(stream.read(MAX_MANIFEST_BYTES + 1))
    if plan["schema"] != 1 or urlsplit(plan["origin"]).hostname != "127.0.0.1":
        raise ValueError("Invalid owned worker plan")
    client = ReleaseClient(plan["origin"], plan["keys"])
    release = client.fetch(plan["pack_id"])
    if release.digest != plan["target_digest"]:
        raise ValueError("Unexpected worker target")
    Installer(lab / "portable", client).install(release, lambda _p: None)
    (lab / "worker-complete.json").write_text(
        json.dumps({"digest": release.digest}), encoding="utf-8"
    )


def run_pack_process_lab(  # noqa: PLR0915 -- one owned process lifecycle
    source, target, keys, *, lab_parent=None
):
    before, after = PackDirectory(source, keys), PackDirectory(target, keys)
    old, new = before.release, after.release
    if (
        old.pack_id != new.pack_id
        or old.platform != new.platform
        or new.platform != current_platform()
    ):
        raise ValueError("Matching current-platform source/target required")
    before.verify()
    after.verify()
    changed = [
        f
        for f in new.files
        if f.path not in before.files or f.sha256 != before.files[f.path].sha256
    ]
    fault = max(changed, key=lambda f: f.size)
    if fault.size < 1024 * 1024:
        raise ValueError("A changed artifact of at least 1 MiB is required")
    lab = (lab_parent or PROJECT_ROOT / ".local").resolve() / (
        "pack-process-" + uuid4().hex[:12]
    )
    lab.mkdir(parents=True)
    (lab / ".omk-owned-pack-process-lab").write_text(
        "Own child and fresh portable root only", encoding="utf-8"
    )
    report = {
        "ok": False,
        "accepted_player_release": False,
        "minecraft_started": False,
        "lab": str(lab),
        "source_digest": old.digest,
        "target_digest": new.digest,
        "target_files": len(new.files),
        "target_bytes": new.total_size,
        "kill_method": "TerminateProcess" if os.name == "nt" else "SIGKILL",
        "checks": [],
    }
    process = None
    log = None
    wire = PackWire(before)

    def expect(condition, name):
        if not condition:
            raise AssertionError(name)
        report["checks"].append(name)
        (lab / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")

    def child():
        return subprocess.Popen(
            [
                sys.executable,
                "-m",
                "omk.pack_process_lab",
                "--worker",
                str(lab / "worker-plan.json"),
            ],
            cwd=PROJECT_ROOT,
            stdout=log,
            stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )

    try:
        with wire.serve() as origin:
            client = ReleaseClient(origin, keys)
            installer = Installer(lab / "portable", client)
            folder = installer.install(client.fetch(old.pack_id), lambda _p: None)
            personal = _personal_files(folder, old)
            session = lab / "portable/userdata/lab-session-sentinel.txt"
            session.parent.mkdir(parents=True)
            session.write_bytes(b"No actual token; owned persistence sentinel")
            personal_session_hash = sha256_file(session)
            expect(
                _all_files_match(folder, old),
                "source_payload_verified_before_child_start",
            )
            wire.source = after
            wire.pause_path = wire.fault_path = fault.path
            plan = {
                "schema": 1,
                "origin": origin,
                "keys": keys,
                "pack_id": new.pack_id,
                "target_digest": new.digest,
            }
            (lab / "worker-plan.json").write_text(json.dumps(plan), encoding="utf-8")
            log = (lab / "worker-killed.log").open("wb")
            process = child()
            if not wire.paused.wait(120):
                raise TimeoutError("Owned child did not reach the streamed artifact")
            partial = installer.root / f"cache/downloads/{fault.sha256}.part"
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline and (
                not partial.exists() or partial.stat().st_size < 256 * 1024
            ):
                time.sleep(0.05)
            expect(
                partial.is_file() and partial.stat().st_size >= 256 * 1024,
                "actual_child_wrote_partial_before_kill",
            )
            state = installer.local_state(new.pack_id)
            expect(
                state["state"] == "incomplete"
                and any(h.digest == old.digest for h in state["history"]),
                "child_saved_incomplete_state_and_signed_source_history",
            )
            expect(process.poll() is None, "owned_child_was_running_at_kill")
            process.kill()
            process.wait(timeout=15)
            report["killed_child_exit_code"] = process.returncode
            expect(process.returncode != 0, "forced_child_exit_observed")
            log.close()
            log = None
            report["partial_bytes_after_kill"] = partial.stat().st_size
            expect(
                not (lab / "worker-complete.json").exists(),
                "killed_child_never_reported_complete",
            )
            retained = {f.path.casefold() for f in new.files}
            obsolete = [f.path for f in old.files if f.path.casefold() not in retained]
            expect(
                all((folder / p).is_file() for p in obsolete),
                "old_owned_files_retained_after_process_kill",
            )
            wire.pause_path = None
            wire.resume_stream.set()
            log = (lab / "worker-restarted.log").open("wb")
            process = child()
            process.wait(timeout=300)
            report["restarted_child_exit_code"] = process.returncode
            expect(process.returncode == 0, "new_process_completed_update")
            expect(
                any(v > 0 for v in wire.fault_offsets[1:]),
                "new_process_used_real_http_range",
            )
            expect(
                json.loads((lab / "worker-complete.json").read_text(encoding="utf-8"))[
                    "digest"
                ]
                == new.digest,
                "new_process_confirmed_exact_target_digest",
            )
            expect(
                _all_files_match(folder, new),
                "all_target_hashes_verified_after_restart",
            )
            expect(
                installer.local_state(new.pack_id)["state"] == "installed",
                "recovered_install_is_ready",
            )
            expect(
                all(not (folder / p).exists() for p in obsolete),
                "obsolete_owned_files_removed_only_after_success",
            )
            prepare_client_defaults(new, folder)
            expect(
                all(
                    sha256_file(folder / name) == digest
                    for name, digest in personal.items()
                ),
                "options_journeymap_saves_screenshots_preserved",
            )
            expect(
                sha256_file(session) == personal_session_hash,
                "launcher_userdata_preserved",
            )
            report["range_offsets"] = wire.fault_offsets[:16]
            report["ok"] = True
    except (
        OSError,
        ValueError,
        ReleaseError,
        AssertionError,
        TimeoutError,
        subprocess.SubprocessError,
    ) as error:
        report.update(error_type=type(error).__name__, error=str(error)[:500])
    finally:
        wire.resume_stream.set()
        if process is not None and process.poll() is None:
            process.kill()
            process.wait(timeout=15)
        if log is not None:
            log.close()
        report["owned_child_stopped"] = process is None or process.poll() is not None
        (lab / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--worker", type=Path, required=True)
    _worker(parser.parse_args().worker)
