"""Pack cards and a compact account panel, without session-management clutter."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from launcher.memory import MemorySnapshot, Preferences
from launcher.skin_view import SkinView
from launcher.widgets import BusyButton, PackCard
from omk.profiles import load_profiles


class Dashboard(QWidget):
    install_requested = Signal(str)
    cancel_requested = Signal()
    message = Signal(str)

    def __init__(
        self,
        preferences: Preferences | None = None,
        machine: MemorySnapshot | None = None,
    ) -> None:
        super().__init__()
        self.preferences = preferences or Preferences()
        machine = machine or MemorySnapshot.read()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 12, 0, 0)
        layout.setSpacing(22)
        content = QWidget()
        packs = QVBoxLayout(content)
        packs.setContentsMargins(0, 0, 8, 0)
        heading = QLabel("Выберите своё приключение")
        heading.setStyleSheet("font-size:21px")
        packs.addWidget(heading)
        self.cards: dict[str, PackCard] = {}
        for profile in load_profiles():
            card = PackCard(profile, machine, self.preferences.memory.get(profile.id))
            self.cards[profile.id] = card
            card.action.clicked.connect(
                lambda checked=False, pack_id=profile.id: self.install_requested.emit(
                    pack_id
                )
            )
            card.cancel.clicked.connect(self.cancel_requested.emit)
            card.memory.changed.connect(
                lambda value, pack_id=profile.id: self._save_memory(pack_id, value)
            )
            packs.addWidget(card)
        packs.addStretch()
        scroll = QScrollArea()
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(content)
        layout.addWidget(scroll, 1)
        layout.addWidget(self._account_panel())

    def _save_memory(self, pack_id: str, value: int) -> None:
        try:
            self.preferences.save_memory(pack_id, value)
        except OSError, ValueError:
            self.message.emit(
                "Не удалось сохранить настройку памяти. Проверьте доступ к папке лаунчера."
            )

    def _account_panel(self) -> QFrame:
        account = QFrame()
        account.setProperty("panel", True)
        account.setMinimumWidth(265)
        account.setMaximumWidth(300)
        panel = QVBoxLayout(account)
        panel.setContentsMargins(21, 20, 21, 20)
        self.greeting = QLabel("Ваш профиль")
        self.greeting.setObjectName("greeting")
        self.greeting.setStyleSheet("font-size:21px")
        panel.addWidget(self.greeting)
        self.skin_preview = SkinView()
        panel.addWidget(self.skin_preview, 1)
        self.upload_button = BusyButton("Загрузить скин…")
        self.upload_button.setObjectName("uploadSkin")
        panel.addWidget(self.upload_button)
        self.change_password = BusyButton("Сменить пароль")
        self.change_password.setProperty("quiet", True)
        self.change_password.setObjectName("changePassword")
        panel.addWidget(self.change_password)
        return account
