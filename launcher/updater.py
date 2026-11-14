"""TUF-verified updates, isolated version folders and a health-checked handoff."""

import contextlib
import http.client
import json
import os
import re
import shutil
import stat
import subprocess
import tempfile
import time
import zipfile
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from secrets import token_hex
from urllib.error import HTTPError
from urllib.parse import urljoin
from urllib.request import Request

from packaging.version import InvalidVersion, Version
from tuf.api import exceptions
from tuf.api.metadata import TargetFile
from tuf.ngclient import Updater
from tuf.ngclient.config import UpdaterConfig
from tuf.ngclient.fetcher import FetcherInterface

from launcher.install import current_platform
from launcher.releases import ReleaseError, inside, safe_path
from launcher.update_sources import github_asset_redirect, github_asset_url
from omk.drasl import DraslClient
from omk.fs import resolved

MAX_ARCHIVE = 512 * 1024**2
MAX_EXPANDED = 2 * 1024**3


class UpdateError(ReleaseError):
    pass


class GitHubAssetUnavailable(exceptions.DownloadError):
    """Availability failure; retry the same signed target from the original CDN."""


class PortableFetcher(FetcherInterface):
    """Use the launcher's transport and its own temporary folder, including TUF."""

    def __init__(
        self, origin: str, temporary: Path, progress: Callable[[str], None]
    ) -> None:
        self.transport = DraslClient(origin, timeout=15)
        self.github = DraslClient("https://github.com", timeout=15)
        self.github_asset: tuple[str, int] | None = None
        self.github_target_urls: set[str] = set()
        self.temporary, self.progress = temporary, progress
        temporary.mkdir(parents=True, exist_ok=True)

    def _fetch(self, url: str) -> Iterator[bytes]:
        if not url.startswith(self.transport.base_url + "/"):
            raise UpdateError("Обновление запросило другой сервер.")
        if self.github_asset is not None and url in self.github_target_urls:
            yield from self._github_asset(*self.github_asset)
            return
        try:
            with self.transport._opener.open(url, timeout=15) as response:
                count = 0
                while chunk := response.read(256 * 1024):
                    count += len(chunk)
                    if "/targets/" in url:
                        self.progress(f"Обновляем лаунчер · {count / 1024**2:.1f} МБ")
                    yield chunk
        except HTTPError as error:
            status = error.code
            error.close()
            raise exceptions.DownloadHTTPError(
                "Update download failed", status
            ) from None

    def use_github_asset(self, target: TargetFile, url: str) -> None:
        """Called only for the target returned by the verified TUF metadata chain."""
        base = self.transport.base_url + "/updates/targets/"
        dirname, _, filename = target.path.rpartition("/")
        self.github_target_urls = {base + target.path} | {
            f"{base}{dirname}/{digest}.{filename}" for digest in target.hashes.values()
        }
        self.github_asset = (url, target.length)

    def _github_asset(self, url: str, expected_length: int) -> Iterator[bytes]:
        visited = set()
        try:
            for _ in range(4):
                if url in visited:
                    raise UpdateError("Зацикленное перенаправление обновления.")
                visited.add(url)
                request = Request(
                    url,
                    headers={
                        "Accept": "application/octet-stream",
                        "User-Agent": "OmkalityCraft-Updater",
                    },
                )
                try:
                    response = self.github._opener.open(request, timeout=15)
                except HTTPError as error:
                    status, location = error.code, error.headers.get("Location")
                    error.close()
                    if status in {301, 302, 303, 307, 308} and location:
                        try:
                            if any(
                                ord(char) <= 32 or char == "\\" for char in location
                            ):
                                raise ValueError("Invalid redirect characters")
                            url = github_asset_redirect(urljoin(url, location))
                        except ValueError:
                            raise UpdateError(
                                "Недопустимое перенаправление обновления."
                            ) from None
                        continue
                    raise GitHubAssetUnavailable("GitHub asset unavailable") from None
                with response:
                    if response.status != 200:
                        raise GitHubAssetUnavailable("GitHub asset unavailable")
                    count = 0
                    while chunk := response.read(256 * 1024):
                        count += len(chunk)
                        self.progress(f"Обновляем лаунчер · {count / 1024**2:.1f} МБ")
                        yield chunk
                    if count < expected_length:
                        raise GitHubAssetUnavailable("GitHub asset interrupted")
                    return
            raise UpdateError("Слишком много перенаправлений обновления.")
        except OSError, http.client.HTTPException:
            raise GitHubAssetUnavailable("GitHub asset unavailable") from None

    @contextlib.contextmanager
    def download_file(self, url: str, max_length: int):
        with tempfile.TemporaryFile(dir=self.temporary) as output:
            count = 0
            for chunk in self.fetch(url):
                count += len(chunk)
                if count > max_length:
                    raise exceptions.DownloadLengthMismatchError(
                        "Update exceeds its declared size"
                    )
                output.write(chunk)
            output.seek(0)
            yield output


