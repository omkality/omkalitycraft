"""Portable desktop account prototype; game installation is a later milestone."""

import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any, override

from PySide6.QtCore import QLockFile, Qt, QThreadPool, QTimer
from PySide6.QtGui import QCloseEvent, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QStackedWidget,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from launcher.accounts import (
    AccountError,
    AccountService,
    AuthResult,
    PasswordChanged,
    Registration,
    validate_skin,
)
from launcher.session import SessionStoreError
from launcher.storage import FileSessionStore
from launcher.tasks import Task
from omk.drasl import DraslClient, DraslError
from omk.profiles import load_profiles

STYLE = """
QWidget { background: #141b22; color: #e5edf3; font-size: 14px; }
QLineEdit, QListWidget, QComboBox { background: #202b36; border: 1px solid #3d4c5b; border-radius: 7px; padding: 9px; }
QPushButton { background: #263646; border: 1px solid #43576a; border-radius: 7px; padding: 10px 16px; }
QPushButton:hover { background: #354b60; }
QPushButton:disabled { color: #7b8b98; background: #202b36; border-color: #2e3a46; }
QPushButton[primary="true"] { background: #3bbf89; color: #10251d; font-weight: bold; border: none; }
QPushButton[primary="true"]:disabled { background: #275d48; color: #9cafaa; }
QLabel[title="true"] { font-size: 28px; font-weight: bold; }
QLabel[muted="true"] { color: #a5b6c4; }
QLabel[error="true"] { color: #ffbb9a; }
QTabWidget::pane { border: none; }
QTabBar::tab { background: #202b36; padding: 10px 22px; margin-right: 5px; border-radius: 6px; }
QTabBar::tab:selected { background: #354b60; }
QCheckBox { padding: 7px 0; }
QProgressBar { border: none; background: #263646; height: 3px; }
QProgressBar::chunk { background: #3bbf89; }
"""


def label(text: str, *, muted: bool = False) -> QLabel:
    widget = QLabel(text)
    widget.setTextFormat(Qt.TextFormat.PlainText)
    widget.setWordWrap(True)
    widget.setProperty("muted", muted)
    return widget


def field(name: str, placeholder: str = "", *, password: bool = False) -> QLineEdit:
    widget = QLineEdit()
    widget.setObjectName(name)
    widget.setPlaceholderText(placeholder)
    widget.setMaxLength(256)
    if password:
        widget.setEchoMode(QLineEdit.EchoMode.Password)
    return widget


def button(
    text: str, name: str, action: Callable[[], Any], *, primary: bool = False
) -> QPushButton:
    widget = QPushButton(text)
    widget.setObjectName(name)
    widget.setProperty("primary", primary)
    widget.clicked.connect(action)
    return widget


class PasswordDialog(QDialog):
    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setWindowTitle("Сменить пароль")
        layout = QVBoxLayout(self)
        layout.addWidget(
            label("Смена пароля завершит прежние сессии на всех устройствах.")
        )
        form = QFormLayout()
        self.old = field("oldPassword", password=True)
        self.new = field("newPassword", "Хотя бы 12 символов", password=True)
        self.repeat = field("repeatPassword", password=True)
        form.addRow("Текущий пароль", self.old)
        form.addRow("Новый пароль", self.new)
        form.addRow("Ещё раз", self.repeat)
        layout.addLayout(form)
        self.error = label("")
        self.error.setProperty("error", True)
        layout.addWidget(self.error)
        controls = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        controls.accepted.connect(self._validate)
        controls.rejected.connect(self.reject)
        layout.addWidget(controls)

    def _validate(self) -> None:
        if self.new.text() != self.repeat.text():
            self.error.setText("Новые пароли не совпадают.")
        elif not self.old.text() or len(self.new.text()) < 12:
            self.error.setText(
                "Введите текущий пароль и новый пароль из 12 или более символов."
            )
        else:
            self.accept()


