"""Exercise real Java logging in an isolated folder, without starting Minecraft."""

import argparse
import json
import os
import subprocess
from pathlib import Path
from uuid import uuid4

from launcher.log_policy import prepare_logging
from omk.diagnostics import BoundedLog, collect_output
from omk.logging_runtime import logging_pins, stage_logging_runtime
from omk.profiles import PROJECT_ROOT

SOURCE = """import org.apache.logging.log4j.LogManager;
import org.apache.logging.log4j.Logger;
public class LogFlood {
  public static void main(String[] args) {
    Logger log = LogManager.getLogger("omk.logging.lab");
    String payload = new String(new char[1000]).replace('\\0', 'x');
    for (int i = 0; i < 40000; i++) log.info("entry-" + i + " " + payload);
    try { throw new IllegalStateException("omk-stack-probe"); }
    catch (Exception error) { log.error("expected lab exception", error); }
    log.info("Проверка UTF-8: literal ${java:version}");
    LogManager.shutdown();
  }
}
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--java", type=Path, required=True)
    parser.add_argument("--javac", type=Path, required=True)
    args = parser.parse_args()
    java, javac = args.java.resolve(), args.javac.resolve()
    if not java.is_file() or not javac.is_file():
        parser.error("Supply explicit existing Java and javac executables")
    lab = PROJECT_ROOT / ".local" / ("logging probe " + uuid4().hex[:8])
    lab.mkdir(parents=True)
    jars = stage_logging_runtime(lab)
    classpath = os.pathsep.join(str(path) for path in jars)
    source = lab / "LogFlood.java"
    source.write_text(SOURCE, encoding="utf-8")
    subprocess.run(
        [
            str(javac),
            "-source",
            "8",
            "-target",
            "8",
            "-proc:none",
            "-encoding",
            "UTF-8",
            "-classpath",
            classpath,
            "-d",
            str(lab),
            str(source),
        ],
        capture_output=True,
        check=True,
        timeout=60,
    )
    config = prepare_logging("1.12.2", lab / "logging")
    process = subprocess.Popen(
        [
            str(java),
            "-Dfile.encoding=UTF-8",
            "-Dlog4j.configurationFile=" + config.as_uri(),
            "-cp",
            classpath + os.pathsep + str(lab),
            "LogFlood",
        ],
        cwd=lab,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    console = lab / "userdata/logs/dj2-game.log"
    try:
        collect_output(process.stdout, BoundedLog(console))
        if process.wait(timeout=30) != 0:
            raise RuntimeError("Java logging probe exited with an error")
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=10)
    native = sorted((lab / "logs").glob("*"))
    text = (lab / "logs/latest.log").read_text(encoding="utf-8")
    console_text = console.read_text(encoding="utf-8")
    checks = {
        "native_rotation": len(native) == 4
        and all(p.stat().st_size < 9 * 1024**2 for p in native),
        "console_rotation": len(list(console.parent.glob("dj2-game.log*"))) == 3,
        "stack_preserved": "IllegalStateException" in text and "LogFlood.main" in text,
        "latest_event_preserved": "entry-39999" in text,
        "utf8_and_literal_lookup": "Проверка UTF-8: literal ${java:version}" in text
        and "Проверка UTF-8" in console_text,
        "no_config_errors": "ERROR StatusLogger" not in console_text
        and "ERROR StatusConsoleListener" not in console_text,
    }
    report = {
        "ok": all(checks.values()),
        "checks": checks,
        "folder": str(lab.relative_to(PROJECT_ROOT)),
        "logging": logging_pins()["version"],
        "native_bytes": {p.name: p.stat().st_size for p in native},
        "console_bytes": sum(
            p.stat().st_size for p in console.parent.glob("dj2-game.log*")
        ),
    }
    (lab / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
