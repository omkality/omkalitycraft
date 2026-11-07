"""Bundled Rubik Bold, pixel nicknames and native Qt animations."""

from pathlib import Path
from string import Template

from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication

ASSETS = Path(__file__).resolve().parent / "assets"

# Obsidian surfaces and ice-gray controls. Semantic colors stay distinct from the
# brand palette so an error or a disabled action cannot look like a primary CTA.
BACKGROUND = "#0b0d10"
SURFACE = "#12161b"
RAISED = "#1b2128"
BORDER = "#303842"
TEXT = "#edf2f7"
MUTED = "#9ba7b5"
ICE = "#dbe7f2"
SUCCESS = "#afcec5"
WARNING = "#e4bc84"
ERROR = "#edacaa"


def install_font(app: QApplication) -> None:
    if not app.property("omkBoldFontsLoaded"):
        for name in ("Rubik.ttf", "Monocraft-Bold.ttf"):
            if QFontDatabase.addApplicationFont(str(ASSETS / "fonts" / name)) < 0:
                raise RuntimeError("Bundled launcher font is missing or unreadable")
        app.setProperty("omkBoldFontsLoaded", True)
    font = QFont("Rubik", 11, QFont.Weight.Bold)
    app.setFont(font)


STYLE = Template("""
QWidget { background: $background; color: $text; font-family: 'Rubik'; font-size: 15px; font-weight: 700; }
QLabel, QCheckBox, QSlider, QTabWidget, QStackedWidget { background: transparent; }
QLineEdit, QComboBox { background: #0e1217; border: 1px solid $border; border-radius: 10px; padding: 12px;
min-height:22px; selection-background-color: #c4d4e3; selection-color: #10151b; }
QLineEdit:hover, QComboBox:hover { border-color: #586574; }
QLineEdit:focus, QComboBox:focus { border-color: $ice; }
QLineEdit::placeholder { color: #728090; }
QLineEdit[minecraftNickname="true"] { font-family:'Monocraft'; font-size:18px; font-weight:700; }
QPushButton { background: $raised; border: 1px solid $border; border-radius: 10px;
padding: 12px 18px; min-height:18px; }
QPushButton:hover { background: #28313b; border-color: #647485; }
QPushButton:focus { border-color: $ice; }
QPushButton:pressed { background: #10151b; padding-top: 14px; padding-bottom: 10px; }
QPushButton:disabled { color: #6c7784; background: #1b2027; border-color: #2c333c; }
QPushButton[primary="true"] { background: $ice; color: #141b23; border: 1px solid $ice; }
QPushButton[primary="true"]:hover { background: #f2f7fc; border-color: #f2f7fc; }
QPushButton[primary="true"]:pressed { background: #b8cadb; border-color: #b8cadb; }
QPushButton[primary="true"]:disabled { background: #252e38; color: #8a98a7; border-color: #303b47; }
QPushButton[quiet="true"] { border: 1px solid transparent; background: transparent; color: $muted; padding: 8px; }
QPushButton[quiet="true"]:hover { color: $text; background: $raised; }
QPushButton[quiet="true"]:focus { border-color: $ice; }
QLabel[title="true"] { font-size: 27px; letter-spacing: 2px; }
QLabel[muted="true"] { color: $muted; }
QLabel[error="true"] { color: $error; }
QLabel[warning="true"] { color: $warning; font-size: 14px; }
QSlider::groove:horizontal { background:#303a45; height:4px; border-radius:2px; }
QSlider::sub-page:horizontal { background:$ice; border-radius:2px; }
QSlider::handle:horizontal { background:$text; border:2px solid #8295a7;
width:12px; margin:-5px 0; border-radius:7px; }
QSlider::groove:horizontal:disabled { background:#252b33; }
QSlider::sub-page:horizontal:disabled { background:#39434f; }
QSlider::handle:horizontal:disabled { background:#596573; border-color:#39434f; }
QLabel:disabled { color:#737f8c; }
QFrame[panel="true"] { background: $surface; border: 1px solid #29323d; border-radius: 18px; }
QWidget#accountPanel { background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
stop:0 #1b232d,stop:0.6 #12171e,stop:1 #101419); }
QWidget#authPanel { background: $surface; border: 1px solid #29323d; border-radius: 18px; }
QWidget[authForm="true"], QTabBar { background: transparent; }
QLabel[socialLink="true"] { background:#13181f; border:1px solid #29323d; border-radius:10px; padding:8px 18px; }
QLabel[socialLink="true"]:hover { background: #222b35; border-color: #647485; }
QProgressBar { border: none; border-radius: 3px; background: #2b3540; min-height: 5px; max-height: 5px; }
QProgressBar::chunk { background: $ice; border-radius: 3px; }
QTabWidget::pane { border: none; }
QTabBar::tab { background: #191f27; color:$muted; padding: 12px 20px; margin-right: 6px; margin-bottom:16px;
border-radius: 9px; border:1px solid #29323d; }
QTabBar::tab:selected { background: #dbe7f2; color: #141b23; border-color:$ice; }
QTabBar::tab:hover:!selected { color:$text; background:#28313b; }
QCheckBox { padding: 8px 0; spacing:9px; }
QCheckBox::indicator { width:16px; height:16px; border:1px solid #8295a7; border-radius:4px; background:#0e1217; }
QCheckBox::indicator:checked { background:$ice; image:url("$checkmark"); }
QCheckBox::indicator:focus { border-color:$ice; }
QToolTip { color: $text; background: $raised; border: 1px solid $warning; border-radius: 9px; padding: 8px 11px; }
QScrollArea, QScrollArea > QWidget > QWidget { background: transparent; }
QScrollBar:vertical { background:$background; width:8px; margin:0; }
QScrollBar::handle:vertical { background:#3c4856; border-radius:4px; min-height:32px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height:0; }
""").substitute(
    background=BACKGROUND,
    surface=SURFACE,
    raised=RAISED,
    border=BORDER,
    text=TEXT,
    muted=MUTED,
    ice=ICE,
    warning=WARNING,
    error=ERROR,
    checkmark=(ASSETS / "checkmark.svg").as_posix().replace('"', r"\""),
)
