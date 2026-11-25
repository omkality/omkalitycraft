"""Validate one complete, isolated Apple Silicon DJ2 launch and crash."""

import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
from urllib.request import urlopen

repository = Path.cwd()
sys.path.insert(0, str(repository))

from launcher.install import Installer, ReleaseClient
from launcher.releases import inside
from omk.labs.launcher.client_crash_fixture import (
    build_crash_agent, COMPILER_SHA256, COMPILER_SOURCE,
)

origin = "https://138.124.40.35"
keys = json.loads((repository / "launcher/assets/release-keys.json").read_text())
client = ReleaseClient(origin, keys, minimum_generations={"dj2": 2})
release = client.fetch("dj2", "macos-arm64")
assert release.platform == "macos-arm64" and release.version == "2.23.4-omk.14"
pin = json.loads((repository / "profiles/lab/mcmcp.json").read_text())["artifacts"][0]


def fetch(url, file, size_limit, digest):
    with urlopen(url, timeout=40) as response:
        data = response.read(size_limit + 1)
    assert len(data) <= size_limit and hashlib.sha256(data).hexdigest() == digest
    file.write_bytes(data)


def diagnostics(state, log):
    if state.is_file():
        details = json.loads(state.read_text())
        print("Observed phase, Java exit and dialog count:", details.get("phase"),
              details.get("game_exit"), details.get("crash_dialog_count"), flush=True)
    if not log.is_file():
        print("Java did not write a game log", flush=True)
        return
    lines = log.read_text(errors="replace").splitlines()
    relevant = re.compile(
        r"exception|fatal|OpenGL|out.?of.?memory|CrashAssistantJarInJarHelper|crash report|MCMCP instance",
        re.I,
    )
    sensitive = re.compile(r"token|credential|password|secret|authorization", re.I)
    matches = [line[:550] for line in lines if relevant.search(line) and not sensitive.search(line)]
    for line in matches[:4] + matches[-22:]:
        print(line, flush=True)
    print("Last Java log class:", re.sub(r":.*", "", lines[-1])[:120] if lines else "", flush=True)


def finish(process, marker):
    marker.touch()
    try:
        process.wait(timeout=25)
    except subprocess.TimeoutExpired:
        process.terminate()
        process.wait(timeout=15)


def exercise(scripts, env, lab, mode, log):
    state = lab / "probe-state.json"
    state.unlink(missing_ok=True)
    process = subprocess.Popen([sys.executable, "-u", str(scripts / "probe.py"), mode], env=env)
    try:
        for _ in range(65):
            if state.exists() and json.loads(state.read_text())["phase"] == "java-started":
                break
            assert process.poll() is None, "Graphical client exited before launch"
            time.sleep(1)
        subprocess.run(
            [sys.executable, "-u", str(scripts / "check_mcp.py"), mode, "--trigger"],
            env=env, check=True, timeout=400,
        )
        for _ in range(55):
            value = json.loads(state.read_text())
            if value["phase"] == "verified" and value["ok"]:
                print("MACOS_DJ2_VERIFIED", mode, value["game_exit"], value["crash_dialog_count"], flush=True)
                return
            assert value["phase"] != "unexpected-result"
            time.sleep(1)
        raise RuntimeError("Native macOS crash verification timed out")
    except (subprocess.SubprocessError, RuntimeError, AssertionError):
        diagnostics(state, log)
        raise
    finally:
        finish(process, lab / "request-close-validated-probe")


with tempfile.TemporaryDirectory(prefix="client-crash-lab-macos-", dir=os.environ["RUNNER_TEMP"]) as scope:
    lab = Path(scope).resolve()
    (lab / "OWNED_CRASH_PROBE").write_text("isolated Apple Silicon acceptance")
    tools = lab / "tooling"
    tools.mkdir()
    fetch(COMPILER_SOURCE, tools / "ecj.jar", 6_000_000, COMPILER_SHA256)
    fetch(pin["source"], tools / pin["name"], pin["size"], pin["sha256"])
    root = lab / "client"
    installer = Installer(root, client)
    last = 0.0

    def progress(snapshot):
        global last
        now = time.monotonic()
        if now - last > 20:
            print("Installer progressing", flush=True)
            last = now

    folder = installer.install(release, progress, clean_mods=True)
    print("Verified signed macOS DJ2", release.version, len(release.files), release.digest, flush=True)
    fixture = build_crash_agent(inside(folder, release.launch["java"]), tools / "ecj.jar", lab)
    manifest = lab / "manifest.json"
    manifest.write_text(json.dumps(release.envelope))
    (lab / "stage.json").write_text(json.dumps({
        "game": str(folder), "root": str(root), "manifest": str(manifest), "agent": str(fixture),
    }))
    env = {
        **os.environ, "OMK_CRASH_PROBE_ROOT": str(lab), "OMK_CRASH_TEST_REPO": str(repository),
        "OMK_CRASH_TOOLING": str(tools),
    }
    scripts = Path(__file__).resolve().parent
    log = root / "userdata/logs/dj2-game.log"
    for mode in ("report", "no-report", "normal"):
        exercise(scripts, env, lab, mode, log)
