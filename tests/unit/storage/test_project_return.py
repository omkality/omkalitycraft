import copy
import json
import subprocess
import sys
from datetime import timedelta
from types import SimpleNamespace

import pytest

from omk.backups.offsite_process import OffsiteError
from omk.owner.admin import AdminError
from omk.owner.storage import project_return as journal
from tests.fixtures.unit.game.project_policy import prepared as policy_prepared
from tests.fixtures.unit.storage.project_return import operation

__all__ = ["operation", "policy_prepared"]


def run(p, action=journal.run):
    return action(p.config, p.operation, checkpoint=lambda: copy.deepcopy(p.fence))


def test_full_journal_preserves_selection_and_sources_without_boot(operation):
    p = operation
    assert not list(p.target.iterdir())
    before = {f.name: journal.raw.archive.digest(f) for f in p.source.iterdir()}
    r = journal.read(p.config, p.operation)
    assert r["raw"]["selection"] == p.raw["selection"]
    assert not journal.status(p.config, p.operation)["files_verified"]
    result = run(p)
    assert (
        result["files_verified"]
        and not result["boot_allowed"]
        and not result["ready_for_players"]
    )
    assert run(p, journal.verify)["files_verified"]
    assert before == {f.name: journal.raw.archive.digest(f) for f in p.source.iterdir()}
    with pytest.raises(AdminError):
        run(p)


@pytest.mark.parametrize("phase", ["raw", "policy"])
def test_lost_worker_reply_requires_verify_never_repeated_apply(
    operation, monkeypatch, phase
):
    p = operation
    module = journal.raw if phase == "raw" else journal.policy
    original = module.stage

    def lost(*a, **kw):
        original(*a, **kw)
        raise OSError("worker reply lost")

    monkeypatch.setattr(module, "stage", lost)
    with pytest.raises(OSError):
        run(p)
    assert journal.read(p.config, p.operation)["phase"] == phase + "-requested"
    with pytest.raises(AdminError):
        run(p)
    monkeypatch.setattr(
        module, "stage", lambda *a, **kw: pytest.fail("verify must never apply")
    )
    result = run(p, journal.verify)
    assert result["phase"] == ("raw-staged" if phase == "raw" else "files-verified")


@pytest.mark.parametrize("phase", ["raw", "policy"])
def test_partial_stage_cannot_be_adopted_or_retried(operation, monkeypatch, phase):
    p = operation
    if phase == "raw":
        original = journal.raw.copy_file

        def partial(*a, **kw):
            original(*a, **kw)
            raise OSError("partial copy")

        monkeypatch.setattr(journal.raw, "copy_file", partial)
    else:
        original = journal.policy.shared.os.replace

        def partial(a, b):
            if str(a).endswith(".tmp"):
                return original(a, b)
            original(a, b)
            raise OSError("partial policy")

        monkeypatch.setattr(journal.policy.shared.os, "replace", partial)
    with pytest.raises(OSError):
        run(p)
    with pytest.raises(AdminError):
        run(p)
    with pytest.raises((ValueError, OffsiteError)):
        run(p, journal.verify)


@pytest.mark.parametrize(
    "fault", ["current", "fence", "expiry", "clock", "allowlist", "intent"]
)
def test_stale_authority_or_intent_refuses_before_target_write(
    operation, monkeypatch, fault
):
    p = operation
    if fault == "current":
        (p.current / journal.policy.shared.RANKS).write_text("later ranks")
    elif fault == "fence":
        p.fence["source"] = "restarted-source"
    elif fault == "allowlist":
        p.config.servers["dj2"] = p.target
    elif fault == "intent":
        path = journal.path(p.config, p.operation)
        r = json.loads(path.read_bytes())
        r["current_sha256"] = "1" * 64
        path.write_text(json.dumps(r))
    else:
        now = journal._now()
        monkeypatch.setattr(
            journal,
            "_now",
            lambda: now + timedelta(days=2 if fault == "expiry" else -2),
        )
    with pytest.raises(AdminError):
        run(p)
    assert not list(p.target.iterdir())


def test_changed_fence_after_copy_preserves_uncertain_journal(operation, monkeypatch):
    p = operation
    original = journal.raw.stage

    def changed(*a, **kw):
        result = original(*a, **kw)
        p.fence["source"] = "restarted"
        return result

    monkeypatch.setattr(journal.raw, "stage", changed)
    with pytest.raises(AdminError):
        run(p)
    assert journal.read(p.config, p.operation)["phase"] == "raw-requested"
    assert not (p.target / journal.policy.PLAN).exists()


