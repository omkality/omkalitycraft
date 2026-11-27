"""One launcher dialog for a finished Minecraft run with crash evidence."""

from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from omk.shared.fs import resolved


class CrashDialog(QDialog):
    """Show the local diagnostic directory and any confirmed receipt for the run."""

    def __init__(
        self, directory: Path, parent: QWidget, *, report_received: bool = False
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("OmkalityCraft")
        self.setObjectName("gameCrashDialog")
        self.setWindowFlag(Qt.WindowType.WindowContextHelpButtonHint, False)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.resize(580, 160)

        self.directory = directory
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)
        heading = QLabel("Minecraft вылетел")
        heading.setStyleSheet("font-size: 24px")
        layout.addWidget(heading)
        if report_received:
            receipt = QLabel("Мы получили отчёт")
            receipt.setObjectName("crashReportReceipt")
            layout.addWidget(receipt)
        self.hint = QLabel("Папка с логами")
        self.hint.setProperty("muted", True)
        layout.addWidget(self.hint)

        path = QLineEdit(str(directory))
        path.setObjectName("crashDirectory")
        path.setReadOnly(True)
        path.setCursorPosition(0)
        layout.addWidget(path)

        open_folder = QPushButton("Открыть папку")
        open_folder.setObjectName("openCrashDirectory")
        open_folder.setProperty("primary", True)
        open_folder.clicked.connect(self._open_directory)
        close = QPushButton("Закрыть")
        close.clicked.connect(self.accept)
        controls = QHBoxLayout()
        controls.addStretch()
        controls.addWidget(close)
        controls.addWidget(open_folder)
        layout.addLayout(controls)
        open_folder.setDefault(True)
        open_folder.setFocus()

    def _open_directory(self) -> None:
        directory = self.directory
        if (
            not directory.is_dir()
            or resolved(directory) != directory.absolute()
            or not QDesktopServices.openUrl(QUrl.fromLocalFile(str(directory)))
        ):
            self.hint.setText("Не удалось открыть папку. Путь можно скопировать.")
