import sys
from pathlib import Path

import pytest

from launcher.paths import default_data_dir
from omk.profiles import PROJECT_ROOT


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
