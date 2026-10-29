"""Session data has no account password; sensitive fields are excluded from repr."""

import json
from dataclasses import asdict, dataclass, field
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True)
class Session:
    origin: str
    username: str
    player_uuid: str
    player_name: str
    access_token: str = field(repr=False)
    client_token: str = field(repr=False)

    def __post_init__(self) -> None:
        for value in asdict(self).values():
            if not isinstance(value, str) or not value or len(value) > 8192:
                raise ValueError("Invalid session data")
        UUID(self.player_uuid)

    def serialize(self) -> str:
        return json.dumps({"schema": 1, **asdict(self)})

    @classmethod
    def deserialize(cls, value: str) -> Session:
        if len(value) > 32768:
            raise ValueError("Invalid session size")
        data = json.loads(value)
        if not isinstance(data, dict) or data.pop("schema", None) != 1:
            raise ValueError("Unsupported session schema")
        return cls(**data)


class SessionStoreError(RuntimeError):
    """Safe storage error without a filesystem path or credential payload."""


class SessionStore(Protocol):
    def load(self) -> Session | None: ...
    def save(self, session: Session) -> None: ...
    def clear(self) -> None: ...
