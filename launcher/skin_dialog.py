"""One skin upload with a visual preview, without Minecraft-version choices."""

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from launcher.skin_view import SkinView
from launcher.skins import Skin


class SkinDialog(QDialog):
    def __init__(self, skin: Skin, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("skinUploadDialog")
        self.setWindowTitle("Ваш скин")
        self.setMinimumWidth(340)
        self.skin = skin
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        heading = QLabel("Проверьте, как выглядит персонаж")
        heading.setWordWrap(True)
        layout.addWidget(heading)
        self.preview = SkinView()
        self.preview.set_skin(skin.png, skin.model)
        self.preview.setMinimumHeight(290)
        layout.addWidget(self.preview)
        self.adjust = QPushButton("Настроить модель")
        self.adjust.setObjectName("adjustSkinModel")
        self.adjust.setProperty("quiet", True)
        self.adjust.setVisible(not skin.legacy)
        layout.addWidget(self.adjust)
        self.model_choice = QComboBox()
        self.model_choice.setObjectName("skinModelChoice")
        self.model_choice.addItem("Стандартная", "classic")
        self.model_choice.addItem("Узкая", "slim")
        self.model_choice.setCurrentIndex(1 if skin.model == "slim" else 0)
        self.model_choice.setEnabled(not skin.legacy)
        self.model_choice.hide()
        self.adjust.clicked.connect(self._adjust_model)
        self.model_choice.currentIndexChanged.connect(self._update_preview)
        layout.addWidget(self.model_choice)
        actions = QDialogButtonBox()
        self.upload = actions.addButton(
            "Загрузить", QDialogButtonBox.ButtonRole.AcceptRole
        )
        self.upload.setObjectName("confirmSkinUpload")
        self.upload.setProperty("primary", True)
        cancel = actions.addButton("Отмена", QDialogButtonBox.ButtonRole.RejectRole)
        cancel.setObjectName("cancelSkinUpload")
        actions.accepted.connect(self.accept)
        actions.rejected.connect(self.reject)
        layout.addWidget(actions)

    @property
    def model(self) -> str:
        return str(self.model_choice.currentData())

    def _adjust_model(self) -> None:
        self.model_choice.setVisible(not self.model_choice.isVisible())

    def _update_preview(self) -> None:
        self.preview.set_skin(self.skin.png, self.model)
