"""Illustrated, offline player reference for the DJ2 server."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)


def _text(text: str, *, muted: bool = False) -> QLabel:
    label = QLabel(text)
    label.setTextFormat(Qt.TextFormat.PlainText)
    label.setWordWrap(True)
    label.setProperty("muted", muted)
    return label


def _heading(text: str, size: int = 20) -> QLabel:
    label = _text(text)
    label.setStyleSheet(f"font-size:{size}px")
    return label


def _panel() -> tuple[QFrame, QVBoxLayout]:
    frame = QFrame()
    frame.setProperty("panel", True)
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(18, 15, 18, 15)
    layout.setSpacing(7)
    return frame, layout


def _flow(*steps: tuple[str, str]) -> QFrame:
    frame, layout = _panel()
    row = QHBoxLayout()
    row.setSpacing(10)
    for index, (title, description) in enumerate(steps):
        if index:
            arrow = _heading("→", 25)
            arrow.setAlignment(Qt.AlignmentFlag.AlignCenter)
            arrow.setStyleSheet("font-size:25px;color:#9fb9d0")
            row.addWidget(arrow)
        step = QVBoxLayout()
        step.setSpacing(4)
        step.addWidget(_heading(title, 16))
        step.addWidget(_text(description, muted=True))
        step.addStretch()
        row.addLayout(step, 1)
    layout.addLayout(row)
    return frame


def _named_rows(*rows: tuple[str, str]) -> QFrame:
    frame, layout = _panel()
    for title, detail in rows:
        heading = _heading(title, 16)
        heading.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(heading)
        layout.addWidget(_text(detail, muted=True))
        layout.addSpacing(4)
    return frame


def _chunk_example() -> QFrame:
    frame, body = _panel()
    body.addWidget(_heading("Как читать карту чанков", 17))
    demo = QHBoxLayout()
    demo.setSpacing(18)
    grid = QGridLayout()
    grid.setSpacing(3)
    for row, pattern in enumerate((".....", ".ccl.", ".cc..")):
        for column, kind in enumerate(pattern):
            color, border = {
                ".": ("#202a35", "#354454"),
                "c": ("#39695a", "#7aa692"),
                "l": ("#39695a", "#ed9480"),
            }[kind]
            square = QLabel()
            square.setFixedSize(23, 23)
            square.setStyleSheet(
                f"background:{color};border:2px solid {border};border-radius:3px"
            )
            grid.addWidget(square, row, column)
    demo.addLayout(grid)
    legend = QVBoxLayout()
    legend.addWidget(_text("← Закрашенная клетка — приват вашей команды."))
    legend.addWidget(_text("← Красная рамка — включена прогрузка.", muted=True))
    legend.addWidget(_text("Одна клетка занимает 16 × 16 блоков.", muted=True))
    demo.addLayout(legend, 1)
    body.addLayout(demo)
    return frame


def _world_table() -> QFrame:
    frame, body = _panel()
    grid = QGridLayout()
    grid.setHorizontalSpacing(15)
    grid.setVerticalSpacing(10)
    grid.setColumnStretch(0, 2)
    grid.setColumnStretch(1, 1)
    grid.setColumnStretch(2, 1)
    rows = (
        ("Мир", "Размер, блоки", "/rtp от центра"),
        ("Основной", "32 768 × 32 768", "до 5 000"),
        ("Ресурсный", "16 384 × 16 384", "до 4 094"),
        ("Ад", "8 192 × 8 192", "до 2 046"),
        ("Сумеречный лес", "8 192 × 8 192", "до 2 046"),
        ("Край", "16 384 × 16 384", "Недоступен"),
        ("Остальные измерения", "8 192 × 8 192", "Недоступен"),
    )
    for row, cells in enumerate(rows):
        for column, text in enumerate(cells):
            grid.addWidget(_text(text, muted=row == 0), row, column)
    body.addLayout(grid)
    return frame


class PlayerGuideDialog(QDialog):
    """Show the currently documented server controls and limits by topic."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("playerGuide")
        self.setWindowTitle("Памятка игрока · Divine Journey 2 RU")
        area = parent.window().screen().availableGeometry()
        self.resize(min(940, area.width() - 38), min(685, area.height() - 65))
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 18)
        layout.setSpacing(12)
        layout.addWidget(_heading("Памятка игрока", 25))
        layout.addWidget(_text("Divine Journey 2 RU", muted=True))
        self.tabs = QTabWidget()
        self.tabs.setObjectName("playerGuideSections")
        for name, content in (
            ("Первые шаги", self._start()),
            ("Приваты", self._claims()),
            ("Квесты и команды", self._quests()),
            ("Миры и /rtp", self._worlds()),
            ("Правила", self._rules()),
        ):
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QFrame.Shape.NoFrame)
            scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            scroll.setWidget(content)
            self.tabs.addTab(scroll, name)
        layout.addWidget(self.tabs, 1)

        footer = QHBoxLayout()
        footer.addStretch()
        close = QPushButton("Закрыть")
        close.setObjectName("closePlayerGuide")
        close.setProperty("primary", True)
        close.clicked.connect(self.accept)
        footer.addWidget(close)
        layout.addLayout(footer)

    @staticmethod
    def _page(*blocks: QWidget) -> QWidget:
        content = QWidget()
        column = QVBoxLayout(content)
        column.setContentsMargins(0, 2, 10, 8)
        column.setSpacing(12)
        for block in blocks:
            column.addWidget(block)
        column.addStretch()
        return content

    @classmethod
    def _start(cls) -> QWidget:
        return cls._page(
            _heading("От спавна до своей базы"),
            _flow(
                ("Сетевая игра", "Выберите Divine Journey 2 RU."),
                ("/rtp", "Откройте чат клавишей T и найдите место для базы."),
                ("E → Занятые чанки", "Займите место на карте FTB."),
            ),
            _named_rows(
                ("K — книга квестов", "Первые задания объясняют, с чего начать в DJ2."),
                (
                    "/sethome база",
                    "Запомните точку. Команда /home база вернёт вас туда.",
                ),
                ("/guide", "Короткая памятка доступна прямо в игре."),
                (
                    "/world",
                    "Показывает название текущего мира, даже если местность похожа.",
                ),
            ),
        )

    @classmethod
    def _claims(cls) -> QWidget:
        return cls._page(
            _heading("Защитите место, где строите"),
            _text(
                "Откройте инвентарь клавишей E. На боковой панели FTB нажмите "
                "«Занятые чанки». Карта показывает участок текущего мира."
            ),
            _chunk_example(),
            _named_rows(
                (
                    "ЛКМ — занять · Shift + ЛКМ — снять приват",
                    "Кликните по клетке или протяните выделение. Проверьте, "
                    "что на карте появился цвет вашей команды.",
                ),
                (
                    "ПКМ — загрузить · Shift + ПКМ — выключить загрузку",
                    "Включайте прогрузку после привата. Выделяйте чанки с механизмами, "
                    "которым нужно работать, когда вы отошли от базы.",
                ),
                (
                    "50 приватов и 10 прогрузок на участника",
                    "На всю команду доступно до 100 приватов и 20 прогрузок. "
                    "Например, у троих игроков общий лимит всё равно 100 и 20.",
                ),
                (
                    "До трёх отдельных территорий на участника",
                    "Клетки одной территории соприкасаются сторонами. "
                    "Если они касаются только углами, считаются разными участками.",
                ),
            ),
        )

    @classmethod
    def _quests(cls) -> QWidget:
        return cls._page(
            _heading("Квесты вместе с друзьями"),
            _flow(
                ("K", "Откройте книгу квестов."),
                ("Квест-команда", "Выберите «Создать команду»."),
                ("Пригласить", "Друг примет приглашение в книге квестов."),
            ),
            _text(
                "Квестовая команда отвечает за прогресс BetterQuesting. "
                "Откройте завершённый квест и заберите награду. "
                "Настройка «Одна награда на всех» делает награду общей."
            ),
            _named_rows(
                (
                    "Команда FTB для общего привата",
                    "Создайте команду через /team create имя. Пригласите друга командой "
                    "/team status Ник invited. Друг вступает через /team join имя.",
                ),
                (
                    "/dj2 book_of_logic",
                    "Показывает по-русски, какие условия нужно выполнить для Книги Логики.",
                ),
                (
                    "/bq_user refresh",
                    "Обновляет данные книги квестов, если её экран не показал свежий прогресс.",
                ),
            ),
        )

    @classmethod
    def _worlds(cls) -> QWidget:
        return cls._page(
            _heading("Куда переносит /rtp"),
            _flow(
                ("/world", "Узнайте, в каком мире вы сейчас."),
                ("/rtp", "Команда ищет свободную безопасную площадку."),
                ("Тот же мир", "Новые координаты в текущем измерении."),
            ),
            _world_table(),
            _text(
                "Три вызова доступны подряд. После третьего начинается пауза "
                "на пять минут. Принятый вызов считается попыткой, даже если "
                "перенос отменился. Поиск не заходит в чужие приваты."
            ),
            _text(
                "/resource ведёт на спавн ресурсного мира, /spawn — на спавн "
                "основного. Для встречи используйте /tpa Ник, друг вводит /tpaccept ВашНик.",
                muted=True,
            ),
        )

    @classmethod
    def _rules(cls) -> QWidget:
        return cls._page(
            _heading("Правила и ограничения"),
            _named_rows(
                (
                    "Спавн защищён в обоих мирах",
                    "Для стройки найдите свободное место через /rtp и займите чанки. "
                    "Защита спавна не мешает забрать вещи из своей могилы.",
                ),
                (
                    "Ресурсный мир для добычи",
                    "При обновлении ресурсного мира его постройки пропадают. "
                    "Инвентарь и квестовый прогресс остаются. Постоянную базу удобнее "
                    "строить в основном мире.",
                ),
                (
                    "Три точки дома на игрока",
                    "Посмотрите сохранённые точки через /home list. "
                    "Команда /delhome имя освобождает место для новой.",
                ),
                (
                    "Как открыть могилу",
                    "Подойдите к своей могиле и зажмите приседание, по умолчанию Shift.",
                ),
                (
                    "Приглашение для нового игрока",
                    "Один ключ используется один раз в лаунчере на вкладке «Первый вход». "
                    "После регистрации выбирайте «Уже есть аккаунт».",
                ),
            ),
        )
