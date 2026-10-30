"""Pack cards and a compact account panel, without session-management clutter."""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from launcher.skin_view import SkinView
from launcher.widgets import BusyButton, PackCard
from omk.profiles import load_profiles


class Dashboard(QWidget):
    install_requested = Signal(str)
    cancel_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 12, 0, 0)
        layout.setSpacing(22)
        packs = QVBoxLayout()
        heading = QLabel("Выберите своё приключение")
        heading.setStyleSheet("font-size:21px")
        packs.addWidget(heading)
        self.cards: dict[str, PackCard] = {}
        for profile in load_profiles():
            card = PackCard(profile)
            self.cards[profile.id] = card
            card.action.clicked.connect(
                lambda checked=False, pack_id=profile.id: self.install_requested.emit(
                    pack_id
                )
            )
            card.cancel.clicked.connect(self.cancel_requested.emit)
            packs.addWidget(card)
        packs.addStretch()
        layout.addLayout(packs, 1)
        layout.addWidget(self._account_panel())

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
        row = QHBoxLayout()
        text = QLabel("Модель скина")
        text.setProperty("muted", True)
        row.addWidget(text)
        row.addStretch()
        help_button = QPushButton("?")
        help_button.setObjectName("skinHelp")
        help_button.setFixedSize(28, 28)
        help_button.setToolTip("Чем отличаются форматы скинов и модели Steve / Alex?")
        help_button.setProperty("quiet", True)
        help_button.clicked.connect(self._skin_help)
        row.addWidget(help_button)
        panel.addLayout(row)
        self.skin_model = QComboBox()
        self.skin_model.addItem("Steve · обычные руки", "classic")
        self.skin_model.addItem("Alex · тонкие руки", "slim")
        panel.addWidget(self.skin_model)
        self.upload_button = BusyButton("Загрузить скин…")
        self.upload_button.setObjectName("uploadSkin")
        panel.addWidget(self.upload_button)
        self.change_password = BusyButton("Сменить пароль")
        self.change_password.setProperty("quiet", True)
        self.change_password.setObjectName("changePassword")
        panel.addWidget(self.change_password)
        return account

    def _skin_help(self) -> None:
        QMessageBox.information(
            self,
            "Как выбрать скин",
            "Формат PNG:\n64×64 — современный; 64×32 — старый.\n\n"
            "Модель персонажа:\nSteve — руки шириной 4 пикселя; Alex — 3 пикселя. "
            "Это отдельный параметр, он не определяется одной лишь версией Minecraft.\n\n"
            "Для Alex нужен скин 64×64. В сборках на Minecraft 1.7.10 современные детали "
            "скина требуют поддержки со стороны модов.\n\n"
            "Поддерживается обычный PNG до 256 КБ. Повреждённые изображения не загружаются.",
        )
