"""Account workflows independent of Qt and individual modpacks."""

import re
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID, uuid4

from launcher.session import Session, SessionStore, SessionStoreError
from launcher.skin_defaults import DEFAULT_SKIN_MODEL, default_skin_bytes
from launcher.skins import SkinError, decode_skin
from omk.accounts import MAX_REGISTRATION_PASSWORD_LENGTH, MIN_PASSWORD_LENGTH
from omk.accounts.drasl import DraslClient, DraslError

USERNAME_PATTERN = r"[A-Za-z0-9_]{3,16}"
PASSWORD_RANGE = (
    f"от {MIN_PASSWORD_LENGTH} до {MAX_REGISTRATION_PASSWORD_LENGTH} символов"
)


class AccountError(RuntimeError):
    """An error safe to show to a player."""


class PasswordChanged(AccountError):
    """The password changed, but the new session could not be established."""


@dataclass(frozen=True)
class Registration:
    """Carry validated registration input until the account request completes."""

    username: str
    password: str = field(repr=False)
    invitation: str = field(repr=False)


@dataclass(frozen=True)
class AuthResult:
    """Carry the active session and profile information needed by the launcher."""

    session: Session
    remembered: bool
    skin_png: bytes | None = field(default=None, repr=False)
    skin_model: str = "classic"


def validate_skin(png: bytes) -> None:
    try:
        decode_skin(png)
    except SkinError as error:
        raise AccountError(str(error)) from None


