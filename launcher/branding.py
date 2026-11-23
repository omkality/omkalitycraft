"""Shared launcher mark, independent of any game profile."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import QApplication, QHBoxLayout, QLabel

from launcher.ui.theme import ASSETS

ICON = ASSETS / "branding/icon.png"


def install_branding(app: QApplication) -> None:
    app.setWindowIcon(QIcon(str(ICON)))


def logo_label() -> QLabel:
    logo = QLabel()
    logo.setObjectName("launcherLogo")
    logo.setAccessibleName("Логотип OmkalityCraft")
    logo.setFixedSize(56, 56)
    logo.setPixmap(
        QPixmap(str(ICON)).scaled(
            56,
            56,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
    )
    return logo


def title_header() -> QHBoxLayout:
    header = QHBoxLayout()
    header.setSpacing(16)
    header.addWidget(logo_label())
    title = QLabel("OMKALITYCRAFT")
    title.setTextFormat(Qt.TextFormat.PlainText)
    title.setWordWrap(True)
    title.setProperty("title", True)
    header.addWidget(title, 1)
    return header
