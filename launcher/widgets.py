"""Small native Qt controls for real states and restrained animation."""

import html
from typing import override
from urllib.parse import urlsplit

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QColor, QDesktopServices, QPainter, QPen, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
)

from launcher.install import Progress
from launcher.memory import MemorySnapshot
from launcher.memory_widget import MemoryControl
from launcher.theme import ASSETS
from omk.profiles import ServerProfile


def open_link(url: str) -> None:
    parsed = urlsplit(url)
    if (
        parsed.scheme == "https"
        and parsed.hostname
        and not parsed.username
        and not parsed.password
    ):
        QDesktopServices.openUrl(QUrl(url))


def external_label(text: str, url: str, *, icon_name: str | None = None) -> QLabel:
    icon = QUrl.fromLocalFile(str(ASSETS / "external-link.svg")).toString()
    prefix = ""
    if icon_name is not None:
        channel = QUrl.fromLocalFile(str(ASSETS / icon_name)).toString()
        prefix = f'<img src="{html.escape(channel, quote=True)}" width="16" height="16">&nbsp;&nbsp;'
    widget = QLabel(
        f'<a href="{html.escape(url, quote=True)}" style="color:#a9d6c8;text-decoration:none">'
        f'{prefix}{html.escape(text)}&nbsp;<img src="{html.escape(icon, quote=True)}" width="11" height="11"></a>'
    )
    widget.setTextInteractionFlags(
        Qt.TextInteractionFlag.LinksAccessibleByMouse
        | Qt.TextInteractionFlag.LinksAccessibleByKeyboard
    )
    widget.linkActivated.connect(open_link)
    widget.setWordWrap(False)
    return widget


class BusyButton(QPushButton):
    def __init__(self, text: str, parent=None) -> None:
        super().__init__(text, parent)
        self._busy = False
        self._angle = 0
        self._normal_text = text
        self.timer = QTimer(self)
        self.timer.setInterval(35)
        self.timer.timeout.connect(self._tick)

    def _tick(self) -> None:
        self._angle = (self._angle + 18) % 360
        self.update()

    def set_busy(self, busy: bool, message: str = "") -> None:
        if busy and not self._busy:
            self._normal_text = self.text()
        self._busy = busy
        self.setEnabled(not busy)
        self.setText(message or self._normal_text)
        self.timer.start() if busy else self.timer.stop()
        self.update()

    @override
    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        if self._busy:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setPen(QPen(QColor("#a5efd1"), 2.2))
            painter.drawArc(
                17, self.height() // 2 - 6, 12, 12, self._angle * 16, 250 * 16
            )


def artwork(name: str, width: int, height: int) -> QPixmap:
    pixmap = QPixmap(width, height)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    QSvgRenderer(str(ASSETS / name)).render(painter)
    painter.end()
    return pixmap