class LauncherWindow(QMainWindow):
    def __init__(self, service: AccountService, *, auto_restore: bool = True) -> None:
        super().__init__()
        self.service = service
        self.pending: Registration | None = None
        self.busy = False
        self._task: Task | None = None
        self._success: Callable[[Any], None] | None = None
        self._context = ""
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(1)
        self.setWindowTitle("OmkalityCraft · разработка")
        self.resize(900, 650)
        self.setMinimumSize(760, 600)
        self.setStyleSheet(STYLE)
        root = QWidget()
        layout = QVBoxLayout(root)
        layout.setContentsMargins(30, 24, 30, 24)
        title = label("OMKALITYCRAFT")
        title.setProperty("title", True)
        layout.addWidget(title)
        layout.addWidget(label("Играть вместе. Без лишних шагов.", muted=True))
        self.pages = QStackedWidget()
        self.auth_page = self._auth_page()
        self.password_page = self._password_page()
        self.home_page = self._home_page()
        for page in [self.auth_page, self.password_page, self.home_page]:
            self.pages.addWidget(page)
        layout.addWidget(self.pages, 1)
        self.status = label("")
        self.status.setObjectName("statusMessage")
        self.status.setProperty("error", True)
        layout.addWidget(self.status)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.hide()
        layout.addWidget(self.progress)
        self.setCentralWidget(root)
        if auto_restore:
            QTimer.singleShot(0, self._restore)

    def _auth_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(label("Войти или присоединиться к серверу"))
        tabs = QTabWidget()
        layout.addWidget(tabs)
        signup, login = QWidget(), QWidget()
        signup_layout, login_layout = QFormLayout(signup), QFormLayout(login)
        self.signup_name = field("signupName", "От 3 до 16 латинских букв, цифр или _")
        self.invitation = field("invitationCode", "Код от владельца сервера")
        signup_layout.addRow("Ник", self.signup_name)
        signup_layout.addRow("Приглашение", self.invitation)
        signup_layout.addRow(
            label(
                "Пароль создадим автоматически. Его нужно будет сохранить один раз.",
                muted=True,
            )
        )
        signup_layout.addRow(
            button(
                "Продолжить",
                "prepareRegistration",
                self._prepare_registration,
                primary=True,
            )
        )
        self.login_name = field("loginName", "Ваш ник")
        self.login_password = field("loginPassword", password=True)
        login_layout.addRow("Ник", self.login_name)
        login_layout.addRow("Пароль", self.login_password)
        login_layout.addRow(button("Войти", "loginButton", self._login, primary=True))
        login_layout.addRow(
            button("Не помню пароль", "recoveryHelp", self._recovery_help)
        )
        self.login_password.returnPressed.connect(self._login)
        tabs.addTab(login, "Уже есть аккаунт")
        tabs.addTab(signup, "Первый вход")
        layout.addWidget(
            label(
                "Запомненный вход хранится в папке лаунчера. Не передавайте папку userdata другим людям.",
                muted=True,
            )
        )
        layout.addStretch()
        return page

    def _password_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(
            label(
                "Сохраните пароль — он пригодится на другом компьютере или после потери папки лаунчера."
            )
        )
        self.issued_password = field("issuedPassword")
        self.issued_password.setReadOnly(True)
        layout.addWidget(self.issued_password)
        layout.addWidget(
            button("Копировать пароль", "copyPassword", self._copy_password)
        )
        layout.addWidget(
            label(
                "Аккаунт будет создан после подтверждения. Пароль в файлы лаунчера не записывается.",
                muted=True,
            )
        )
        self.saved_password = QCheckBox("Я сохранил пароль в надёжном месте")
        self.saved_password.setObjectName("savedPassword")
        layout.addWidget(self.saved_password)
        self.register_button = button(
            "Создать аккаунт и войти", "registerButton", self._register, primary=True
        )
        self.register_button.setEnabled(False)
        self.saved_password.toggled.connect(self.register_button.setEnabled)
        layout.addWidget(self.register_button)
        self.retry_login = button(
            "Аккаунт уже создан? Войти выданным паролем",
            "retryIssuedLogin",
            self._login_issued,
        )
        self.retry_login.hide()
        layout.addWidget(self.retry_login)
        layout.addWidget(button("Назад", "registrationBack", self._back_to_auth))
        layout.addStretch()
        return page

    def _home_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        self.greeting = label("")
        self.greeting.setObjectName("greeting")
        layout.addWidget(self.greeting)
        layout.addWidget(label("Сборки"))
        packs = QListWidget()
        packs.setObjectName("serverProfiles")
        for profile in load_profiles():
            state = "Подготовка" if profile.status == "legacy" else "Планируется"
            packs.addItem(
                f"{profile.name}  ·  Minecraft {profile.minecraft}  ·  {state}"
            )
        layout.addWidget(packs)
        play = QPushButton("Запуск игры появится на следующем этапе")
        play.setEnabled(False)
        layout.addWidget(play)
        row = QHBoxLayout()
        self.skin_model = QComboBox()
        self.skin_model.addItem("Классические руки", "classic")
        self.skin_model.addItem("Узкие руки", "slim")
        row.addWidget(self.skin_model)
        row.addWidget(button("Загрузить скин…", "uploadSkin", self._choose_skin))
        self.skin_preview = QLabel()
        self.skin_preview.setFixedSize(64, 64)
        row.addWidget(self.skin_preview)
        layout.addLayout(row)
        layout.addWidget(
            button("Сменить пароль…", "changePassword", self._change_password)
        )
        layout.addWidget(button("Завершить все сессии…", "revokeAll", self._revoke_all))
        layout.addWidget(button("Забыть вход на этом ПК", "forgetDevice", self._forget))
        return page

    def _prepare_registration(self) -> None:
        try:
            self.pending = self.service.prepare_registration(
                self.signup_name.text(), self.invitation.text()
            )
        except AccountError as error:
            self.status.setText(str(error))
            return
        self.issued_password.setText(self.pending.password)
        self.saved_password.setChecked(False)
        self.retry_login.hide()
        self.status.clear()
        self.pages.setCurrentWidget(self.password_page)

    def _register(self) -> None:
        registration = self.pending
        if registration is not None and self.saved_password.isChecked():
            self.retry_login.show()
            self._start(
                lambda: self.service.register(registration),
                self._authenticated,
                "register",
            )

    def _login_issued(self) -> None:
        registration = self.pending
        if registration is not None:
            self._start(
                lambda: self.service.login(
                    registration.username, registration.password
                ),
                self._authenticated,
                "login",
            )

    def _copy_password(self) -> None:
        QApplication.clipboard().setText(self.issued_password.text())

    def _back_to_auth(self) -> None:
        self.pending = None
        self.issued_password.clear()
        self.pages.setCurrentWidget(self.auth_page)
        self.status.clear()

    def _login(self) -> None:
        name, password = self.login_name.text(), self.login_password.text()
        self.login_password.clear()
        self._start(
            lambda: self.service.login(name, password), self._authenticated, "login"
        )

    def _restore(self) -> None:
        self._start(self.service.restore, self._restored, "restore")

    def _restored(self, result: AuthResult | None) -> None:
        if result is not None:
            self._authenticated(result)
        else:
            self.pages.setCurrentWidget(self.auth_page)

    def _authenticated(self, result: AuthResult) -> None:
        self.pending = None
        self.issued_password.clear()
        self.login_password.clear()
        self.invitation.clear()
        self.greeting.setText(f"Привет, {result.session.player_name}!")
        self.pages.setCurrentWidget(self.home_page)
        self.status.setText(
            "Вход запомнен."
            if result.remembered
            else "Вход выполнен, но запомнить его не удалось. Проверьте доступ к папке лаунчера."
        )

    def _choose_skin(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Выберите PNG-скин", "", "PNG (*.png)"
        )
        if not path:
            return
        try:
            with Path(path).open("rb") as file:
                png = file.read(1024 * 1024 + 1)
            validate_skin(png)
        except (OSError, AccountError) as error:
            self._failed(error)
            return
        model = self.skin_model.currentData()

        def done(_: Any) -> None:
            pixmap = QPixmap()
            pixmap.loadFromData(png, "PNG")
            self.skin_preview.setPixmap(
                pixmap.scaled(64, 64, Qt.AspectRatioMode.KeepAspectRatio)
            )
            self.status.setText(
                "Скин загружен. В игре он появится после обновления профиля."
            )

        self._start(lambda: self.service.upload_skin(png, model), done, "skin")

    def _change_password(self) -> None:
        dialog = PasswordDialog(self)
        accepted = dialog.exec() == QDialog.DialogCode.Accepted
        old, new = dialog.old.text(), dialog.new.text()
        dialog.old.clear()
        dialog.new.clear()
        dialog.repeat.clear()
        dialog.deleteLater()
        if not accepted:
            return
        self._start(
            lambda: self.service.change_password(old, new),
            self._authenticated,
            "password",
        )

    def _revoke_all(self) -> None:
        password, ok = QInputDialog.getText(
            self,
            "Завершить все сессии",
            "Введите пароль. После этого нужно будет войти заново на всех устройствах.",
            QLineEdit.EchoMode.Password,
        )
        if ok:
            self._start(
                lambda: self.service.revoke_all(password), self._forgotten, "password"
            )

    def _forget(self) -> None:
        try:
            self.service.forget()
        except SessionStoreError as error:
            self.status.setText(str(error))
            return
        self._forgotten(None)

    def _forgotten(self, _: Any) -> None:
        self.skin_preview.clear()
        self.pages.setCurrentWidget(self.auth_page)
        self.status.setText("Вход на этом устройстве забыт.")

    def _recovery_help(self) -> None:
        QMessageBox.information(
            self,
            "Восстановление доступа",
            "Используйте выданный при регистрации пароль. Если он потерян вместе с сохранённым входом, "
            "обратитесь к владельцу сервера. Восстановление потребует подтверждения владельца аккаунта; "
            "одного ника недостаточно.",
        )

    def _start(
        self, operation: Callable[[], Any], success: Callable[[Any], None], context: str
    ) -> None:
        if self.busy:
            return
        self.busy, self._success, self._context = True, success, context
        self.pages.setEnabled(False)
        self.progress.show()
        self.status.setText("Соединяемся…")
        task = Task(operation)
        task.signals.completed.connect(self._completed)
        task.signals.failed.connect(self._failed)
        self._task = task
        self.pool.start(task)

    def _idle(self) -> None:
        self.busy = False
        self.pages.setEnabled(True)
        self.progress.hide()
        self._task = None
        self.status.clear()

    def _completed(self, result: Any) -> None:
        success, self._success = self._success, None
        self._idle()
        if success is not None:
            success(result)

    def _failed(self, error: Exception) -> None:
        self._success = None
        self._idle()
        if isinstance(error, PasswordChanged) or (
            self.pages.currentWidget() == self.home_page
            and self.service.current is None
        ):
            self.pages.setCurrentWidget(self.auth_page)
        if isinstance(error, (AccountError, SessionStoreError)):
            message = str(error)
        elif isinstance(error, DraslError):
            if error.status == 429:
                message = "Слишком много попыток. Подождите немного и повторите."
            elif error.status in {400, 401, 403} and self._context == "register":
                message = "Проверьте приглашение и ник. Если запрос прерывался, попробуйте войти выданным паролем."
            elif error.status in {400, 401, 403}:
                message = (
                    "Вход не подтверждён. Проверьте ник и пароль или войдите заново."
                )
            else:
                message = "Сервис временно недоступен. Повторите попытку позже."
        elif isinstance(error, OSError):
            message = "Не удалось соединиться с сервером или открыть файл. Сохранённый вход не удалён."
        else:
            message = "Не удалось выполнить действие. Повторите попытку."
        self.status.setText(message)

    @override
    def closeEvent(self, event: QCloseEvent) -> None:
        if self.busy:
            self.status.setText("Дождитесь завершения текущего действия.")
            event.ignore()
        else:
            event.accept()


def instance_lock(data_dir: Path) -> QLockFile | None:
    data_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    lock = QLockFile(str(data_dir / "launcher.lock"))
    lock.setStaleLockTime(0)
    return lock if lock.tryLock(0) else None


def run_launcher(auth_url: str, data_dir: Path) -> int:
    app = QApplication.instance() or QApplication(sys.argv[:1])
    try:
        lock = instance_lock(data_dir)
        if lock is None:
            QMessageBox.information(
                None, "OmkalityCraft", "Лаунчер с этой папкой данных уже открыт."
            )
            return 2
        service = AccountService(
            DraslClient(auth_url), FileSessionStore(data_dir / "session.json")
        )
    except OSError, ValueError:
        QMessageBox.warning(
            None,
            "OmkalityCraft",
            "Не удалось открыть папку данных или настроить адрес авторизации.",
        )
        return 2
    window = LauncherWindow(service)
    window.show()
    try:
        return app.exec()
    finally:
        lock.unlock()
