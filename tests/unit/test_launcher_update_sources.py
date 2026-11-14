import argparse
import contextlib
import json
import threading
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import Mock, patch
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request

import pytest
from tuf.api import exceptions
from tuf.api.metadata import Metadata

from launcher.install import current_platform
from launcher.update_sources import github_asset_redirect, github_asset_url
from launcher.updater import LauncherUpdater, PortableFetcher, UpdateError
from omk.drasl import DraslClient
from omk.release_cli import add_release_commands, prepare_release
from omk.updates import publish_update
from tests.http_fixture import serve


def asset(version="1.1.0", platform=None):
    platform = platform or current_platform()
    return (
        "https://github.com/omkality/omkalitycraft/releases/download/"
        f"launcher-v{version}/OmkalityCraft-{version}-{platform}.zip"
    )


@pytest.mark.parametrize(
    "platform", ["windows-x64", "linux-x64", "macos-x64", "macos-arm64"]
)
def test_exact_versioned_asset_policy(platform):
    assert github_asset_url(asset(platform=platform), "1.1.0", platform) == asset(
        platform=platform
    )
    other_tag = asset(platform=platform).replace("/launcher-v", "/v")
    assert github_asset_url(other_tag, "1.1.0", platform) == other_tag


@pytest.mark.parametrize(
    "bad",
    [
        None,
        123,
        "https://github.com/omkality/omkalitycraft/releases/latest/download/app.zip",
        asset().replace("https:", "http:"),
        asset().replace("github.com/", "github.com.evil/"),
        asset().replace("github.com/", "user@github.com/"),
        asset().replace("/omkality/", "/other/"),
        asset().replace("launcher-v1.1.0", "latest"),
        asset().replace("launcher-v1.1.0", "launcher-v1.2.0"),
        asset().replace("OmkalityCraft-1.1.0", "OmkalityCraft-1.0.0"),
        asset() + "?token=not-accepted",
        asset() + "#fragment",
        asset().replace(".zip", ".exe"),
        asset().replace("/releases/download/", "/archive/refs/tags/"),
    ],
)
def test_asset_policy_rejects_nonversioned_or_other_sources(bad):
    with pytest.raises(ValueError):
        github_asset_url(bad, "1.1.0", current_platform())


@pytest.mark.parametrize(
    "url",
    [
        "http://release-assets.githubusercontent.com/file",
        "https://release-assets.githubusercontent.com.evil/file",
        "https://user@release-assets.githubusercontent.com/file",
        "https://release-assets.githubusercontent.com:444/file",
        "https://127.0.0.1/file",
        "file:///private/file",
        "https://release-assets.githubusercontent.com/file#fragment",
        "https://release-assets.githubusercontent.com/fi\nle",
        "https://release-assets.githubusercontent.com\\@evil/file",
        "https://release-assets.githubusercontent.com/кириллица",
    ],
)
def test_redirect_policy_rejects_unsafe_endpoints(url):
    with pytest.raises(ValueError):
        github_asset_redirect(url)


def test_signed_cdn_query_and_default_tls_port_are_allowed():
    url = "https://release-assets.githubusercontent.com:443/asset?signature=a%2Fb"
    assert github_asset_redirect(url) == url


@pytest.fixture
def release(tmp_path: Path):
    archive = tmp_path / "bundle.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("OmkalityCraft", b"test executable, never executed")
    repository, keys = tmp_path / "cdn/updates", tmp_path / "keys"
    root = publish_update(
        repository,
        keys,
        archive,
        "1.1.0",
        "OmkalityCraft",
        github_asset_url=asset(),
    )
    return tmp_path, repository, root.read_bytes(), archive.read_bytes()


