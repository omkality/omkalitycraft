"""Offline guide with common rules and per-pack instruction pages."""

from collections.abc import Callable, Iterable
from pathlib import Path

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap, QPolygonF
from PySide6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from launcher.pack.keybindings import saved_legacy_key_labels
from launcher.pack.player_guides import COMMON_COMMANDS, PACK_GUIDES, RULES, PackGuide
from launcher.releases import ReleaseError
from launcher.ui.theme import ASSETS
from omk.shared.profiles import ServerProfile


def _text(text: str, *, muted: bool = False, size: int = 0) -> QLabel:
    label = QLabel(text)
    label.setTextFormat(Qt.TextFormat.PlainText)
    label.setWordWrap(True)
    label.setProperty("muted", muted)
    if size:
        label.setStyleSheet(f"font-size:{size}px")
    return label


def _panel() -> tuple[QFrame, QVBoxLayout]:
    frame = QFrame()
    frame.setProperty("panel", True)
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(16, 14, 16, 14)
    layout.setSpacing(8)
    return frame, layout


def _flow(steps: tuple[tuple[str, QLabel], ...]) -> QWidget:
    flow = QWidget()
    row = QHBoxLayout(flow)
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(0)
    for index, (title, description) in enumerate(steps):
        if index:
            arrow = _text("→")
            arrow.setObjectName("questFlowArrow")
            arrow.setStyleSheet("font-size:24px;color:#a8c6dd")
            arrow.setFixedWidth(36)
            arrow.setAlignment(Qt.AlignmentFlag.AlignCenter)
            row.addWidget(arrow)
        step, body = _panel()
        step.setObjectName("questFlowStep")
        body.setContentsMargins(12, 12, 12, 12)
        heading = _text(title, size=16)
        heading.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        description.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        body.addStretch()
        body.addWidget(heading)
        body.addWidget(description)
        body.addStretch()
        row.addWidget(step, 1)
    return flow


def _rows(title: str, rows: tuple[tuple[str, str], ...]) -> QFrame:
    frame, layout = _panel()
    if title:
        layout.addWidget(_text(title, size=18))
    for name, detail in rows:
        heading = _text(name, size=15)
        if name.startswith("/"):
            heading.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse
            )
        layout.addWidget(heading)
        layout.addWidget(_text(detail, muted=True))
        layout.addSpacing(4)
    return frame


def _world_table(worlds: tuple[tuple[str, str], ...]) -> QFrame:
    frame, body = _panel()
    grid = QGridLayout()
    grid.setHorizontalSpacing(14)
    grid.setVerticalSpacing(9)
    grid.setColumnStretch(0, 2)
    grid.setColumnStretch(1, 1)
    for row, cells in enumerate((("Мир", "Размер в блоках"), *worlds)):
        for column, text in enumerate(cells):
            grid.addWidget(_text(text, muted=row == 0), row, column)
    body.addLayout(grid)
    return frame


def _claim_picture(
    asset: str,
    name: str,
    description: str,
    width: int,
    arrow_tip: tuple[int, int] | None = None,
) -> QLabel | None:
    screenshot = QPixmap(str(ASSETS / "guides" / asset))
    if screenshot.isNull():
        return None
    if arrow_tip is not None:
        tip = QPointF(*arrow_tip)
        arrow = QPolygonF([tip + QPointF(20, -4), tip, tip + QPointF(13, 16)])
        painter = QPainter(screenshot)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        for color, stroke in (("#161b21", 8), ("#ffe18a", 4)):
            pen = QPen(QColor(color), stroke)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            painter.drawLine(tip + QPointF(91, 27), tip)
            painter.drawPolyline(arrow)
        painter.end()
    illustration = QLabel()
    illustration.setObjectName(name)
    illustration.setAccessibleName(description)
    illustration.setPixmap(screenshot.scaledToWidth(min(width, screenshot.width())))
    illustration.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
    return illustration


