import threading
from types import SimpleNamespace
from urllib.error import URLError

import pytest
from PySide6.QtCore import QObject

from launcher.accounts import AccountService
from launcher.app import LauncherWindow
from launcher.controller import InstallController
from launcher.game import GameRunner
from launcher.releases import ReleaseError
from launcher.storage import FileSessionStore
from tests.fixtures.fakes import FakeDrasl


def test_previously_installed_pack_repairs_and_launches_from_one_action(
    qtbot, tmp_path, monkeypatch
):
    service = AccountService(FakeDrasl(), FileSessionStore(tmp_path / "session.json"))
    installer = SimpleNamespace(
        local_state=lambda _pack: {"state": "incomplete", "install_complete": True}
    )
    window = LauncherWindow(
        service, installer=installer, runner=GameRunner(tmp_path), auto_restore=False
    )
    qtbot.addWidget(window)
    window._authenticated(service.login("test_player", "test-password"))
    calls = []
    monkeypatch.setattr(
        window.installation,
        "start",
        lambda pack_id, **options: calls.append((pack_id, options)),
    )
    card = window.home_page.cards["dj2"]
    qtbot.waitUntil(lambda: card.action.text() == "Проверить и играть")
    card.action.click()
    assert [(pack_id, options["play"]) for pack_id, options in calls] == [("dj2", True)]


@pytest.mark.parametrize(
    "error",
    [
        URLError("owned fixture offline"),
        ReleaseError("invalid signed manifest"),
        ReleaseError(
            "Нужно обновление лаунчера. Проверьте соединение и перезапустите OmkalityCraft."
        ),
    ],
)
def test_play_never_falls_back_to_cached_pack_when_manifest_check_fails(
    qtbot, tmp_path, error
):
    service = AccountService(FakeDrasl(), FileSessionStore(tmp_path / "session.json"))
    service.login("test_player", "test-password")
    session = service.store.path.read_bytes()
    artifact = tmp_path / "instances/dj2/mods/keep.jar"
    artifact.parent.mkdir(parents=True)
    artifact.write_bytes(b"owned installed sentinel")
    calls = []

    def fetch(_pack):
        calls.append("fetch")
        raise error

    def forbidden(*_args, **_kwargs):
        calls.append("install_or_launch")
        raise AssertionError("Manifest check must finish before preparation or launch")

    installer = SimpleNamespace(
        client=SimpleNamespace(fetch=fetch),
        cancel=threading.Event(),
        local_state=lambda _pack: {"state": "installed", "release": object()},
        directory=lambda _pack: artifact.parent.parent,
        install=forbidden,
    )
    parent = QObject()
    controller = InstallController(
        installer, service, SimpleNamespace(start=forbidden), parent
    )
    with qtbot.waitSignal(controller.failed, timeout=5000) as failed:
        controller.start("dj2", play=True)
    assert failed.args == ["dj2", error]
    assert calls == ["fetch"]
    assert controller.busy is False
    assert service.store.path.read_bytes() == session
    assert artifact.read_bytes() == b"owned installed sentinel"
    assert controller.pool.waitForDone(5000)


def test_previous_game_blocks_pack_changes_after_restart(qtbot, tmp_path):
    service = AccountService(FakeDrasl(), FileSessionStore(tmp_path / "session.json"))
    release = object()
    blocked = ReleaseError("Minecraft уже запущен.")
    calls = []

    def check(manifest):
        assert manifest is release
        calls.append("previous game")
        raise blocked

    def forbidden(*_args, **_kwargs):
        calls.append("install or launch")
        raise AssertionError("The running game must be checked before altering files")

    installer = SimpleNamespace(
        client=SimpleNamespace(fetch=lambda _pack: release),
        cancel=threading.Event(),
        install=forbidden,
    )
    runner = SimpleNamespace(ensure_stopped=check, start=forbidden)
    parent = QObject()
    controller = InstallController(installer, service, runner, parent)
    with qtbot.waitSignal(controller.failed, timeout=5000) as result:
        controller.start("dj2", play=True)
    assert result.args == ["dj2", blocked]
    assert calls == ["previous game"]
    assert controller.pool.waitForDone(5000)


def test_launcher_dock_follows_the_hidden_game_lifecycle(qtbot, tmp_path, monkeypatch):
    service = AccountService(FakeDrasl(), FileSessionStore(tmp_path / "session.json"))
    window = LauncherWindow(service, runner=GameRunner(tmp_path), auto_restore=False)
    qtbot.addWidget(window)
    seen = []
    monkeypatch.setattr("launcher.app.set_launcher_dock_visible", seen.append)
    result = None
    game = SimpleNamespace(
        poll=lambda: result,
        diagnostics_done=threading.Event(),
        logging_failed=threading.Event(),
        log_path=tmp_path / "game.log",
        crash_report=None,
    )
    window.show()
    window._installed(
        "dj2", SimpleNamespace(game=game, release=SimpleNamespace(version="2.23.4"))
    )
    assert window.isHidden() and seen == [False]
    result = 0
    game.diagnostics_done.set()
    window._poll_game()
    assert window.isVisible() and seen == [False, True]


@pytest.mark.parametrize(
    "message",
    [
        "Не удалось проверить актуальную версию сборки. Проверьте соединение и повторите.",
        "Нужно обновление лаунчера. Проверьте соединение и перезапустите OmkalityCraft.",
    ],
    ids=["network", "launcher-minimum"],
)
def test_manifest_error_is_readable_on_minimum_launcher(qtbot, tmp_path, message):
    service = AccountService(FakeDrasl(), FileSessionStore(tmp_path / "session.json"))
    window = LauncherWindow(service, runner=GameRunner(tmp_path), auto_restore=False)
    qtbot.addWidget(window)
    window._authenticated(service.login("test_player", "test-password"))
    card = window.home_page.cards["dj2"]
    card.set_local_state({"state": "installed", "version": "2.21.3-omk.4"})
    # Transport has independent coverage; this test renders the supplied warning.
    window._install_failed("dj2", ReleaseError(message))
    window.resize(1020, 680)
    with qtbot.waitExposed(window):
        window.show()
    assert "Проверьте соединение" in card.state_label.text()
    assert card.state_label.wordWrap()
    assert card.action.text() == "Повторить"
    assert card.installed
    assert window.width() == 1020
    assert card.state_label.geometry().right() <= card.contentsRect().right()
