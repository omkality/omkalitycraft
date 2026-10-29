"""Account workflows independent of Qt and individual modpacks."""

import re
import secrets
import struct
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID, uuid4

from launcher.session import Session, SessionStore, SessionStoreError
from omk.drasl import DraslClient, DraslError


class AccountError(RuntimeError):
    """An error safe to show to a player."""


class PasswordChanged(AccountError):
    """The password changed, but the new session could not be established."""


@dataclass(frozen=True)
class Registration:
    username: str
    password: str = field(repr=False)
    invitation: str = field(repr=False)


@dataclass(frozen=True)
class AuthResult:
    session: Session
    remembered: bool


def validate_skin(png: bytes) -> None:
    if (
        len(png) < 24
        or len(png) > 1024 * 1024
        or png[:8] != b"\x89PNG\r\n\x1a\n"
        or png[12:16] != b"IHDR"
    ):
        raise AccountError("Нужен PNG-скин размером 64×64 или 64×32, до 1 МБ.")
    if struct.unpack(">II", png[16:24]) not in {(64, 64), (64, 32)}:
        raise AccountError("Нужен PNG-скин размером 64×64 или 64×32.")


class AccountService:
    def __init__(self, client: DraslClient, store: SessionStore) -> None:
        self.client = client
        self.store = store
        self.current: Session | None = None

    @staticmethod
    def prepare_registration(username: str, invitation: str) -> Registration:
        username, invitation = username.strip(), invitation.strip()
        if not re.fullmatch(r"[A-Za-z0-9_]{3,16}", username):
            raise AccountError(
                "Ник: от 3 до 16 латинских букв, цифр или знаков подчёркивания."
            )
        if not invitation:
            raise AccountError("Введите код приглашения.")
        # The player saves the issued password BEFORE the registration request.
        # Even a lost HTTP response cannot leave them with an unknown password.
        return Registration(username, secrets.token_urlsafe(24), invitation)

    def register(self, registration: Registration) -> AuthResult:
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

    def upload_skin(self, png: bytes, model: str) -> None:
        session = self._require_session()
        validate_skin(png)
        if model not in {"classic", "slim"}:
            raise AccountError("Выберите классическую модель или узкие руки.")
        self.client.upload_game_skin(
            UUID(session.player_uuid).hex, session.access_token, png, model
        )

    def _confirm_password(self, password: str) -> tuple[Session, str]:
        session = self._require_session()
        response = self.client.login(session.username, password)
        player = self._single_player(response["user"])
        if UUID(player["uuid"]) != UUID(session.player_uuid):
            raise AccountError("Не удалось подтвердить владельца аккаунта.")
        # This management token stays in memory only for the explicit operation.
        return session, response["apiToken"]

    def change_password(self, old_password: str, new_password: str) -> AuthResult:
        if len(new_password) < 12:
            raise AccountError("Новый пароль должен содержать хотя бы 12 символов.")
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
        session, api_token = self._confirm_password(password)
        self.client.signout(session.username, password)
        self.client.update_user(
            api_token, {"resetApiToken": True, "resetMinecraftToken": True}
        )
        self.forget()

    def forget(self) -> None:
        self.store.clear()
        self.current = None