class AccountService:
    """Coordinate Drasl requests with the launcher's portable session store."""

    def __init__(self, client: DraslClient, store: SessionStore) -> None:
        self.client = client
        self.store = store
        self.current: Session | None = None

    @staticmethod
    def prepare_registration(
        username: str, invitation: str, password: str
    ) -> Registration:
        """Validate the invitation, nickname and password fields for registration."""
        username, invitation = username.strip(), invitation.strip()
        if not re.fullmatch(USERNAME_PATTERN, username):
            raise AccountError(
                "Ник: от 3 до 16 латинских букв, цифр или знаков подчёркивания."
            )
        if not invitation:
            raise AccountError("Введите код приглашения.")
        if (
            not isinstance(password, str)
            or not MIN_PASSWORD_LENGTH
            <= len(password)
            <= MAX_REGISTRATION_PASSWORD_LENGTH
        ):
            raise AccountError(f"Пароль должен содержать {PASSWORD_RANGE}.")
        return Registration(username, password, invitation)

    def register(self, registration: Registration) -> AuthResult:
        """Redeem an invitation and establish the account's game session."""
        response = self.client.register(
            registration.username,
            registration.password,
            registration.invitation,
            request_api_token=False,
        )
        player = self._single_player(response["user"])
        return self._authenticate(
            registration.username, registration.password, player["uuid"]
        )

    def login(self, username: str, password: str) -> AuthResult:
        """Authenticate with Drasl and save the resulting game session."""
        if not username.strip() or not password:
            raise AccountError("Введите ник и пароль.")
        return self._authenticate(username.strip(), password)

    def _authenticate(
        self, username: str, password: str, expected_uuid: str | None = None
    ) -> AuthResult:
        client_token = uuid4().hex
        game = self.client.authenticate(username, password, client_token)
        session = self._session(username, game)
        if session.client_token != client_token:
            raise AccountError("Сервис вернул несовпадающую сессию. Вход остановлен.")
        if expected_uuid is not None and UUID(session.player_uuid) != UUID(
            expected_uuid
        ):
            raise AccountError(
                "Сервис вернул несовпадающий игровой профиль. Вход остановлен."
            )
        return self._remember(session)

    @staticmethod
    def _single_player(user: dict[str, Any]) -> dict[str, Any]:
        players = user.get("players", [])
        if len(players) != 1:
            raise AccountError(
                "Для этого лаунчера у аккаунта должен быть один игровой профиль."
            )
        return players[0]

    def _session(self, username: str, game: dict[str, Any]) -> Session:
        selected = game.get("selectedProfile")
        if not selected:
            raise AccountError("У аккаунта нет выбранного игрового профиля.")
        return Session(
            self.client.base_url,
            username,
            str(UUID(selected["id"])),
            selected["name"],
            game["accessToken"],
            game["clientToken"],
        )

    def _remember(self, session: Session) -> AuthResult:
        self.current = session
        try:
            self.store.save(session)
        except SessionStoreError:
            return AuthResult(session, remembered=False)
        return AuthResult(session, remembered=True)

    def restore(self) -> AuthResult | None:
        """Load and validate the remembered session at startup."""
        saved = self.store.load()
        if saved is None:
            return None
        if saved.origin != self.client.base_url:
            raise AccountError(
                "Сохранённый вход относится к другому серверу авторизации."
            )
        try:
            game = self.client.refresh(saved.access_token, saved.client_token)
        except DraslError as exc:
            if exc.status not in {400, 401, 403}:
                raise
            self.forget()
            return None
        session = self._session(saved.username, game)
        if (
            session.player_uuid != saved.player_uuid
            or session.client_token != saved.client_token
        ):
            raise AccountError(
                "Сервис вернул другой профиль или другую сессию. Вход остановлен."
            )
        return self._remember(session)

    def _require_session(self) -> Session:
        if self.current is None:
            raise AccountError("Сначала войдите в аккаунт.")
        return self.current

    def renew_for_game(self) -> Session:
        """Refresh game credentials before starting the client."""
        saved = self._require_session()
        try:
            game = self.client.refresh(saved.access_token, saved.client_token)
        except DraslError as error:
            if error.status in {400, 401, 403}:
                self.current = None
                self.store.clear()
            raise
        session = self._session(saved.username, game)
        if (
            session.player_uuid != saved.player_uuid
            or session.client_token != saved.client_token
        ):
            raise AccountError("Сервис вернул другую игровую сессию.")
        return self._remember(session).session

    def upload_skin(self, png: bytes, model: str) -> None:
        """Upload the selected skin for the authenticated game profile."""
        session = self._require_session()
        try:
            png = decode_skin(png, model).png
        except SkinError as error:
            raise AccountError(str(error)) from None
        self.client.upload_game_skin(
            UUID(session.player_uuid).hex, session.access_token, png, model
        )

    def reset_skin(self) -> None:
        """Restore the default skin for the authenticated game profile."""
        self.upload_skin(default_skin_bytes(), DEFAULT_SKIN_MODEL)

    def _confirm_password(self, password: str) -> tuple[Session, str]:
        session = self._require_session()
        response = self.client.login(session.username, password)
        player = self._single_player(response["user"])
        if UUID(player["uuid"]) != UUID(session.player_uuid):
            raise AccountError("Не удалось подтвердить владельца аккаунта.")
        # This management token stays in memory only for the explicit operation.
        return session, response["apiToken"]

    def change_password(self, old_password: str, new_password: str) -> AuthResult:
        """Change the account password and report whether the game session was renewed."""
        if len(new_password) < MIN_PASSWORD_LENGTH:
            raise AccountError(
                f"Новый пароль должен содержать хотя бы {MIN_PASSWORD_LENGTH} символов."
            )
        if old_password == new_password:
            raise AccountError("Новый пароль должен отличаться от прежнего.")
        session, api_token = self._confirm_password(old_password)
        self.client.update_user(
            api_token,
            {
                "password": new_password,
                "resetApiToken": True,
                "resetMinecraftToken": True,
            },
        )
        self.current = None
        try:
            self.store.clear()
            return self.login(session.username, new_password)
        except OSError, DraslError, SessionStoreError:
            raise PasswordChanged("Пароль изменён. Войдите с новым паролем.") from None

    def revoke_all(self, password: str) -> None:
        """Revoke the account's sessions through Drasl and clear the local session."""
        session, api_token = self._confirm_password(password)
        self.client.signout(session.username, password)
        self.client.update_user(
            api_token, {"resetApiToken": True, "resetMinecraftToken": True}
        )
        self.current = None
        self.store.clear()

    def forget(self) -> None:
        """Remove the remembered session from the portable data directory."""
        self.store.clear()
        self.current = None
