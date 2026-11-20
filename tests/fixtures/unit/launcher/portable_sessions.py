"""Test dependencies for portable sessions."""

from pathlib import Path

import pytest

from launcher.accounts import AccountService
from launcher.storage import FileSessionStore
from tests.fixtures.fakes import FakeDrasl


@pytest.fixture
def account(tmp_path: Path) -> AccountService:
    return AccountService(
        FakeDrasl(), FileSessionStore(tmp_path / "userdata" / "session.json")
    )
