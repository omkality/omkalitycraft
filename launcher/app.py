"""Portable desktop launcher with account and installation workflows."""

import json
import sys
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any, override

from PySide6.QtCore import QLockFile, Qt, QThreadPool, QTimer
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QLabel,
    QLineEdit,
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
)
from launcher.controller import InstallationResult, InstallController
from launcher.dashboard import Dashboard
from launcher.game import GameProcess, GameRunner
from launcher.install import Installer, ReleaseClient
from launcher.memory import MIN_MB, Preferences
from launcher.releases import ReleaseError
from launcher.session import SessionStoreError
from launcher.skin_dialog import SkinDialog
from launcher.skins import MAX_SKIN_BYTES, SkinError, decode_skin
from launcher.social import SocialFooter
from launcher.storage import FileSessionStore
from launcher.tasks import Task
from launcher.theme import ASSETS, STYLE, install_font
from launcher.widgets import BusyButton
from omk.diagnostics import event, failure
from omk.drasl import DraslClient, DraslError


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
    widget = BusyButton(text)
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
    def __init__(
        self,
        service: AccountService,
        *,
        auto_restore: bool = True,
        installer: Installer | None = None,
        runner: GameRunner | None = None,
    ) -> None:
        super().__init__()
        self.service = service
        self.report_runner = runner
        self.diagnostic_root = runner.root if runner is not None else None
        store_path = getattr(service.store, "path", None)
        self.preferences = Preferences(
            store_path.parent / "preferences.json" if store_path is not None else None
        )
        install_font(QApplication.instance())
        self.installation: InstallController | None = None
        self.game: GameProcess | None = None
        self.game_pack: str | None = None
        self._close_after_install = False
        self._busy_button: BusyButton | None = None
        self.pending: Registration | None = None
        self.busy = False
        self._task: Task | None = None
        self._success: Callable[[Any], None] | None = None
        self._context = ""
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(1)
        self.setWindowTitle("OmkalityCraft · разработка")
        self.resize(1200, 850)
        self.setMinimumSize(1020, 680)
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
        layout.addWidget(SocialFooter())
        self.setCentralWidget(root)
        self._setup_installation(installer, runner)
        if auto_restore:
            QTimer.singleShot(0, self._restore)

    def _setup_installation(
        self, installer: Installer | None, runner: GameRunner | None
    ) -> None:
        self.game_timer = QTimer(self)
        self.game_timer.setInterval(1500)
        self.game_timer.timeout.connect(self._poll_game)
        if installer is not None and runner is not None:
            self.installation = InstallController(installer, self.service, runner, self)
            self.installation.progress.connect(self._install_progress)
            self.installation.completed.connect(self._installed)
            self.installation.failed.connect(self._install_failed)
            self.installation.states.connect(self._local_states)
            self.home_page.install_requested.connect(self._install)
            self.home_page.cancel_requested.connect(self.installation.cancel)
            self.installation.inspect(list(self.home_page.cards))
        else:
            for card in self.home_page.cards.values():
                card.action.setEnabled(False)

    def _auth_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(label("Войти или присоединиться к сообществу"))
        tabs = QTabWidget()
        layout.addWidget(tabs)
        signup, login = QWidget(), QWidget()
        signup_layout, login_layout = QFormLayout(signup), QFormLayout(login)
        self.signup_name = field("signupName", "От 3 до 16 латинских букв, цифр или _")
        self.invitation = field("invitationCode", "Код от владельца проекта")
        signup_layout.addRow("Ник", self.signup_name)
        signup_layout.addRow("Приглашение", self.invitation)
        signup_layout.addRow(
            label(
                "При сбое лаунчер может автоматически передать владельцу технический отчёт об ошибке.",
                muted=True,
            )
        )
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

    def _home_page(self) -> Dashboard:
        page = Dashboard(self.preferences)
        page.message.connect(self.status_message)
        self.greeting = page.greeting
        self.skin_preview = page.skin_preview
        page.upload_button.clicked.connect(self._choose_skin)
        page.change_password.clicked.connect(self._change_password)
        return page

    def status_message(self, message: str) -> None:
        self.status.setText(message)

    def _local_states(self, states: dict) -> None:
        for pack_id, state in states.items():
            card = self.home_page.cards[pack_id]
            if card.profile.status != "planned":
                card.set_local_state(state)

    def _install(self, pack_id: str) -> None:
        if (
            self.busy
            or self.game is not None
            or self.installation is None
            or self.installation.busy
        ):
            return
        self.status.clear()
        memory_mb = self.home_page.cards[pack_id].memory.selected_mb
        if memory_mb < MIN_MB:
            self.status.setText("Недостаточно памяти для запуска этой сборки.")
            return
        self.home_page.upload_button.setEnabled(False)
        self.home_page.change_password.setEnabled(False)
        for card in self.home_page.cards.values():
            card.action.setEnabled(False)
        self.home_page.cards[pack_id].action.set_busy(True, "Подготавливаем…")
        self.installation.start(
            pack_id, play=self.home_page.cards[pack_id].installed, memory_mb=memory_mb
        )

    def _install_progress(self, pack_id: str, progress) -> None:
        self.home_page.cards[pack_id].update_progress(progress)

    def _installation_idle(self) -> None:
        self.home_page.upload_button.setEnabled(True)
        self.home_page.change_password.setEnabled(True)
        for card in self.home_page.cards.values():
            card.action.setEnabled(card.profile.status != "planned")

    def _installed(self, pack_id: str, result: InstallationResult) -> None:
        if self.diagnostic_root is not None:
            event(
                self.diagnostic_root,
                "pack_prepared",
                pack=pack_id,
                pack_version=result.release.version,
            )
        self._installation_idle()
        card = self.home_page.cards[pack_id]
        card.finished(success=True)
        card.state_label.setText("Установлена · " + result.release.version)
        if result.game is not None:
            self.game, self.game_pack = result.game, pack_id
            card.action.setText("Игра запущена")
            for other in self.home_page.cards.values():
                other.action.setEnabled(False)
            self.skin_preview.animation.pause()
            self.game_timer.start()
        if self._close_after_install:
            self.close()

    def _install_failed(self, pack_id: str, error: Exception) -> None:
        if self.diagnostic_root is not None:
            failure(self.diagnostic_root, "install:" + pack_id, error)
        self._installation_idle()
        message = (
            str(error)
            if isinstance(error, ReleaseError)
            else "Не удалось подготовить игру. Повторите попытку."
        )
        self.home_page.cards[pack_id].finished(success=False, message=message)
        if self.service.current is None:
            self.pages.setCurrentWidget(self.auth_page)
        if self._close_after_install:
            self.close()

    def _poll_game(self) -> None:
        if self.game is None or self.game.poll() is None:
            return
        if not self.game.diagnostics_done.is_set():
            return
        code = self.game.poll()
        logging_failed = self.game.logging_failed.is_set()
        card = self.home_page.cards[self.game_pack]
        self.game, self.game_pack = None, None
        self.game_timer.stop()
        self._installation_idle()
        card.finished(success=True)
        self.skin_preview.animation.resume()
        if code:
            self.status.setText("Игра завершилась с ошибкой. Можно запустить её снова.")
        elif logging_failed:
            self.status.setText(
                "Не удалось записать журнал игры. Проверьте свободное место и доступ к папке лаунчера."
            )
        if self.isHidden():
            self.close()
            QApplication.instance().quit()

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
        if self.report_runner is not None:
            self.report_runner.send_reports(result.session)
        self.pending = None
        self.issued_password.clear()
        self.login_password.clear()
        self.invitation.clear()
        self.greeting.setText(f"Привет, {result.session.player_name}!")
        self.pages.setCurrentWidget(self.home_page)
        if result.skin_png is not None:
            self.skin_preview.set_skin(result.skin_png, result.skin_model)
        else:
            self.skin_preview.reset_skin()
        self.status.setText(
            ""
            if result.remembered
            else "Вход выполнен, но запомнить его не удалось. Проверьте доступ к папке лаунчера."
        )

    def _choose_skin(self) -> None:
        if self.busy:
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Выберите PNG-скин", "", "PNG (*.png)"
        )
        if not path:
            return
        try:
            with Path(path).open("rb") as file:
                png = file.read(MAX_SKIN_BYTES + 1)
            skin = decode_skin(png)
            png = skin.png
        except (OSError, AccountError, SkinError) as error:
            self._failed(error)
            return
        dialog = SkinDialog(skin, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        model = dialog.model

        def done(_: Any) -> None:
            self.skin_preview.set_skin(png, model)
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
        if self.busy or (self.installation is not None and self.installation.busy):
            return
        self.busy, self._success, self._context = True, success, context
        if self.diagnostic_root is not None:
            event(self.diagnostic_root, "operation_started", context=context)
        self.pages.setEnabled(False)
        self.progress.show()
        self.status.setText("Соединяемся…")
        names = {
            "login": "loginButton",
            "register": "registerButton",
            "skin": "uploadSkin",
            "password": "changePassword",
        }
        self._busy_button = self.findChild(BusyButton, names.get(context, ""))
        if self._busy_button is not None:
            self._busy_button.set_busy(True, "Подождите…")

        def with_skin():
            result = operation()
            if isinstance(result, AuthResult):
                try:
                    skin = self.service.client.skin_profile(result.session.player_uuid)
                    if skin is not None:
                        result = replace(result, skin_png=skin[0], skin_model=skin[1])
                except (
                    OSError,
                    DraslError,
                    ValueError,
                    KeyError,
                    TypeError,
                    AttributeError,
                ):
                    pass  # A texture outage must not invalidate a successful login.
            return result

        task = Task(with_skin)
        task.signals.completed.connect(self._completed)
        task.signals.failed.connect(self._failed)
        self._task = task
        self.pool.start(task)

    def _idle(self) -> None:
        self.busy = False
        if self._busy_button is not None:
            self._busy_button.set_busy(False)
            self._busy_button = None
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
        if self.diagnostic_root is not None:
            failure(self.diagnostic_root, self._context, error)
        self._success = None
        self._idle()
        if isinstance(error, PasswordChanged) or (
            self.pages.currentWidget() == self.home_page
            and self.service.current is None
        ):
            self.pages.setCurrentWidget(self.auth_page)
        if isinstance(error, (AccountError, SessionStoreError, SkinError)):
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
        if self.installation is not None and self.installation.busy:
            self._close_after_install = True
            self.installation.cancel()
            event.ignore()
        elif self.game is not None and self.game.poll() is None:
            self.hide()
            event.ignore()
        elif self.busy:
            self.status.setText("Дождитесь завершения текущего действия.")
            event.ignore()
        else:
            event.accept()


def instance_lock(data_dir: Path, name: str = "launcher.lock") -> QLockFile | None:
    data_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    lock = QLockFile(str(data_dir / name))
    lock.setStaleLockTime(0)
    return lock if lock.tryLock(0) else None


def run_launcher(
    auth_url: str,
    data_dir: Path,
    *,
    api_url: str | None = None,
    root: Path | None = None,
) -> int:
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
    root = root or data_dir.parent
    installer = None
    if api_url is not None:
        keys = json.loads((ASSETS / "release-keys.json").read_text(encoding="utf-8"))
        installer = Installer(root, ReleaseClient(api_url, keys))
    window = LauncherWindow(
        service, installer=installer, runner=GameRunner(root, reports_url=api_url)
    )
    window.show()
    try:
        return app.exec()
    finally:
        lock.unlock()
