import json
import stat
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from tuf.api import exceptions
from tuf.api.metadata import Metadata

from launcher.install import current_platform
from launcher.releases import ReleaseError
from launcher.updater import (
    LauncherUpdater,
    PreparedUpdate,
    UpdateError,
    acknowledge_health,
)
from omk.updates import _signer, publish_update
from tests.http_fixture import serve


@pytest.fixture
def updates(tmp_path: Path):
    archive = tmp_path / "bundle.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("OmkalityCraft", b"test executable payload")
        bundle.writestr("_internal/config.json", b"{}")
    repository = tmp_path / "cdn/updates"
    keys = tmp_path / "keys"
    root = publish_update(repository, keys, archive, "1.1.0", "OmkalityCraft")
    return tmp_path, repository, keys, archive, root.read_bytes()


def test_real_tuf_download_and_versioned_staging_preserves_data(updates):
    temporary, repository, _, _, root = updates
    portable = temporary / "portable"
    (portable / "userdata").mkdir(parents=True)
    session = portable / "userdata/session.json"
    session.write_text("test session only")
    with serve(repository.parent) as (url, _):
        updater = LauncherUpdater(portable, url, root, "1.0.0")
        progress = []
        update = updater.prepare(progress.append)
        assert update.version == "1.1.0"
        assert update.entrypoint.read_bytes() == b"test executable payload"
        assert update.folder.is_relative_to(portable / "app_versions")
        assert session.read_text() == "test session only"
        assert any("Обновляем" in message for message in progress)
        assert (
            LauncherUpdater(temporary / "current", url, root, "1.1.0").prepare(
                lambda _: None
            )
            is None
        )


def test_corrupt_archive_is_rejected_before_extract(updates):
    temporary, repository, _, _, root = updates
    next((repository / f"targets/{current_platform()}").glob("*.zip")).write_bytes(
        b"corrupt"
    )
    with (
        serve(repository.parent) as (url, _),
        pytest.raises(exceptions.LengthOrHashMismatchError),
    ):
        LauncherUpdater(temporary / "portable", url, root, "1.0").prepare(
            lambda _: None
        )
    assert not (temporary / "portable/app_versions").exists()


def test_expired_metadata_rejected(updates):
    temporary, repository, keys, archive, root = updates
    publish_update(
        repository,
        keys,
        archive,
        "1.2.0",
        "OmkalityCraft",
        now=datetime.now(UTC) - timedelta(days=100),
    )
    with (
        serve(repository.parent) as (url, _),
        pytest.raises(exceptions.ExpiredMetadataError),
    ):
        LauncherUpdater(temporary / "portable", url, root, "1.0").prepare(
            lambda _: None
        )


def test_modified_metadata_signature_rejected(updates):
    temporary, repository, _, _, root = updates
    path = repository / "metadata/timestamp.json"
    data = json.loads(path.read_text())
    data["signed"]["version"] += 5
    path.write_text(json.dumps(data))
    with (
        serve(repository.parent) as (url, _),
        pytest.raises(exceptions.UnsignedMetadataError),
    ):
        LauncherUpdater(temporary / "portable", url, root, "1.0").prepare(
            lambda _: None
        )


def test_metadata_rollback_rejected(updates):
    temporary, repository, keys, archive, root = updates
    old = (repository / "metadata/timestamp.json").read_bytes()
    publish_update(repository, keys, archive, "1.2.0", "OmkalityCraft")
    with serve(repository.parent) as (url, _):
        updater = LauncherUpdater(temporary / "portable", url, root, "1.0")
        updater.prepare(lambda _: None)
        (repository / "metadata/timestamp.json").write_bytes(old)
        with pytest.raises(exceptions.BadVersionNumberError):
            updater.prepare(lambda _: None)


@pytest.mark.parametrize(
    "filename", ["../escape", "/absolute", "userdata/session.json", "CON.txt"]
)
def test_zip_traversal_and_personal_files_rejected(tmp_path: Path, filename: str):
    archive = tmp_path / "bad.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr(filename, b"bad")
    updater = LauncherUpdater(tmp_path / "portable", "http://127.0.0.1:9", b"", "1.0")
    with pytest.raises(ReleaseError):
        updater._extract(archive, updater.root / "app_versions/test")
    assert not (tmp_path / "escape").exists()


def test_zip_symlink_rejected():
    member = zipfile.ZipInfo("link")
    member.external_attr = (stat.S_IFLNK | 0o777) << 16
    with pytest.raises(UpdateError):
        LauncherUpdater._validate_zip([member])


def test_failed_child_keeps_previous_working_version_and_blacklists_digest(
    tmp_path: Path,
):
    updater = LauncherUpdater(tmp_path, "http://127.0.0.1:9", b"", "1.0")
    folder = tmp_path / "app_versions/new"
    folder.mkdir(parents=True)
    executable = folder / "app"
    executable.write_bytes(b"test")
    update = PreparedUpdate("2.0", folder, executable, "digest")
    process = Mock()
    process.poll.return_value = 1
    with patch("launcher.updater.subprocess.Popen", return_value=process):
        assert not updater.handoff(update, timeout=0.1)
    assert json.loads(updater.state_file.read_text())["failed"] == ["digest"]
    assert updater.active() is None


def test_successful_child_must_return_matching_health_nonce(tmp_path: Path):
    updater = LauncherUpdater(tmp_path, "http://127.0.0.1:9", b"", "1.0")
    folder = tmp_path / "app_versions/new"
    folder.mkdir(parents=True)
    executable = folder / "app"
    executable.write_bytes(b"test")
    update = PreparedUpdate("2.0", folder, executable, "digest")

    def start(command, **kwargs):
        acknowledge_health(tmp_path, Path(command[4]), command[6])
        process = Mock()
        process.poll.return_value = None
        return process

    with patch("launcher.updater.subprocess.Popen", side_effect=start):
        assert updater.handoff(update)
    assert updater.active().entrypoint == executable
    assert json.loads(updater.state_file.read_text())["highest_version"] == "2.0"


def test_publisher_rejects_changed_contents_without_version_bump(updates):
    _, repository, keys, archive, _ = updates
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("OmkalityCraft", b"different build")
    with pytest.raises(ValueError, match="new version"):
        publish_update(repository, keys, archive, "1.1.0", "OmkalityCraft")


def test_publisher_rejects_downgrade(updates):
    _, repository, keys, archive, _ = updates
    with pytest.raises(ValueError, match="older launcher"):
        publish_update(repository, keys, archive, "1.0.0", "OmkalityCraft")


def test_private_keys_cannot_be_created_under_public_update_repository(tmp_path: Path):
    with pytest.raises(ValueError, match="outside"):
        publish_update(
            tmp_path, tmp_path / "keys", tmp_path / "absent.zip", "1.0", "app"
        )
    assert not (tmp_path / "keys").exists()


def test_tuf_root_rotation_is_verified_and_cached(updates):
    temporary, repository, keys, _, root = updates
    document = Metadata.from_file(str(repository / "metadata/1.root.json"))
    document.signed.version = 2
    document.sign(_signer(keys, "root"))
    document.to_file(str(repository / "metadata/2.root.json"))
    with serve(repository.parent) as (url, _):
        updater = LauncherUpdater(temporary / "portable", url, root, "1.0")
        assert updater.prepare(lambda _: None).version == "1.1.0"
        assert (updater.cache / "metadata/root_history/2.root.json").is_file()
