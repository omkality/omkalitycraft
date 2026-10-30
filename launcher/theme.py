"""Bundled Rubik Medium and native Qt animations; no WebEngine dependency."""

from pathlib import Path

from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication

ASSETS = Path(__file__).resolve().parent / "assets"


def install_font(app: QApplication) -> None:
    if not app.property("omkRubikLoaded"):
        font_id = QFontDatabase.addApplicationFont(str(ASSETS / "fonts" / "Rubik.ttf"))
        if font_id < 0:
            raise RuntimeError("Bundled Rubik font is missing or unreadable")
        app.setProperty("omkRubikLoaded", True)
    font = QFont("Rubik Medium", 10, QFont.Weight.Medium)
    app.setFont(font)


STYLE = """
QWidget { background: #11191f; color: #ecf2f5; font-family: 'Rubik Medium'; font-size: 13px; font-weight: 500; }
QLabel { background: transparent; }
QLineEdit, QComboBox { background: #1a272f; border: 1px solid #30434d; border-radius: 9px; padding: 11px; }
QLineEdit:focus, QComboBox:focus { border-color: #6dd6ac; }
QPushButton { background: #22333d; border: 1px solid #354b57; border-radius: 9px; padding: 11px 16px; }
QPushButton:hover { background: #2a414b; border-color: #618577; }
QPushButton:pressed { background: #17252d; padding-top: 13px; padding-bottom: 9px; }
QPushButton:disabled { color: #6f858d; background: #1a272e; border-color: #2a3a42; }
QPushButton[primary="true"] { background: #78dcaf; color: #0f3025; border: none; }
QPushButton[primary="true"]:hover { background: #9cebc7; }
QPushButton[primary="true"]:pressed { background: #50bf8c; }
QPushButton[primary="true"]:disabled { background: #254d40; color: #85a89a; }
QPushButton[quiet="true"] { border: none; background: transparent; color: #9cbbb9; padding: 5px; }
QLabel[title="true"] { font-size: 28px; }
QLabel[muted="true"] { color: #91a9b1; }
QLabel[error="true"] { color: #efb094; }
QFrame[panel="true"] { background: #172229; border: 1px solid #2a3a42; border-radius: 14px; }
QProgressBar { border: none; border-radius: 3px; background: #273b43; min-height: 5px; max-height: 5px; }
QProgressBar::chunk { background: #78dcaf; border-radius: 3px; }
QTabWidget::pane { border: none; }
QTabBar::tab { background: #1a2932; padding: 11px 22px; margin-right: 5px; border-radius: 7px; }
QTabBar::tab:selected { background: #304a53; }
QCheckBox { padding: 8px 0; }
QToolTip { color: #ecf2f5; background: #22333d; border: 1px solid #4b6a72; padding: 8px; }
"""
