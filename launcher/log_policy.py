"""Versioned Java logging adapter; unrelated packs keep their declared configuration."""

from pathlib import Path

from omk.diagnostics import prune_native_archives, prune_reports
from omk.fs import resolved

FORGE_112 = """<?xml version="1.0" encoding="UTF-8"?>
<Configuration status="WARN">
  <Appenders>
    <Console name="SysOut" target="SYSTEM_OUT">
      <PatternLayout charset="UTF-8" pattern="[%d{yyyy-MM-dd HH:mm:ss.SSS}] [%t/%level] [%logger]: %msg{nolookups}%n"/>
    </Console>
    <RollingRandomAccessFile name="File" fileName="logs/latest.log" filePattern="logs/latest-%i.log.gz">
      <PatternLayout charset="UTF-8" pattern="[%d{yyyy-MM-dd HH:mm:ss.SSS}] [%t/%level] [%logger]: %msg{nolookups}%n"/>
      <Policies><OnStartupTriggeringPolicy/><SizeBasedTriggeringPolicy size="8MB"/></Policies>
      <DefaultRolloverStrategy max="3" fileIndex="min"/>
    </RollingRandomAccessFile>
  </Appenders>
  <Loggers>
    <Root level="info">
      <Filters><MarkerFilter marker="NETWORK_PACKETS" onMatch="DENY" onMismatch="NEUTRAL"/></Filters>
      <AppenderRef ref="SysOut"/><AppenderRef ref="File"/>
    </Root>
  </Loggers>
</Configuration>
"""


def prepare_logging(minecraft: str, directory: Path) -> Path | None:
    if minecraft != "1.12.2":
        return None
    if resolved(directory) != directory:
        raise OSError("Linked logging configuration directory")
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "forge-1.12.2.xml"
    if path.is_symlink() or path.is_junction() or directory.resolve() != directory:
        raise OSError("Linked logging configuration")
    if not path.exists() or path.read_text(encoding="utf-8") != FORGE_112:
        path.write_text(FORGE_112, encoding="utf-8")
    return path


def prune_game_logs(root: Path, folder: Path):
    """Called only before launch or after the owned process has stopped."""
    prune_reports(root, folder / "crash-reports")
    prune_reports(root, folder, jvm=True)
    prune_native_archives(root, folder / "logs")
