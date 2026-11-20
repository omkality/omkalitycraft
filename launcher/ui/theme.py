"""Bundled Rubik Bold, pixel nicknames and native Qt animations."""

from pathlib import Path
from string import Template
from typing import override

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication, QWidget

ASSETS = Path(__file__).resolve().parents[1] / "assets"

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
TOOLTIP_STYLE = (
    "font-family:'Rubik';font-size:15px;font-weight:700;"
    f"color:{TEXT};background:{RAISED};border:1px solid {WARNING};"
    "border-radius:9px;padding:8px 11px;"
)


class _TooltipSurface(QObject):
    @override
    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if (
            event.type() == QEvent.Type.Polish
            and isinstance(watched, QWidget)
            and watched.windowType() == Qt.WindowType.ToolTip
        ):
            # Rounded QSS paints only the panel; its native window also needs alpha.
            # Polish runs before the window is shown, as required by Qt.
            watched.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        return False


def install_font(app: QApplication) -> None:
    if not hasattr(app, "_omk_tooltip_surface"):
        app._omk_tooltip_surface = _TooltipSurface(app)
        app.installEventFilter(app._omk_tooltip_surface)
    if not app.property("omkBoldFontsLoaded"):
        for name in ("Rubik.ttf", "Monocraft-Bold.ttf"):
            if QFontDatabase.addApplicationFont(str(ASSETS / "fonts" / name)) < 0:
                raise RuntimeError("Bundled launcher font is missing or unreadable")
        app.setProperty("omkBoldFontsLoaded", True)
    font = QFont("Rubik", 11, QFont.Weight.Bold)
    app.setFont(font)


STYLE = Template((ASSETS / "theme.qss").read_text(encoding="utf-8")).substitute(
    background=BACKGROUND,
    surface=SURFACE,
    raised=RAISED,
    border=BORDER,
    text=TEXT,
    muted=MUTED,
    ice=ICE,
    warning=WARNING,
    error=ERROR,
    tooltip_style=TOOLTIP_STYLE,
    checkmark=(ASSETS / "checkmark.svg").as_posix().replace('"', r"\""),
)
