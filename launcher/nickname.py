"""Strict Java nicknames with brief, non-blocking feedback on rejected input."""

from typing import override

from PySide6.QtCore import QPoint, QRegularExpression, Qt, QTimer
from PySide6.QtGui import (
    QFocusEvent,
    QGuiApplication,
    QHideEvent,
    QPainter,
    QPaintEvent,
    QRegularExpressionValidator,
)
from PySide6.QtWidgets import QLabel, QLineEdit, QStyle, QStyleOption, QToolTip

from launcher.accounts import USERNAME_PATTERN
from launcher.theme import TOOLTIP_STYLE


class _NicknameNotice(QLabel):
    @override
    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        option = QStyleOption()
        option.initFrom(self)
        self.style().drawPrimitive(
            QStyle.PrimitiveElement.PE_Widget, option, painter, self
        )
        painter.end()
        super().paintEvent(event)


class NicknameField(QLineEdit):
    def __init__(self, name: str) -> None:
        super().__init__()
        self.setObjectName(name)
        self.setPlaceholderText("Omkality_01")
        self.setMaxLength(16)
        self.setProperty("minecraftNickname", True)
        self.setValidator(
            QRegularExpressionValidator(QRegularExpression(USERNAME_PATTERN), self)
        )
        self.setToolTip("3–16 символов: A–Z, a–z, 0–9 и _.")
        self.notice_text = ""
        # A validation notice is not hover help: macOS hides stock QToolTip on
        # every non-modifier KeyRelease, including the key that rejected input.
        self.notice = _NicknameNotice(
            self,
            Qt.WindowType.ToolTip
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowDoesNotAcceptFocus,
        )
        self.notice.setObjectName("nicknameNotice")
        self.notice.setStyleSheet("QLabel {" + TOOLTIP_STYLE + "}")
        self.notice.setWordWrap(True)
        self.notice.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.notice.hide()
        self.notice_timer = QTimer(self)
        self.notice_timer.setSingleShot(True)
        self.notice_timer.setInterval(2200)
        self.notice_timer.timeout.connect(self._hide_notice)
        self.inputRejected.connect(self._input_rejected)

    def _input_rejected(self) -> None:
        self.notice_text = (
            "В нике может быть не больше 16 символов."
            if len(self.text()) >= self.maxLength()
            else "Для ника подходят только латинские буквы, цифры и _."
        )
        point = self.mapToGlobal(QPoint(0, self.height() + 6))
        screen = QGuiApplication.screenAt(point) or self.screen()
        available = screen.availableGeometry().adjusted(8, 8, -8, -8)
        self.notice.setMaximumWidth(min(480, available.width()))
        self.notice.setText(self.notice_text)
        self.notice.adjustSize()
        self.notice.move(
            min(
                max(point.x(), available.left()),
                available.right() - self.notice.width() + 1,
            ),
            min(
                max(point.y(), available.top()),
                available.bottom() - self.notice.height() + 1,
            ),
        )
        QToolTip.hideText()
        self.notice.show()
        self.notice_timer.start()

    def _hide_notice(self) -> None:
        self.notice_timer.stop()
        self.notice.hide()

    @override
    def focusOutEvent(self, event: QFocusEvent) -> None:
        self._hide_notice()
        super().focusOutEvent(event)

    @override
    def hideEvent(self, event: QHideEvent) -> None:
        self._hide_notice()
        super().hideEvent(event)
