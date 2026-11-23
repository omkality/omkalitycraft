"""Per-profile client requirements; estimates never become installation gates."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from launcher.memory import LOW_MEMORY_HOST_MB
from omk.shared.profiles import HardwareTier, ServerProfile


def _text(text: str, name: str = "", *, muted: bool = False) -> QLabel:
    label = QLabel(text)
    label.setObjectName(name)
    label.setTextFormat(Qt.TextFormat.PlainText)
    label.setWordWrap(True)
    label.setProperty("muted", muted)
    return label


class RequirementsDialog(QDialog):
    """Display the pack's published system requirements and memory guidance."""

    def __init__(self, profile: ServerProfile, parent: QWidget) -> None:
        super().__init__(parent, Qt.WindowType.Popup)
        self.setObjectName("requirements_" + profile.id)
        self.setWindowTitle("Системные требования · " + profile.name)
        screen = self.screen().availableGeometry()
        self.setFixedWidth(min(650, screen.width() - 30))
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(12)
        title = _text("Системные требования")
        title.setStyleSheet("font-size:24px")
        layout.addWidget(title)
        layout.addWidget(_text(profile.name, muted=True))

        layout.addWidget(self._content(profile))
        close = QPushButton("Понятно")
        close.setObjectName("closeRequirements")
        close.setProperty("primary", True)
        close.clicked.connect(self.accept)
        close.setDefault(True)
        controls = QHBoxLayout()
        controls.addStretch()
        controls.addWidget(close)
        layout.addLayout(controls)

    @classmethod
    def _content(cls, profile: ServerProfile) -> QWidget:
        content = QWidget()
        body = QVBoxLayout(content)
        body.setContentsMargins(0, 0, 8, 0)
        body.setSpacing(16)
        requirements = profile.requirements
        if requirements is None:
            body.addWidget(_text("Требования для этой сборки пока не подготовлены."))
        else:
            if requirements.state == "pending":
                body.addWidget(_text("СБОРКА ГОТОВИТСЯ", "requirementsState"))
            columns = QHBoxLayout()
            columns.setSpacing(14)
            columns.addWidget(
                cls._tier(
                    "Минимальные",
                    "minimum",
                    requirements.minimum,
                    requirements.minimum_note,
                ),
                1,
            )
            columns.addWidget(
                cls._tier(
                    "Рекомендуемые",
                    "recommended",
                    requirements.recommended,
                    "",
                ),
                1,
            )
            body.addLayout(columns)
            if requirements.recommended is not None:
                memory = (
                    f"Для Java по умолчанию — {profile.memory_default_mb / 1024:g} ГБ."
                )
                if profile.memory_recommended_mb < profile.memory_default_mb:
                    memory += (
                        f" При {LOW_MEMORY_HOST_MB / 1024:g} ГБ ОЗУ или меньше — "
                        f"{profile.memory_recommended_mb / 1024:g} ГБ, если позволяет объём памяти."
                    )
                body.addWidget(_text(memory, "requirementsJavaMemory"))
            body.addWidget(_text(requirements.platforms, "requirementsOS", muted=True))
            body.addWidget(_text(requirements.scope, "requirementsScope", muted=True))
        body.addStretch()
        return content

    @staticmethod
    def _tier(title: str, name: str, tier: HardwareTier | None, note: str) -> QFrame:
        panel = QFrame()
        panel.setProperty("panel", True)
        panel.setObjectName(name + "Requirements")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(8)
        heading = _text(title)
        heading.setStyleSheet("font-size:18px")
        layout.addWidget(heading)
        if tier is None and note:
            layout.addWidget(_text(note, name + "Pending", muted=True))
        if tier is not None:
            for key, caption, value in (
                ("ram", "Оперативная память ПК", f"{tier.ram_gb} ГБ"),
                ("cpu", "Процессор", tier.cpu),
                ("graphics", "Графика", tier.graphics),
                ("storage", "Свободное место", f"{tier.storage_gb} ГБ"),
            ):
                label = _text(caption, muted=True)
                label.setStyleSheet("font-size:13px;margin-top:4px")
                layout.addWidget(label)
                layout.addWidget(_text(value, name + "_" + key))
        layout.addStretch()
        return panel
