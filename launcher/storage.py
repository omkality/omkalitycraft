"""Portable session files. Bearer tokens are sensitive; no encryption is claimed."""

import os
import tempfile
from contextlib import suppress
from pathlib import Path

from launcher.session import Session, SessionStoreError


class FileSessionStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> Session | None:
        try:
            if not self.path.exists():
                return None
            with self.path.open("rb") as file:
                data = file.read(32769)
            return Session.deserialize(data.decode("utf-8"))
        except OSError, ValueError, TypeError:
            raise SessionStoreError(
                "Не удалось прочитать сохранённый вход. Можно войти заново."
            ) from None

    def save(self, session: Session) -> None:
        temporary: Path | None = None
        try:
            self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            descriptor, name = tempfile.mkstemp(
                prefix=".session-", suffix=".tmp", dir=self.path.parent
            )
            temporary = Path(name)
            with os.fdopen(descriptor, "w", encoding="utf-8") as file:
                file.write(session.serialize())
                file.flush()
                os.fsync(file.fileno())
            os.replace(temporary, self.path)
        except OSError:
            raise SessionStoreError(
                "Не удалось запомнить вход в папке лаунчера."
            ) from None
        finally:
            if temporary is not None:
                with suppress(OSError):
                    temporary.unlink(missing_ok=True)

    def clear(self) -> None:
        try:
            self.path.unlink(missing_ok=True)
        except OSError:
            raise SessionStoreError("Не удалось удалить сохранённый вход.") from None
