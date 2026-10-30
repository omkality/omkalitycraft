"""Bounded, resumable downloads and verified, portable installation state."""

import json
import os
import platform
import shutil
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request

from launcher.releases import (
    MAX_MANIFEST_BYTES,
    Artifact,
    Release,
    ReleaseError,
    inside,
    read_release,
    sha256_file,
)
from omk.drasl import DraslClient


class InstallCancelled(ReleaseError):
    pass


def current_platform() -> str:
    operating_system = {"Windows": "windows", "Linux": "linux", "Darwin": "macos"}.get(
        platform.system()
    )
    architecture = {
        "amd64": "x64",
        "x86_64": "x64",
        "arm64": "arm64",
        "aarch64": "arm64",
    }.get(platform.machine().lower())
    if operating_system is None or architecture is None:
        raise ReleaseError("Эта платформа пока не поддерживается.")
    return f"{operating_system}-{architecture}"


@dataclass(frozen=True)
class Progress:
    stage: str
    done: int
    total: int
    filename: str = ""

    @property
    def percent(self) -> int:
        return min(100, int(self.done * 100 / max(1, self.total)))


class ReleaseClient:
    def __init__(self, origin: str, trusted_keys: dict[str, str]) -> None:
        self.transport = DraslClient(origin, timeout=20)
        self.trusted_keys = trusted_keys

    def fetch(self, pack_id: str, target: str | None = None) -> Release:
        target = target or current_platform()
        request = Request(
            f"{self.transport.base_url}/releases/{quote(pack_id, safe='')}/{target}/manifest"
        )
        try:
            with self.transport._opener.open(request, timeout=20) as response:
                data = response.read(MAX_MANIFEST_BYTES + 1)
        except HTTPError as error:
            status = error.code
            error.close()
            if status == 404:
                raise ReleaseError(
                    "Сборка для вашей платформы ещё готовится."
                ) from None
            raise ReleaseError(
                "Не удалось получить сборку. Попробуйте позже."
            ) from None
        release = read_release(data, self.trusted_keys)
        if release.pack_id != pack_id or release.platform != target:
            raise ReleaseError("Сервер вернул описание другой сборки или платформы.")
        return release


