"""Versioned Java logging adapter; unrelated packs keep their declared configuration."""

import os
from pathlib import Path
from string import Template

from omk.diagnostics import prune_native_archives, prune_reports
from omk.fs import resolved


def forge_log_settings(environment=None) -> dict[str, int]:
    env = os.environ if environment is None else environment
    settings = {}
    for suffix, default, maximum in (("MIB", 8, 64), ("FILES", 3, 10)):
        name = "OMK_FORGE_LOG_" + suffix
        raw = env.get(name, str(default))
        if (
            not isinstance(raw, str)
            or not raw.isascii()
            or not raw.isdecimal()
            or len(raw) > 2
            or not 1 <= int(raw) <= maximum
        ):
            raise ValueError("Invalid " + name)
        settings[suffix.lower()] = int(raw)
    return settings


_FORGE_112 = Template("""<?xml version="1.0" encoding="UTF-8"?>
<Configuration status="WARN">
  <Appenders>
    <Console name="SysOut" target="SYSTEM_OUT">
      <PatternLayout charset="UTF-8" pattern="[%d{yyyy-MM-dd HH:mm:ss.SSS}] [%t/%level] [%logger]: %msg{nolookups}%n"/>
    </Console>
    <RollingRandomAccessFile name="File" fileName="logs/latest.log" filePattern="logs/latest-%i.log.gz">
      <PatternLayout charset="UTF-8" pattern="[%d{yyyy-MM-dd HH:mm:ss.SSS}] [%t/%level] [%logger]: %msg{nolookups}%n"/>
      <Policies><OnStartupTriggeringPolicy/><SizeBasedTriggeringPolicy size="${mib}MB"/></Policies>
      <DefaultRolloverStrategy max="$files" fileIndex="min"/>
    </RollingRandomAccessFile>
  </Appenders>
  <Loggers>
    <Root level="info">
      <Filters><MarkerFilter marker="NETWORK_PACKETS" onMatch="DENY" onMismatch="NEUTRAL"/></Filters>
      <AppenderRef ref="SysOut"/><AppenderRef ref="File"/>
    </Root>
  </Loggers>
</Configuration>
""")

FORGE_112 = _FORGE_112.substitute(forge_log_settings({}))


def prepare_logging(
    minecraft: str, directory: Path, *, environment=None
) -> Path | None:
    if minecraft != "1.12.2":
        return None
    text = _FORGE_112.substitute(forge_log_settings(environment))
    if resolved(directory) != directory:
        raise OSError("Linked logging configuration directory")
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "forge-1.12.2.xml"
    if path.is_symlink() or path.is_junction() or directory.resolve() != directory:
        raise OSError("Linked logging configuration")
    if not path.exists() or path.read_text(encoding="utf-8") != text:
        path.write_text(text, encoding="utf-8")
    return path


def prune_game_logs(root: Path, folder: Path):
    """Called only before launch or after the owned process has stopped."""
    prune_reports(root, folder / "crash-reports")
    prune_reports(root, folder, jvm=True)
    prune_native_archives(root, folder / "logs")
