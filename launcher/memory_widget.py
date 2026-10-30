"""Native per-card heap slider; all limits come from profile data."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QSlider, QVBoxLayout, QWidget

from launcher.memory import MIN_MB, STEP_MB, MemorySnapshot, choose_memory
from omk.profiles import ServerProfile


class MemoryControl(QWidget):
    changed = Signal(int)

    def __init__(
        self, profile: ServerProfile, machine: MemorySnapshot, requested: int | None
    ) -> None:
        super().__init__()
        self.profile, self.machine = profile, machine
        choice = choose_memory(profile, machine, requested)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 2)
        layout.setSpacing(4)
        row = QHBoxLayout()
        row.addWidget(QLabel("Память для игры"))
        row.addStretch()
        self.value = QLabel()
        row.addWidget(self.value)
        layout.addLayout(row)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setObjectName("memory_" + profile.id)
        self.slider.setRange(
            MIN_MB // STEP_MB, max(MIN_MB, choice.maximum_mb) // STEP_MB
        )
        self.slider.setValue(max(MIN_MB, choice.selected_mb) // STEP_MB)
        self.slider.setEnabled(choice.maximum_mb >= MIN_MB)
        self.slider.setAccessibleName("Память для " + profile.name)
        self.slider.setToolTip(
            f"Рекомендуется {profile.memory_recommended_mb / 1024:g} ГБ. Часть памяти оставляем системе и Java."
        )
        layout.addWidget(self.slider)
        self.warning = QLabel()
        self.warning.setWordWrap(True)
        self.warning.setProperty("warning", True)
        layout.addWidget(self.warning)
        self.slider.valueChanged.connect(self._changed)
        self._update()

    @property
    def selected_mb(self) -> int:
        return choose_memory(
            self.profile, self.machine, self.slider.value() * STEP_MB
        ).selected_mb

    def _update(self) -> None:
        choice = choose_memory(
            self.profile, self.machine, self.slider.value() * STEP_MB
        )
        self.value.setText(f"{choice.selected_mb / 1024:g} ГБ")
        self.warning.setText(choice.warning)
        self.warning.setVisible(bool(choice.warning))

    def _changed(self) -> None:
        self._update()
        self.changed.emit(self.selected_mb)
