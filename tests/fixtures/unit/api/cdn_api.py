"""Test dependencies for cdn api."""

from pathlib import Path

import pytest

from api.settings.config import settings


@pytest.fixture
def cdn_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(settings, "content_root", str(tmp_path))
    return tmp_path
