"""Small HTTP adapter; GUI code does not need to know Drasl route names."""

import base64
import json
import secrets
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


class DraslError(RuntimeError):
    """An HTTP failure without echoing a response containing credentials."""

    def __init__(self, status: int) -> None:
        self.status = status
        super().__init__(f"Drasl returned HTTP {status}")


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(
        self, req: Any, fp: Any, code: int, msg: str, headers: Any, newurl: str
    ) -> None:
        # Never forward an Authorization header or a password to another location.
        return None


class DraslClient:
    def __init__(self, base_url: str, timeout: float = 5.0) -> None:
        parts = urlsplit(base_url)
        if (
            not parts.hostname
            or parts.username is not None
            or parts.password is not None
            or parts.query
            or parts.fragment
            or parts.path not in {"", "/"}
        ):
            raise ValueError("Expected an authentication service origin")
        is_loopback = parts.hostname in {"127.0.0.1", "::1", "localhost"}
        if parts.scheme != "https" and not (parts.scheme == "http" and is_loopback):
            raise ValueError("Authentication requires HTTPS outside loopback")
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._opener = build_opener(_NoRedirect())

    def request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        token: str | None = None,
    ) -> Any:
        headers = {"Accept": "application/json"}
        data = None
        if payload is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(payload).encode("utf-8")
        if token is not None:
            headers["Authorization"] = f"Bearer {token}"
        body = self._send(method, path, data, headers)
        return json.loads(body) if body else None

    def _send(
        self, method: str, path: str, data: bytes | None, headers: dict[str, str]
    ) -> bytes:
        if not path.startswith("/") or path.startswith("//") or "#" in path:
            raise ValueError("Expected an absolute API path")
        request = Request(
            self.base_url + path, data=data, headers=headers, method=method
        )
        try:
            with self._opener.open(request, timeout=self.timeout) as response:
                body = response.read(4 * 1024 * 1024 + 1)
                if len(body) > 4 * 1024 * 1024:
                    raise DraslError(502)
        except HTTPError as exc:
            status = exc.code
            exc.close()
            raise DraslError(status) from None
        return body

    def register(
        self,
        username: str,
        password: str,
        invite: str,
        *,
        request_api_token: bool = True,
    ) -> dict[str, Any]:
        return self.request(
            "POST",
            "/drasl/api/v3/users",
            {
                "username": username,
                "password": password,
                "inviteCode": invite,
                "requestApiToken": request_api_token,
            },
        )

    def authenticate(
        self, username: str, password: str, client_token: str
    ) -> dict[str, Any]:
        return self.request(
            "POST",
            "/auth/authenticate",
            {
                "agent": {"name": "Minecraft", "version": 1},
                "username": username,
                "password": password,
                "clientToken": client_token,
                "requestUser": True,
            },
        )

    def login(self, username: str, password: str) -> dict[str, Any]:
        return self.request(
            "POST", "/drasl/api/v3/login", {"username": username, "password": password}
        )

    def user(self, token: str) -> dict[str, Any]:
        return self.request("GET", "/drasl/api/v3/user", token=token)

    def refresh(self, access_token: str, client_token: str) -> dict[str, Any]:
        return self.request(
            "POST",
            "/auth/refresh",
            {"accessToken": access_token, "clientToken": client_token},
        )

    def update_user(self, token: str, changes: dict[str, Any]) -> dict[str, Any]:
        return self.request("PATCH", "/drasl/api/v3/user", changes, token)

    def signout(self, username: str, password: str) -> None:
        self.request(
            "POST", "/auth/signout", {"username": username, "password": password}
        )

    def upload_skin(
        self, player_uuid: str, token: str, png: bytes, model: str
    ) -> dict[str, Any]:
        return self.request(
            "PATCH",
            f"/drasl/api/v3/players/{player_uuid}",
            {"skinBase64": base64.b64encode(png).decode("ascii"), "skinModel": model},
            token,
        )

    def upload_game_skin(
        self, player_id: str, token: str, png: bytes, model: str
    ) -> None:
        boundary = "omk-" + secrets.token_hex(16)
        form_model = "slim" if model == "slim" else ""
        body = (
            (
                f'--{boundary}\r\nContent-Disposition: form-data; name="model"\r\n\r\n{form_model}\r\n'
                f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="skin.png"\r\n'
                "Content-Type: image/png\r\n\r\n"
            ).encode()
            + png
            + f"\r\n--{boundary}--\r\n".encode()
        )
        self._send(
            "PUT",
            f"/authlib-injector/api/user/profile/{player_id}/skin",
            body,
            {
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "Authorization": f"Bearer {token}",
            },
        )

    def skin_profile(self, player_id: str) -> tuple[bytes, str] | None:
        from launcher.skins import (  # noqa: PLC0415 - keep PNG decoding lazy
            MAX_SKIN_BYTES,
            decode_skin,
        )

        profile = self.request("GET", f"/session/minecraft/profile/{player_id}")
        textures = next(
            (
                item["value"]
                for item in profile.get("properties", [])
                if item.get("name") == "textures"
            ),
            None,
        )
        if textures is None:
            return None
        payload = json.loads(base64.b64decode(textures, validate=True))
        skin = payload.get("textures", {}).get("SKIN")
        if skin is None:
            return None
        target, origin = urlsplit(skin["url"]), urlsplit(self.base_url)
        if target.username or target.password or target.fragment:
            raise ValueError("Invalid texture URL")
        if target.hostname == "textures.minecraft.net" and target.port in {None, 443}:
            target = target._replace(scheme="https")
        elif (target.scheme, target.netloc) != (origin.scheme, origin.netloc):
            raise ValueError("Unexpected texture origin")
        with self._opener.open(
            Request(urlunsplit(target)), timeout=self.timeout
        ) as response:
            png = response.read(MAX_SKIN_BYTES + 1)
        model = skin.get("metadata", {}).get("model", "classic")
        return decode_skin(png, model).png, model
