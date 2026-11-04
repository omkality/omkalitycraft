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
from tests.fakes import FakeDrasl


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
    # Avoid an exception traceback retaining the frame that owns these live widgets.
    # The real HTTP failure has independent coverage without Qt widget ownership.
    window._install_failed("dj2", ReleaseError(message))
    window.resize(1020, 680)
    window.show()
    qtbot.waitExposed(window)
    assert "Проверьте соединение" in card.state_label.text()
    assert card.state_label.wordWrap()
    assert card.action.text() == "Повторить"
    assert card.installed
    assert window.width() == 1020
    assert card.state_label.geometry().right() <= card.contentsRect().right()
