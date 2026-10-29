"""Small HTTP adapter; GUI code does not need to know Drasl route names."""

import json
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlsplit
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
        if not path.startswith("/") or path.startswith("//") or "#" in path:
            raise ValueError("Expected an absolute API path")
        headers = {"Accept": "application/json"}
        data = None
        if payload is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(payload).encode("utf-8")
        if token is not None:
            headers["Authorization"] = f"Bearer {token}"
        request = Request(
            self.base_url + path, data=data, headers=headers, method=method
        )
        try:
            with self._opener.open(request, timeout=self.timeout) as response:
                body = response.read()
        except HTTPError as exc:
            status = exc.code
            exc.close()
            raise DraslError(status) from None
        return json.loads(body) if body else None

    def register(self, username: str, password: str, invite: str) -> dict[str, Any]:
        return self.request(
            "POST",
            "/drasl/api/v3/users",
            {
                "username": username,
                "password": password,
                "inviteCode": invite,
                "requestApiToken": True,
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
            },
        )