@contextlib.contextmanager
def github_wire(payload, mode="ok", location=None):
    """Real loopback HTTP underneath a test-only HTTPS URL mapping; no live GitHub."""
    requests = []
    cdn = "https://release-assets.githubusercontent.com/fixture"

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/start" and mode not in {"direct", "404", "429", "503"}:
                self.send_response(302)
                self.send_header("Location", location or cdn)
                self.end_headers()
                return
            if mode in {"404", "429", "503"}:
                self.send_error(int(mode))
                return
            if mode == "loop":
                self.send_response(302)
                self.send_header("Location", cdn)
                self.end_headers()
                return
            if mode == "many":
                hop = int(urlsplit(self.path).query.removeprefix("hop=") or "0") + 1
                self.send_response(302)
                self.send_header("Location", cdn + "?hop=" + str(hop))
                self.end_headers()
                return
            data = payload
            if mode == "wronghash":
                data = bytes([payload[0] ^ 1]) + payload[1:]
            elif mode == "oversize":
                data += b"unexpected"
            self.send_response(200)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data[: len(data) // 2] if mode == "drop" else data)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    opener = DraslClient(f"http://127.0.0.1:{server.server_port}")._opener

    class Bridge:
        def open(self, request, timeout):
            requests.append(request.full_url)
            assert request.get_method() == "GET" and request.data is None
            headers = dict(request.header_items())
            assert not {"authorization", "cookie"} & {k.lower() for k in headers}
            if mode == "timeout":
                raise TimeoutError("network fixture only")
            if request.full_url == asset():
                path = "/start"
            else:
                assert request.full_url == cdn or request.full_url.startswith(
                    cdn + "?hop="
                ), "Unexpected outbound URL"
                path = "/cdn" + (
                    "?" + urlsplit(request.full_url).query
                    if urlsplit(request.full_url).query
                    else ""
                )
            return opener.open(
                Request(
                    f"http://127.0.0.1:{server.server_port}{path}", headers=headers
                ),
                timeout=timeout,
            )

    original = PortableFetcher

    def fetcher(*args, **kwargs):
        result = original(*args, **kwargs)
        result.github._opener = Bridge()
        return result

    try:
        with patch("launcher.updater.PortableFetcher", side_effect=fetcher):
            yield requests
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


@pytest.mark.parametrize("mode", ["ok", "direct"])
def test_real_tuf_uses_github_and_verifies_before_extract(release, mode):
    temporary, repository, root, payload = release
    with (
        serve(repository.parent) as (origin, mirror),
        github_wire(payload, mode) as github,
    ):
        progress = []
        update = LauncherUpdater(temporary / "portable", origin, root, "1.0").prepare(
            progress.append
        )
    assert update.entrypoint.read_bytes() == b"test executable, never executed"
    assert github[0] == asset()
    assert len(github) == (2 if mode == "ok" else 1)
    assert not any("/targets/" in path for path, _ in mirror)
    assert any("Обновляем" in text for text in progress)


@pytest.mark.parametrize("mode", ["404", "429", "503", "timeout", "drop"])
def test_unavailable_or_interrupted_github_restarts_on_verified_mirror(release, mode):
    temporary, repository, root, payload = release
    portable = temporary / "portable"
    personal = portable / "userdata/session.json"
    personal.parent.mkdir(parents=True)
    personal.write_bytes(b"test session, preserved")
    with (
        serve(repository.parent) as (origin, mirror),
        github_wire(payload, mode) as github,
    ):
        update = LauncherUpdater(portable, origin, root, "1.0").prepare(lambda _: None)
    assert update.entrypoint.read_bytes() == b"test executable, never executed"
    assert personal.read_bytes() == b"test session, preserved"
    assert github and sum("/targets/" in path for path, _ in mirror) == 1
    assert not list((portable / "userdata/updates/tmp").iterdir())


@pytest.mark.parametrize(
    "mode,error",
    [
        ("wronghash", exceptions.LengthOrHashMismatchError),
        ("oversize", exceptions.DownloadLengthMismatchError),
        ("loop", UpdateError),
    ],
)
def test_integrity_and_redirect_failures_do_not_extract_or_silently_fallback(
    release, mode, error
):
    temporary, repository, root, payload = release
    portable = temporary / "portable"
    with (
        serve(repository.parent) as (origin, mirror),
        github_wire(payload, mode),
        pytest.raises(error),
    ):
        LauncherUpdater(portable, origin, root, "1.0").prepare(lambda _: None)
    assert not (portable / "app_versions").exists()
    assert not any("/targets/" in path for path, _ in mirror)


@pytest.mark.parametrize(
    "location",
    ["https://evil.invalid/asset", "http://127.0.0.1/private", "//evil.invalid/x"],
)
def test_untrusted_redirect_is_rejected_before_request(release, location):
    temporary, repository, root, payload = release
    with (
        serve(repository.parent) as (origin, _),
        github_wire(payload, location=location) as github,
        pytest.raises(UpdateError, match="перенаправление"),
    ):
        LauncherUpdater(temporary / "portable", origin, root, "1.0").prepare(
            lambda _: None
        )
    assert github == [asset()]


def test_unsigned_asset_url_tampering_is_rejected_before_github(release):
    temporary, repository, root, payload = release
    path = repository / "metadata/targets.json"
    document = json.loads(path.read_bytes())
    document["signed"]["targets"][f"{current_platform()}/launcher.zip"]["custom"][
        "github_asset_url"
    ] = "https://evil.invalid/x.zip"
    # Consistent snapshot uses the versioned copy.
    for name in ["targets.json", "1.targets.json"]:
        (repository / "metadata" / name).write_text(
            json.dumps(document), encoding="utf8"
        )
    with (
        serve(repository.parent) as (origin, _),
        github_wire(payload) as github,
        pytest.raises(exceptions.RepositoryError),
    ):
        LauncherUpdater(temporary / "portable", origin, root, "1.0").prepare(
            lambda _: None
        )
    assert not github


def test_verified_cached_archive_does_not_contact_github_again(release):
    temporary, repository, root, payload = release
    with serve(repository.parent) as (origin, _), github_wire(payload) as github:
        updater = LauncherUpdater(temporary / "portable", origin, root, "1.0")
        updater.prepare(lambda _: None)
        first = list(github)
        updater.prepare(lambda _: None)
        assert github == first


def test_publisher_signs_asset_url_and_preserves_other_platform_targets(release):
    temporary, repository, _, _ = release
    other = "linux-x64" if current_platform() != "linux-x64" else "windows-x64"
    publish_update(
        repository,
        temporary / "keys",
        temporary / "bundle.zip",
        "1.1.0",
        "OmkalityCraft",
        platform=other,
        github_asset_url=asset(platform=other),
    )
    targets = Metadata.from_file(
        str(repository / "metadata/targets.json")
    ).signed.targets
    assert (
        targets[f"{current_platform()}/launcher.zip"].custom["github_asset_url"]
        == asset()
    )
    assert targets[f"{other}/launcher.zip"].custom["github_asset_url"] == asset(
        platform=other
    )


def test_origin_with_trailing_slash_still_prefers_github(release):
    temporary, repository, root, payload = release
    with serve(repository.parent) as (origin, mirror), github_wire(payload) as github:
        LauncherUpdater(temporary / "portable", origin + "/", root, "1.0").prepare(
            lambda _: None
        )
    assert github
    assert not any("/targets/" in path for path, _ in mirror)


def test_even_signed_invalid_asset_url_is_rejected_before_any_asset_request(release):
    temporary, repository, root, payload = release
    with patch(
        "omk.updates.validate_github_asset_url", side_effect=lambda value, *_: value
    ):
        publish_update(
            repository,
            temporary / "keys",
            temporary / "bundle.zip",
            "1.2.0",
            "OmkalityCraft",
            github_asset_url="https://evil.invalid/app.zip",
        )
    with (
        serve(repository.parent) as (origin, mirror),
        github_wire(payload) as github,
        pytest.raises(UpdateError, match="Описание"),
    ):
        LauncherUpdater(temporary / "portable", origin, root, "1.0").prepare(
            lambda _: None
        )
    assert not github and not any("/targets/" in p for p, _ in mirror)


def test_metadata_unavailable_never_uses_unverified_github_or_changes_active_version(
    release,
):
    temporary, _repository, root, payload = release
    portable = temporary / "portable"
    old = portable / "app_versions/old/app"
    old.parent.mkdir(parents=True)
    old.write_bytes(b"last healthy fixture")
    state = portable / "userdata/updates/state.json"
    state.parent.mkdir(parents=True)
    state.write_text(
        json.dumps(
            {
                "active": {
                    "folder": "app_versions/old",
                    "entrypoint": "app",
                    "version": "1.0.1",
                    "digest": "previous",
                }
            }
        )
    )
    before = state.read_bytes()
    with serve(temporary / "empty") as (origin, _), github_wire(payload) as github:
        updater = LauncherUpdater(portable, origin, root, "1.0")
        with pytest.raises(exceptions.DownloadError):
            updater.prepare(lambda _: None)
        assert updater.active().entrypoint == old
    assert (
        not github
        and state.read_bytes() == before
        and old.read_bytes() == b"last healthy fixture"
    )


def test_unavailable_primary_and_corrupt_mirror_preserve_user_files(release):
    temporary, repository, root, payload = release
    next((repository / f"targets/{current_platform()}").glob("*.zip")).write_bytes(
        b"corrupt mirror"
    )
    portable = temporary / "portable"
    session = portable / "userdata/session.json"
    session.parent.mkdir(parents=True)
    session.write_bytes(b"personal fixture")
    with (
        serve(repository.parent) as (origin, _),
        github_wire(payload, "503"),
        pytest.raises(exceptions.LengthOrHashMismatchError),
    ):
        LauncherUpdater(portable, origin, root, "1.0").prepare(lambda _: None)
    assert (
        session.read_bytes() == b"personal fixture"
        and not (portable / "app_versions").exists()
    )


def test_release_cli_signs_versioned_source_in_existing_tuf_flow(release):
    temporary, repository, _, _ = release
    parser = argparse.ArgumentParser()
    add_release_commands(parser.add_subparsers(required=True))
    args = parser.parse_args(
        [
            "release",
            "launcher",
            "--repository",
            str(repository),
            "--keys-dir",
            str(temporary / "keys"),
            "--archive",
            str(temporary / "bundle.zip"),
            "--version",
            "1.2.0",
            "--entrypoint",
            "OmkalityCraft",
            "--platform",
            current_platform(),
            "--github-asset-url",
            asset("1.2.0"),
        ]
    )
    assert prepare_release(args)["deployed"] is False
    targets = Metadata.from_file(
        str(repository / "metadata/targets.json")
    ).signed.targets
    assert targets[f"{current_platform()}/launcher.zip"].custom[
        "github_asset_url"
    ] == asset("1.2.0")


def test_invalid_publisher_source_does_not_create_keys_or_repository(tmp_path):
    archive = tmp_path / "bundle.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("app", b"fixture")
    with pytest.raises(ValueError, match="versioned"):
        publish_update(
            tmp_path / "repository",
            tmp_path / "keys",
            archive,
            "1.0",
            "app",
            github_asset_url="https://evil.invalid/app.zip",
        )
    assert not (tmp_path / "repository").exists() and not (tmp_path / "keys").exists()


@pytest.mark.parametrize("suffix", ["\n", "\t", " "])
def test_raw_redirect_controls_are_not_laundered_by_urljoin(tmp_path, suffix):
    fetcher = PortableFetcher("http://127.0.0.1:9", tmp_path, lambda _: None)
    fetcher.github._opener.open = Mock(
        side_effect=HTTPError(
            asset(),
            302,
            "redirect",
            {"Location": "https://release-assets.githubusercontent.com/file" + suffix},
            None,
        )
    )
    with pytest.raises(UpdateError, match="перенаправление"):
        list(fetcher._github_asset(asset(), 10))
    assert fetcher.github._opener.open.call_count == 1


def test_redirect_chain_is_bounded_even_with_distinct_locations(release):
    temporary, repository, root, payload = release
    with (
        serve(repository.parent) as (origin, mirror),
        github_wire(payload, "many") as github,
        pytest.raises(UpdateError, match="Слишком много"),
    ):
        LauncherUpdater(temporary / "portable", origin, root, "1.0").prepare(
            lambda _: None
        )
    assert len(github) == 4 and not any("/targets/" in p for p, _ in mirror)