def _page(*blocks: QWidget) -> QScrollArea:
    content = QWidget()
    column = QVBoxLayout(content)
    column.setContentsMargins(0, 0, 12, 8)
    column.setSpacing(12)
    for block in blocks:
        column.addWidget(block)
    column.addStretch()
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.Shape.NoFrame)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    scroll.setWidget(content)
    return scroll


class PlayerGuideDialog(QDialog):
    """Show shared policies alongside the guides available for the installed packs."""

    def __init__(
        self,
        parent: QWidget,
        profiles: Iterable[ServerProfile],
        instance_directory: Callable[[str], Path] | None = None,
    ) -> None:
        super().__init__(parent, Qt.WindowType.Popup)
        self.setObjectName("playerGuide")
        self.setWindowTitle("Памятка игрока")
        area = parent.window().screen().availableGeometry()
        self.resize(min(1120, area.width() - 38), min(735, area.height() - 72))
        self._instance_directory = instance_directory
        self._key_hints: dict[str, list[tuple[str, QLabel, str, str]]] = {}
        self._profiles = tuple(
            (profile, PACK_GUIDES[profile.id])
            for profile in profiles
            if profile.id in PACK_GUIDES
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 18)
        layout.setSpacing(14)
        layout.addWidget(_text("Памятка игрока", size=27))

        columns = QHBoxLayout()
        columns.setSpacing(22)
        sidebar = QWidget()
        sidebar.setFixedWidth(206)
        self._navigation = QVBoxLayout(sidebar)
        self._navigation.setContentsMargins(0, 0, 0, 0)
        self._navigation.setSpacing(6)
        self._buttons = QButtonGroup(self)
        self._buttons.idClicked.connect(self._select_topic)
        self.pages = QStackedWidget()
        self.pages.setObjectName("playerGuideSections")
        columns.addWidget(sidebar)
        columns.addWidget(self.pages, 1)
        layout.addLayout(columns, 1)

        self._scope("Общее")
        self._add_topic(
            "guideRules",
            "Правила",
            _page(_text("Правила сервера", size=22), _rows("", RULES)),
        )
        self._add_topic("guideCommands", "Квесты и команды", self._commands())
        for profile, guide in self._profiles:
            self._navigation.addSpacing(13)
            self._scope(profile.name)
            if guide.claims:
                self._add_topic(
                    f"guideClaims_{profile.id}", "Приваты", self._claims(profile, guide)
                )
            if guide.worlds:
                self._add_topic(
                    f"guideWorlds_{profile.id}",
                    "Миры",
                    self._worlds(guide),
                )
        self._navigation.addStretch()
        self._buttons.button(0).setChecked(True)
        self._select_topic(0)

        footer = QHBoxLayout()
        footer.addStretch()
        close = QPushButton("Закрыть")
        close.setObjectName("closePlayerGuide")
        close.setProperty("primary", True)
        close.clicked.connect(self.accept)
        footer.addWidget(close)
        layout.addLayout(footer)

    def _scope(self, name: str) -> None:
        label = _text(name, muted=True, size=14)
        label.setStyleSheet("font-size:14px;margin:4px 9px")
        self._navigation.addWidget(label)

    def _add_topic(self, name: str, label: str, page: QWidget) -> None:
        button = QPushButton(label)
        button.setObjectName(name)
        button.setCheckable(True)
        button.setProperty("guideTopic", True)
        page.setObjectName(name + "Page")
        self._buttons.addButton(button, self.pages.addWidget(page))
        self._navigation.addWidget(button)

    def _select_topic(self, index: int) -> None:
        self.pages.setCurrentIndex(index)

    def _key_hint(
        self, pack_id: str, binding: str, name: str, message: str, fallback: str
    ) -> QLabel:
        label = _text(fallback, muted=True)
        label.setObjectName(name)
        self._key_hints.setdefault(pack_id, []).append(
            (binding, label, message, fallback)
        )
        return label

    def refresh_keys(self) -> None:
        """Refresh the control captions when the guide is opened."""
        for pack_id, hints in self._key_hints.items():
            labels = {}
            if self._instance_directory is not None:
                try:
                    folder = self._instance_directory(pack_id)
                    labels = saved_legacy_key_labels(
                        folder, *(binding for binding, *_ in hints)
                    )
                except OSError, ValueError, ReleaseError:
                    pass
            for binding, label, message, fallback in hints:
                saved = labels.get(binding)
                label.setText(message.format(key=saved) if saved else fallback)

    def _commands(self) -> QTabWidget:
        scopes = QTabWidget()
        scopes.addTab(
            _page(*(_rows(title, commands) for title, commands in COMMON_COMMANDS)),
            "Общие команды",
        )
        for profile, guide in self._profiles:
            blocks = []
            if guide.quest_key:
                blocks.extend(self._quests(profile.id, guide.quest_key))
            blocks.extend(_rows(title, commands) for title, commands in guide.commands)
            scopes.addTab(_page(*blocks), profile.name)
        return scopes

    def _quests(self, pack_id: str, binding: str) -> tuple[QWidget, ...]:
        hint = self._key_hint(
            pack_id,
            binding,
            "questBookControl",
            "Откройте книгу.\nКлавиша {key}",
            "В «Настройки → Управление» найдите действие «Открыть квесты».",
        )
        return (
            _text("Квесты вместе с друзьями", size=18),
            _flow(
                (
                    ("Книга квестов", hint),
                    ("Квест-команда", _text("Нажмите «Создать команду».", muted=True)),
                    (
                        "Пригласить",
                        _text("Друг примет приглашение в книге.", muted=True),
                    ),
                )
            ),
            _text(
                "Квестовая команда объединяет прогресс BetterQuesting. "
                "Команда FTB управляет приватами отдельно. Настройка "
                "«Одна награда на всех» делает квестовую награду общей.",
                muted=True,
            ),
        )

    def _worlds(self, guide: PackGuide) -> QScrollArea:
        blocks: list[QWidget] = [
            _text("Размеры миров", size=22),
            _world_table(guide.worlds),
            _text(
                "Размер показывает расстояние от края до края по каждой оси.",
                muted=True,
            ),
        ]
        if guide.world_notes:
            blocks.append(_rows("", guide.world_notes))
        return _page(*blocks)

    def _claims(self, profile: ServerProfile, guide: PackGuide) -> QScrollArea:
        blocks: list[QWidget] = [_text("Приваты и прогрузка чанков", size=22)]
        button = _claim_picture(
            f"{profile.id}-inventory.png",
            "claimsButtonScreenshot",
            "Стрелка указывает на кнопку «Занятые чанки»",
            530,
            guide.claims_button,
        )
        if guide.inventory_key:
            blocks.append(
                self._key_hint(
                    profile.id,
                    guide.inventory_key,
                    "inventoryControl",
                    "Откройте инвентарь клавишей {key}.",
                    "Откройте инвентарь. Его клавиша указана в «Настройки → Управление».",
                )
            )
        if guide.claims_intro:
            blocks.append(_text(guide.claims_intro))
        if button is not None:
            blocks.append(button)
        example = _claim_picture(
            f"{profile.id}-claims.png",
            "claimsMapScreenshot",
            "Территория команды и прогруженные чанки внутри неё",
            350,
        )
        if example is not None:
            blocks.append(_text("Пример привата на карте", size=17))
            map_panel = QWidget()
            row = QHBoxLayout(map_panel)
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(18)
            row.addWidget(example, alignment=Qt.AlignmentFlag.AlignTop)
            row.addWidget(
                _rows(
                    "Как читать карту",
                    (
                        ("Заливка цветом команды", "Вся занятая территория."),
                        (
                            "Красная рамка",
                            "Чанки внутри привата, где включена прогрузка.",
                        ),
                    ),
                ),
                1,
                Qt.AlignmentFlag.AlignTop,
            )
            blocks.append(map_panel)
        blocks.append(_rows("Действия на карте", guide.claims))
        return _page(*blocks)
