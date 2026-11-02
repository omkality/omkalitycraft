"""Shared launcher mark, independent of any game profile."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import QApplication, QHBoxLayout, QLabel, QVBoxLayout

from launcher.theme import ASSETS

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
    heading = QVBoxLayout()
    heading.setSpacing(4)
    title, subtitle = QLabel("OMKALITYCRAFT"), QLabel(
        "Играть вместе. Без лишних шагов."
    )
    for item in (title, subtitle):
        item.setTextFormat(Qt.TextFormat.PlainText)
        item.setWordWrap(True)
    title.setProperty("title", True)
    subtitle.setProperty("muted", True)
    heading.addWidget(title)
    heading.addWidget(subtitle)
    header.addLayout(heading, 1)
    return header