@dataclass(frozen=True)
class PreparedUpdate:
    version: str
    folder: Path
    entrypoint: Path
    digest: str


def atomic_json(path: Path, document: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(document), encoding="utf-8")
    os.replace(temporary, path)


class LauncherUpdater:
    def __init__(self, root: Path, origin: str, bootstrap: bytes, version: str) -> None:
        self.root, self.origin, self.bootstrap = (
            resolved(root),
            origin.rstrip("/"),
            bootstrap,
        )
        self.version = Version(version)
        self.cache = self.root / "userdata" / "updates"
        self.state_file = self.cache / "state.json"

    def _state(self) -> dict:
        try:
            return json.loads(self.state_file.read_text(encoding="utf-8"))
        except OSError, ValueError:
            return {}

    def active(self) -> PreparedUpdate | None:
        """Last health-checked version, available even if the CDN is unavailable."""
        try:
            record = self._state()["active"]
            folder = inside(self.root, record["folder"])
            if not resolved(folder).is_relative_to(
                resolved(self.root / "app_versions")
            ):
                return None
            executable = inside(folder, record["entrypoint"])
            if not executable.is_file() or Version(record["version"]) <= self.version:
                return None
            return PreparedUpdate(
                record["version"], folder, executable, record["digest"]
            )
        except OSError, ValueError, KeyError, TypeError, ReleaseError:
            return None

    def prepare(self, progress: Callable[[str], None]) -> PreparedUpdate | None:
        progress("Проверяем обновления лаунчера…")
        metadata = self.cache / "metadata"
        targets = self.cache / "downloads"
        for folder in [metadata, targets]:
            folder.mkdir(parents=True, exist_ok=True)
        fetcher = PortableFetcher(self.origin, self.cache / "tmp", progress)
        updater = Updater(
            str(metadata),
            f"{self.origin}/updates/metadata/",
            str(targets),
            f"{self.origin}/updates/targets/",
            fetcher,
            UpdaterConfig(max_root_rotations=32),
            bootstrap=self.bootstrap,
        )
        updater.refresh()
        target = updater.get_targetinfo(f"{current_platform()}/launcher.zip")
        if target is None:
            return None
        try:
            version = target.custom["version"]
            entrypoint = target.custom["entrypoint"]
            if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.+_-]{0,79}", version):
                raise ValueError
            safe_path(entrypoint)
            state = self._state()
            if Version(version) <= self.version:
                return None
            if Version(version) < Version(
                state.get("highest_version", str(self.version))
            ):
                raise UpdateError("Сервер предложил прежнюю версию лаунчера.")
            digest = target.hashes["sha256"]
            if digest in state.get("failed", []):
                raise UpdateError(
                    "Эта версия ранее не запустилась. Ожидаем исправление."
                )
            if target.length > MAX_ARCHIVE:
                raise ValueError
            asset = target.custom.get("github_asset_url")
            if asset is not None:
                github_asset_url(asset, version, current_platform())
        except KeyError, TypeError, ValueError, InvalidVersion:
            raise UpdateError("Описание обновления повреждено.") from None
        active = self.active()
        if (
            active is not None
            and active.digest == digest
            and active.version == version
            and active.entrypoint.relative_to(active.folder).as_posix() == entrypoint
        ):
            return active
        archive = self._download_archive(updater, fetcher, target, asset)
        progress("Подготавливаем новую версию…")
        folder = inside(self.root, f"app_versions/{version}-{digest[:12]}")
        # Never trust a leftover extracted directory: recreate from the verified archive.
        self._extract(archive, folder)
        executable = inside(folder, entrypoint)
        if not executable.is_file():
            raise UpdateError("В обновлении отсутствует программа запуска.")
        if os.name != "nt":
            executable.chmod(executable.stat().st_mode | stat.S_IXUSR)
        return PreparedUpdate(version, folder, executable, digest)

    def _download_archive(
        self,
        updater: Updater,
        fetcher: PortableFetcher,
        target: TargetFile,
        asset: str | None,
    ) -> Path:
        archive = self.cache / "downloads" / f"{target.hashes['sha256']}.zip"
        if updater.find_cached_target(target, str(archive)) is not None:
            return archive
        if asset is None:
            updater.download_target(target, str(archive))
            return archive
        fetcher.use_github_asset(target, asset)
        try:
            updater.download_target(target, str(archive))
        except GitHubAssetUnavailable:
            # A new TUF temporary file restarts from byte zero. Never append
            # mirror bytes to an interrupted primary-source stream.
            fetcher.github_asset = None
            updater.download_target(target, str(archive))
        return archive

    def _extract(self, archive: Path, destination: Path) -> None:
        stage = destination.with_name(destination.name + ".staging")
        if stage.exists():
            self._remove_version(stage)
        stage.mkdir(parents=True)
        try:
            with zipfile.ZipFile(archive) as bundle:
                files = bundle.infolist()
                self._validate_zip(files)
                for member in files:
                    path = inside(stage, member.filename.rstrip("/"))
                    if member.is_dir():
                        path.mkdir(parents=True, exist_ok=True)
                        continue
                    path.parent.mkdir(parents=True, exist_ok=True)
                    with bundle.open(member) as source, path.open("xb") as target:
                        shutil.copyfileobj(source, target, 256 * 1024)
                    mode = member.external_attr >> 16
                    if os.name != "nt" and mode & stat.S_IXUSR:
                        path.chmod(path.stat().st_mode | stat.S_IXUSR)
            if destination.exists():
                self._remove_version(destination)
            os.replace(stage, destination)
        except Exception:
            self._remove_version(stage)
            raise

    @staticmethod
    def _validate_zip(files: list[zipfile.ZipInfo]) -> None:
        if (
            not files
            or len(files) > 20000
            or sum(f.file_size for f in files) > MAX_EXPANDED
        ):
            raise UpdateError("Недопустимый размер обновления.")
        names: set[str] = set()
        for member in files:
            name = member.filename.rstrip("/")
            safe_path(name)
            if (
                name.casefold() in names
                or stat.S_IFMT(member.external_attr >> 16) == stat.S_IFLNK
            ):
                raise UpdateError("Обновление содержит небезопасные пути.")
            if member.file_size > 512 * 1024**2 or member.flag_bits & 1:
                raise UpdateError("Обновление содержит неподдерживаемый файл.")
            names.add(name.casefold())

    def _remove_version(self, path: Path) -> None:
        versions = resolved(self.root / "app_versions")
        target = resolved(path)
        if (
            not target.is_relative_to(versions)
            or target == versions
            or path.is_symlink()
        ):
            raise UpdateError("Недопустимая папка обновления.")
        if path.exists():
            shutil.rmtree(path)

    def handoff(self, update: PreparedUpdate, *, timeout: float = 30) -> bool:
        """The caller releases its instance lock before handoff, reacquiring on failure."""
        nonce = token_hex(24)
        health = self.cache / f"health-{nonce}.json"
        command = [
            str(update.entrypoint),
            "--root",
            str(self.root),
            "--health-file",
            str(health),
            "--health-nonce",
            nonce,
        ]
        try:
            process = subprocess.Popen(command, cwd=self.root, shell=False)
        except OSError:
            state = self._state()
            state["failed"] = [*state.get("failed", [])[-9:], update.digest]
            atomic_json(self.state_file, state)
            return False
        deadline = time.monotonic() + timeout
        healthy = False
        try:
            while time.monotonic() < deadline and process.poll() is None:
                with contextlib.suppress(OSError, ValueError):
                    healthy = (
                        json.loads(health.read_text(encoding="utf-8")).get("nonce")
                        == nonce
                    )
                if healthy:
                    break
                time.sleep(0.05)
            state = self._state()
            if healthy:
                state.update(
                    active={
                        "folder": str(update.folder.relative_to(self.root)).replace(
                            "\\", "/"
                        ),
                        "version": update.version,
                        "entrypoint": str(
                            update.entrypoint.relative_to(update.folder)
                        ).replace("\\", "/"),
                        "digest": update.digest,
                    },
                    highest_version=update.version,
                )
            else:
                if process.poll() is None:
                    process.terminate()
                    with contextlib.suppress(subprocess.TimeoutExpired):
                        process.wait(timeout=5)
                state["failed"] = [*state.get("failed", [])[-9:], update.digest]
            atomic_json(self.state_file, state)
            return healthy
        finally:
            health.unlink(missing_ok=True)


def acknowledge_health(root: Path, path: Path, nonce: str) -> None:
    if not re.fullmatch(r"[0-9a-f]{48}", nonce) or resolved(path).parent != resolved(
        root / "userdata/updates"
    ):
        raise UpdateError("Недопустимый ответ проверки запуска.")
    atomic_json(path, {"nonce": nonce})
