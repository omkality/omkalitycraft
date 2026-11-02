"""Strict Java nicknames with brief, non-blocking feedback on rejected input."""

from typing import override

from PySide6.QtCore import QPoint, QRect, QRegularExpression, QTimer
from PySide6.QtGui import QFocusEvent, QRegularExpressionValidator
from PySide6.QtWidgets import QLineEdit, QToolTip

from launcher.accounts import USERNAME_PATTERN


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
        QToolTip.showText(
            self.mapToGlobal(QPoint(0, self.height() + 6)),
            self.notice_text,
            self,
            QRect(),
            2200,
        )
        self.notice_timer.start()

    def _hide_notice(self) -> None:
        self.notice_timer.stop()
        if QToolTip.text() == self.notice_text:
            QToolTip.hideText()

    @override
    def focusOutEvent(self, event: QFocusEvent) -> None:
        self._hide_notice()
        super().focusOutEvent(event)