class PackCard(QFrame):
    def __init__(
        self,
        profile: ServerProfile,
        machine: MemorySnapshot | None = None,
        requested_mb: int | None = None,
    ) -> None:
        super().__init__()
        self.profile = profile
        self.setProperty("panel", True)
        self.setObjectName("pack_" + profile.id)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(19, 17, 19, 17)
        layout.setSpacing(9)
        layout.addLayout(self._header(profile))
        description = QLabel(profile.description)
        description.setWordWrap(True)
        description.setProperty("muted", True)
        layout.addWidget(description)
        credits = QHBoxLayout()
        credits.addWidget(external_label("Авторы сборки", profile.project_url))
        translation = external_label(profile.translation_label, profile.translation_url)
        translation.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        credits.addWidget(translation, 1)
        layout.addLayout(credits)
        self.memory = MemoryControl(
            profile, machine or MemorySnapshot.read(), requested_mb
        )
        layout.addWidget(self.memory)
        self.state_label = QLabel(
            "Планируется" if profile.status == "planned" else "Не установлена"
        )
        self.state_label.setObjectName("state_" + profile.id)
        self.state_label.setStyleSheet("color:#9bb1b6;background:transparent")
        state_row = QHBoxLayout()
        state_row.addWidget(self.state_label)
        self.online_label = QLabel("Сервер готовится")
        self.online_label.setObjectName("online_" + profile.id)
        self.online_label.setProperty("muted", True)
        self.online_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self.online_label.setVisible(profile.status != "planned")
        state_row.addWidget(self.online_label, 1)
        layout.addLayout(state_row)
        self.progress = QProgressBar()
        self.progress.setObjectName("progress_" + profile.id)
        self.progress.setTextVisible(False)
        self.progress.hide()
        layout.addWidget(self.progress)
        row = QHBoxLayout()
        self.action = BusyButton(
            "Скоро" if profile.status == "planned" else "Скачать сборку"
        )
        self.action.setObjectName("install_" + profile.id)
        self.action.setProperty("primary", True)
        self.action.setEnabled(profile.status != "planned")
        row.addWidget(self.action, 1)
        self.cancel = QPushButton("Приостановить")
        self.cancel.setObjectName("cancel_" + profile.id)
        self.cancel.hide()
        row.addWidget(self.cancel)
        layout.addLayout(row)
        self.installed = False

    def set_server_status(self, value):
        if value is None:
            text = "Онлайн недоступен"
        elif not isinstance(value, dict):
            text = "Сервер готовится"
        elif value.get("state") == "offline":
            text = "Сервер недоступен"
        elif value.get("state") == "checking":
            text = "Проверяем онлайн…"
        elif (
            value.get("state") == "online"
            and all(
                type(value.get(key)) is int and 0 <= value[key] <= 100000
                for key in ("online", "max")
            )
            and value["max"] > 0
        ):
            text = f"Онлайн: {value['online']} / {value['max']}"
        else:
            text = "Онлайн недоступен"
        self.online_label.setText(text)

    def _header(self, profile: ServerProfile) -> QHBoxLayout:
        header = QHBoxLayout()
        cover = QLabel()
        cover.setPixmap(artwork(profile.artwork, 124, 76))
        cover.setFixedSize(124, 76)
        header.addWidget(cover)
        heading = QVBoxLayout()
        name = QLabel(profile.name)
        name.setStyleSheet("font-size:19px;background:transparent")
        heading.addWidget(name)
        version = (
            profile.pack_version
            if profile.pack_version != "unselected"
            else "Сборка ещё не подготовлена"
        )
        self.version_link = external_label(version, profile.version_url)
        heading.addWidget(self.version_link)
        detail = QLabel(
            f"Minecraft {profile.minecraft}  ·  Forge"
            + (" " + profile.forge_version if profile.forge_version else "")
        )
        detail.setProperty("muted", True)
        heading.addWidget(detail)
        header.addLayout(heading, 1)
        return header

    def set_local_state(self, state: dict) -> None:
        self.installed = state.get("state") == "installed"
        if self.installed:
            self.state_label.setText("Установлена · " + state["version"])
            self.state_label.setStyleSheet("color:#92d5b8;background:transparent")
            self.action.setText("Играть")
        elif state.get("state") == "incomplete":
            self.state_label.setText("Загрузка не завершена")
            self.action.setText("Продолжить загрузку")

    def update_progress(self, progress: Progress) -> None:
        self.progress.show()
        self.cancel.show()
        self.action.set_busy(
            True, "Проверяем…" if progress.stage.startswith("Провер") else "Скачиваем…"
        )
        self.progress.setRange(0, 100)
        self.progress.setValue(progress.percent)
        if progress.stage.startswith("Скач"):
            self.state_label.setText(
                f"Скачивание · {progress.percent}% · {progress.done / 1024**2:.0f} / {progress.total / 1024**2:.0f} МБ"
            )
        else:
            self.state_label.setText(progress.stage)

    def finished(self, *, success: bool, message: str = "") -> None:
        self.action.set_busy(False)
        self.progress.hide()
        self.cancel.hide()
        if success:
            self.installed = True
            self.action.setText("Играть")
            self.state_label.setText("Установлена · готова к игре")
            self.state_label.setStyleSheet("color:#92d5b8;background:transparent")
        else:
            self.action.setText("Продолжить загрузку")
            self.state_label.setText(message or "Загрузка не завершена")
