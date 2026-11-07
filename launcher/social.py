"""Compact links to the streamer's public channels."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from launcher.widgets import external_label

CHANNELS = (
    ("YouTube", "https://www.youtube.com/@omkality"),
    ("Twitch", "https://www.twitch.tv/omkality"),
    ("Kick", "https://kick.com/omkality"),
    ("Telegram", "https://t.me/vy_bolshovo_psa"),
)


class SocialFooter(QWidget):
    def __init__(self, update_notice: str = "") -> None:
        super().__init__()
        self.setObjectName("socialFooter")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 14 if update_notice else 6, 0, 0)
        layout.setSpacing(20)
        if update_notice:
            notice = QLabel(update_notice)
            notice.setObjectName("launcherUpdateNotice")
            notice.setTextFormat(Qt.TextFormat.PlainText)
            notice.setWordWrap(True)
            notice.setAlignment(Qt.AlignmentFlag.AlignCenter)
            notice.setProperty("warning", True)
            layout.addWidget(notice)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(24)
        row.addStretch()
        layout.addLayout(row)
        for name, url in CHANNELS:
            link = external_label(
                name, url, icon_name="social-" + name.lower() + ".svg"
            )
            link.setObjectName("social_" + name.lower())
            link.setAlignment(Qt.AlignmentFlag.AlignCenter)
            link.setProperty("socialLink", True)
            row.addWidget(link)
        row.addStretch()
