import sys
from pathlib import Path

import pytest

from launcher.paths import default_data_dir
from omk.shared.profiles import PROJECT_ROOT


def test_source_data_does_not_follow_working_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    assert default_data_dir() == PROJECT_ROOT / "userdata"


def test_bundled_data_is_beside_executable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    executable = tmp_path / "portable" / "OmkalityCraft"
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(executable))
    assert default_data_dir() == executable.parent / "userdata"


@pytest.mark.parametrize("existing", [None, "userdata", "instances"])
def test_macos_app_keeps_data_beside_the_bundle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, existing: str | None
) -> None:
    extracted = tmp_path / "old launcher"
    executable = extracted / "OmkalityCraft.app/Contents/MacOS/OmkalityCraft"
    if existing:
        (extracted / existing).mkdir(parents=True)
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(executable))
    assert default_data_dir() == extracted / "userdata"
