"""Explicit test doubles; never used as runtime credential storage."""

from typing import Any
from uuid import uuid4

from omk.drasl import DraslClient


class FakeDrasl(DraslClient):
    def __init__(self) -> None:
        super().__init__("http://127.0.0.1:25586")
        self.player_uuid = uuid4().hex
        self.management_token = "test-management-token-must-not-be-saved"
        self.calls: list[tuple[str, Any]] = []
        self.refresh_error: Exception | None = None

    def register(
        self,
        username: str,
        password: str,
        invite: str,
        *,
        request_api_token: bool = True,
    ) -> dict[str, Any]:
        self.calls.append(("register_requests_management_token", request_api_token))
        return {
            "user": {
                "username": username,
                "players": [{"uuid": self.player_uuid, "name": username}],
            }
        }

    def authenticate(
        self, username: str, password: str, client_token: str
    ) -> dict[str, Any]:
        self.calls.append(("authenticate", username))
        return self.game(client_token)

    def game(self, client_token: str) -> dict[str, Any]:
        return {
            "accessToken": "test-game-token",
            "clientToken": client_token,
            "selectedProfile": {"id": self.player_uuid, "name": "test_player"},
        }

    def refresh(self, access_token: str, client_token: str) -> dict[str, Any]:
        self.calls.append(("refresh", None))
        if self.refresh_error is not None:
            raise self.refresh_error
        return {**self.game(client_token), "accessToken": "test-renewed-game-token"}

    def login(self, username: str, password: str) -> dict[str, Any]:
        return {
            "apiToken": self.management_token,
            "user": {"players": [{"uuid": self.player_uuid, "name": "test_player"}]},
        }

    def update_user(self, token: str, changes: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(("update_user", set(changes)))
        return {}

    def signout(self, username: str, password: str) -> None:
        self.calls.append(("signout", username))

    def upload_game_skin(
        self, player_id: str, token: str, png: bytes, model: str
    ) -> None:
        self.calls.append(("upload_skin", model))

    def skin_profile(self, player_id: str) -> tuple[bytes, str] | None:
        return None