def test_capacity_and_duplicate_id_never_overwrite_a_selection(operation):
    p = operation
    before = journal.path(p.config, p.operation).read_bytes()
    with pytest.raises(AdminError):
        journal.plan(
            p.config,
            "dj2",
            p.source,
            p.target,
            p.current,
            world="lab-world",
            selection=p.raw["selection"],
            settings=p.raw["settings"],
            checkpoint=lambda: p.fence,
            operation=p.operation,
        )
    assert before == journal.path(p.config, p.operation).read_bytes()


def test_nested_owner_operation_uses_existing_lock(operation):
    p = operation
    with journal.owner.locked(p.config):
        assert run(p)["files_verified"]


def test_invalid_operation_never_escapes_owner_private_root(tmp_path):
    config = SimpleNamespace(private=tmp_path)
    with pytest.raises(AdminError):
        journal.status(config, "../not-an-operation")


PROCESS = """
import json, os, sys
from pathlib import Path
from types import SimpleNamespace
from omk import project_return as j
config=SimpleNamespace(private=Path(sys.argv[1]), servers={'dj2':Path(sys.argv[2])})
operation, fault=sys.argv[3:5]
fence={'source':'stopped-owned-source','target':'empty-owned-target'}
if fault == 'lock':
    try:
        with j.owner.locked(config): pass
    except j.owner.OwnerBusy:
        os._exit(27)
    os._exit(0)
if fault in ('raw','policy'):
    module=j.raw if fault=='raw' else j.policy
    original=module.stage
    def aborted(*a,**kw):
        original(*a,**kw)
        os._exit(23)
    module.stage=aborted
elif fault == 'raw-partial':
    original=j.raw.copy_file
    def aborted(*a,**kw):
        original(*a,**kw)
        os._exit(24)
    j.raw.copy_file=aborted
else:
    original=j.policy.shared.os.replace
    def aborted(a,b):
        original(a,b)
        if not str(a).endswith('.tmp'):
            os._exit(24)
    j.policy.shared.os.replace=aborted
j.run(config,operation,checkpoint=lambda:fence)
raise AssertionError('Fault was not exercised')
"""


def child(p, fault):
    return subprocess.run(
        [
            sys.executable,
            "-c",
            PROCESS,
            str(p.config.private),
            str(p.current),
            p.operation,
            fault,
        ],
        capture_output=True,
        timeout=30,
        check=False,
    )


@pytest.mark.parametrize("fault", ["raw", "policy", "raw-partial", "policy-partial"])
def test_process_death_releases_lock_but_never_repeats_uncertain_write(
    operation, monkeypatch, fault
):
    p = operation
    # Real subprocesses do not inherit pytest's fixture JAR-pin monkeypatch.
    script = PROCESS.replace(
        "operation, fault=sys.argv[3:5]",
        "j.policy.shared.ftb.PINS="
        + repr(journal.policy.shared.ftb.PINS)
        + "\noperation, fault=sys.argv[3:5]",
    )
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            script,
            str(p.config.private),
            str(p.current),
            p.operation,
            fault,
        ],
        capture_output=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == (24 if "partial" in fault else 23), (
        result.stderr.decode()
    )
    with pytest.raises(AdminError):
        run(p)
    if "partial" in fault:
        with pytest.raises((ValueError, OffsiteError)):
            run(p, journal.verify)
    else:
        result = run(p, journal.verify)
        if fault == "raw":
            assert result["phase"] == "raw-staged"
            assert run(p)["files_verified"]
        else:
            assert result["files_verified"]


def test_existing_owner_lock_excludes_a_second_process(operation):
    p = operation
    with journal.owner.locked(p.config):
        assert child(p, "lock").returncode == 27
        assert not list(p.target.iterdir())
    assert child(p, "lock").returncode == 0


def test_journal_capacity_refuses_before_raw_planning(operation, monkeypatch):
    p = operation
    for n in range(7):
        journal.path(p.config, f"{n:032x}").write_text("{}")
    monkeypatch.setattr(
        journal.raw,
        "plan",
        lambda *a, **kw: pytest.fail("full journal must refuse before planning"),
    )
    with pytest.raises(AdminError):
        journal.plan(
            p.config,
            "dj2",
            p.source,
            p.target,
            p.current,
            world="lab-world",
            selection=p.raw["selection"],
            settings=p.raw["settings"],
            checkpoint=lambda: p.fence,
            environment={"OMK_BACKUP_JOURNAL_COUNT": "8"},
        )
    assert not list(p.target.iterdir())


def test_failed_intent_write_never_enters_file_worker(operation, monkeypatch):
    p = operation

    def full(*args):
        raise OSError("simulated journal ENOSPC")

    monkeypatch.setattr(journal, "_write_private", full)
    monkeypatch.setattr(
        journal.raw, "stage", lambda *a, **kw: pytest.fail("no durable intent")
    )
    with pytest.raises(OSError):
        run(p)
    assert not list(p.target.iterdir())
    assert journal.read(p.config, p.operation)["phase"] == "planned"