class Installer:
    def __init__(self, root: Path, client: ReleaseClient, *, workers: int = 4) -> None:
        self.root = root.resolve()
        self.client = client
        self.workers = max(1, min(4, workers))
        self.cancel = threading.Event()
        self._lock = threading.Lock()
        self._bytes: dict[str, int] = {}
        self._hash_locks: dict[str, threading.Lock] = {}
        self._last_progress = 0.0

    def directory(self, pack_id: str) -> Path:
        return inside(self.root, f"instances/{pack_id}")

    def local_state(self, pack_id: str) -> dict:
        try:
            state = self.directory(pack_id) / ".omk-install.json"
            with state.open("rb") as file:
                record = json.loads(file.read(17 * MAX_MANIFEST_BYTES + 65536))
            release = read_release(
                json.dumps(record["release"]).encode(), self.client.trusted_keys
            )
            if release.pack_id != pack_id or release.platform != current_platform():
                return {"state": "missing"}
            history = [
                read_release(json.dumps(value).encode(), self.client.trusted_keys)
                for value in record.get("history", [])
            ]
            if len(history) > 16 or any(
                value.pack_id != pack_id or value.platform != release.platform
                for value in history
            ):
                return {"state": "missing"}
            complete = record.get("complete") is True and all(
                inside(self.directory(pack_id), file.path).is_file()
                and inside(self.directory(pack_id), file.path).stat().st_size
                == file.size
                for file in release.files
            )
            return {
                "state": "installed" if complete else "incomplete",
                "version": release.version,
                "release": release,
                "history": history,
            }
        except OSError, ValueError, KeyError, TypeError, ReleaseError:
            return {"state": "missing"}

    def install(self, release: Release, progress: Callable[[Progress], None]) -> Path:
        if release.platform != current_platform():
            raise ReleaseError("Эта сборка подготовлена для другой платформы.")
        folder = self.directory(release.pack_id)
        folder.mkdir(parents=True, exist_ok=True)
        self._bytes = {}
        self._hash_locks = {file.sha256: threading.Lock() for file in release.files}
        progress(Progress("Проверяем файлы", 0, release.total_size))
        missing: list[Artifact] = []
        for file in release.files:
            self._check_cancel()
            path = inside(folder, file.path)
            valid = (
                path.is_file()
                and path.stat().st_size == file.size
                and sha256_file(path) == file.sha256
            )
            self._bytes[file.path] = file.size if valid else 0
            if not valid:
                missing.append(file)
            self._emit_progress(
                progress,
                Progress(
                    "Проверяем файлы",
                    sum(self._bytes.values()),
                    release.total_size,
                    file.path,
                ),
            )
        if (
            shutil.disk_usage(folder).free
            < sum(file.size for file in missing) + 256 * 1024**2
        ):
            raise ReleaseError("Недостаточно свободного места для сборки.")
        local = self.local_state(release.pack_id)
        history = {
            value.digest: value
            for value in [
                *local.get("history", []),
                *([local["release"]] if "release" in local else []),
            ]
            if value.digest != release.digest
        }
        if len(history) > 16:
            raise ReleaseError("Сначала завершите предыдущее обновление сборки.")
        self._state(folder, release, complete=False, history=list(history.values()))
        with ThreadPoolExecutor(max_workers=self.workers) as pool:
            futures = [
                pool.submit(self._download, release, file, folder, progress)
                for file in missing
            ]
            try:
                for future in futures:
                    future.result()
            except Exception:
                self.cancel.set()
                raise
        self._check_cancel()
        retained = {file.path.casefold() for file in release.files}
        for previous in history.values():
            for file in previous.files:
                path = inside(folder, file.path)
                if file.path.casefold() not in retained and path.is_file():
                    # Remove only files owned by the previous signed release.
                    path.unlink()
        self._state(folder, release, complete=True)
        progress(Progress("Готово к игре", release.total_size, release.total_size))
        return folder

    def _state(
        self,
        folder: Path,
        release: Release,
        *,
        complete: bool,
        history: list[Release] | None = None,
    ) -> None:
        path = folder / ".omk-install.json"
        temporary = folder / ".omk-install.tmp"
        temporary.write_text(
            json.dumps(
                {
                    "release": release.envelope,
                    "complete": complete,
                    "history": [value.envelope for value in (history or [])],
                }
            ),
            encoding="utf-8",
        )
        os.replace(temporary, path)

    def _check_cancel(self) -> None:
        if self.cancel.is_set():
            raise InstallCancelled("Загрузка приостановлена. Её можно продолжить.")

    def _download(
        self,
        release: Release,
        file: Artifact,
        folder: Path,
        progress: Callable[[Progress], None],
    ) -> None:
        with self._hash_locks[file.sha256]:
            self._download_one(release, file, folder, progress)

    def _download_one(
        self,
        release: Release,
        file: Artifact,
        folder: Path,
        progress: Callable[[Progress], None],
    ) -> None:
        temporary = inside(self.root, f"cache/downloads/{file.sha256}.part")
        temporary.parent.mkdir(parents=True, exist_ok=True)
        for attempt in range(3):
            self._check_cancel()
            try:
                self._stream(release, file, temporary, progress)
                break
            except HTTPError as error:
                if error.code not in {429, 502, 503, 504} or attempt == 2:
                    error.close()
                    raise ReleaseError(
                        "Не удалось скачать файл сборки. Попробуйте ещё раз."
                    ) from None
                error.close()
                self.cancel.wait(min(5, 1 + attempt * 2))
            except OSError:
                if attempt == 2:
                    raise ReleaseError(
                        "Загрузка прервалась. Проверьте соединение и повторите."
                    ) from None
                self.cancel.wait(0.5)
        if (
            sha256_file(temporary) != file.sha256
            or temporary.stat().st_size != file.size
        ):
            temporary.unlink(missing_ok=True)
            raise ReleaseError("Файл сборки не прошёл проверку. Повторите загрузку.")
        destination = inside(folder, file.path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        os.replace(temporary, destination)
        if file.executable and os.name != "nt":
            destination.chmod(destination.stat().st_mode | 0o100)

    def _stream(
        self,
        release: Release,
        file: Artifact,
        temporary: Path,
        progress: Callable[[Progress], None],
    ) -> None:
        offset = temporary.stat().st_size if temporary.exists() else 0
        if (
            offset == file.size
            and temporary.exists()
            and sha256_file(temporary) == file.sha256
        ):
            self._notify(file.path, file.size, release, progress)
            return
        if offset >= file.size:
            temporary.unlink(missing_ok=True)
            offset = 0
        url = (
            f"{self.client.transport.base_url}/releases/{release.pack_id}/{release.platform}"
            f"/files/{quote(file.path, safe='/')}"
        )
        request = Request(url, headers={"Range": f"bytes={offset}-"} if offset else {})
        with self.client.transport._opener.open(request, timeout=20) as response:
            if response.status == 206:
                if not response.headers.get("Content-Range", "").startswith(
                    f"bytes {offset}-"
                ):
                    raise ReleaseError("Сервер вернул неверный диапазон файла.")
            elif response.status == 200:
                offset = 0
            else:
                raise ReleaseError("Неожиданный ответ при скачивании сборки.")
            with temporary.open("ab" if offset else "wb") as output:
                while True:
                    self._check_cancel()
                    data = response.read(min(256 * 1024, file.size - offset + 1))
                    if not data:
                        break
                    offset += len(data)
                    if offset > file.size:
                        raise ReleaseError(
                            "Размер скачиваемого файла превышает заявленный."
                        )
                    output.write(data)
                    self._notify(file.path, offset, release, progress)
            if offset < file.size:
                raise OSError("Download interrupted before the expected length")

    def _notify(
        self,
        path: str,
        size: int,
        release: Release,
        progress: Callable[[Progress], None],
    ) -> None:
        with self._lock:
            self._bytes[path] = size
            self._emit_progress(
                progress,
                Progress(
                    "Скачиваем сборку",
                    sum(self._bytes.values()),
                    release.total_size,
                    path,
                ),
            )

    def _emit_progress(
        self, callback: Callable[[Progress], None], value: Progress
    ) -> None:
        now = time.monotonic()
        if now - self._last_progress >= 0.05 or value.done >= value.total:
            self._last_progress = now
            callback(value)
