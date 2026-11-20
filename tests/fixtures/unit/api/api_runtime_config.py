"""Test dependencies for api runtime config."""

import pytest

from api.settings.config import Settings


@pytest.fixture
def clean_settings_env(monkeypatch):
    for name in Settings.model_fields:
        monkeypatch.delenv(name.upper(), raising=False)
