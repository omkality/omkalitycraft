"""Stage accepted client reports for the existing owner-only Windows SSH channel."""

import json
import os
import re
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path

from omk.observability.incidents import MAX_REPORT_BYTES
from omk.shared.fs import resolved

_FILE = re.compile(r"client-crash-[a-f0-9]{32}\.json")
_MAX_EXPORTS = 20


@dataclass(frozen=True)
class ReportRelay:
    """Publish bounded exports owned by the operator and readable by the owner SSH group."""

    directory: Path

    def publish(self, report_id: str, report: dict) -> Path:
        """Write one atomic export and keep the most recent relay files."""
        name = f"client-crash-{report_id}.json"
        if _FILE.fullmatch(name) is None or report.get("id") != report_id:
            raise ValueError("Report ID does not match export")
        if os.name != "posix" or not self.directory.is_absolute():
            raise OSError("The report relay requires an absolute POSIX directory")
        info = self.directory.stat()
        if (
            resolved(self.directory) != self.directory
            or not stat.S_ISDIR(info.st_mode)
            or info.st_uid != os.geteuid()
            or info.st_mode & 0o027
            or info.st_mode & 0o050 != 0o050
        ):
            raise PermissionError(
                "Report relay must be restricted to the owner and SSH group"
            )
        data = json.dumps(report, ensure_ascii=False).encode("utf-8")
        if len(data) > MAX_REPORT_BYTES:
            raise ValueError("Client crash report is too large")

        path = self.directory / name
        with tempfile.NamedTemporaryFile(
            dir=self.directory, prefix=".client-crash-", delete=False
        ) as file:
            temporary = Path(file.name)
            try:
                file.write(data)
                file.flush()
                os.fchown(file.fileno(), -1, info.st_gid)
                os.fchmod(file.fileno(), 0o640)
                os.fsync(file.fileno())
                os.replace(temporary, path)
            finally:
                temporary.unlink(missing_ok=True)
        self._prune(path)
        return path

    def _prune(self, current: Path):
        copies = []
        for path in self.directory.iterdir():
            if path == current or _FILE.fullmatch(path.name) is None:
                continue
            try:
                info = path.lstat()
            except FileNotFoundError:
                continue
            if stat.S_ISREG(info.st_mode):
                copies.append((info.st_mtime_ns, path))
        for _, path in sorted(copies, reverse=True)[_MAX_EXPORTS - 1 :]:
            path.unlink(missing_ok=True)
