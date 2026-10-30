"""Compact links to the streamer's public channels."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QWidget

from launcher.widgets import external_label

CHANNELS = (
    ("YouTube", "https://www.youtube.com/@omkality"),
    ("Twitch", "https://www.twitch.tv/omkality"),
    ("Kick", "https://kick.com/omkality"),
)


class SocialFooter(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("socialFooter")
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 6, 0, 0)
        row.setSpacing(24)
        row.addStretch()
        for name, url in CHANNELS:
            link = external_label(name + " ↗", url)
            link.setObjectName("social_" + name.lower())
            link.setAlignment(Qt.AlignmentFlag.AlignCenter)
            link.setStyleSheet(
                "background:#17252b;border:1px solid #2a3a42;border-radius:12px;padding:7px 20px"
            )
            row.addWidget(link)
        row.addStretch()
