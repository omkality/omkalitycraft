"""Versioned result projection for owner clients; no execution or recovery policy."""

import subprocess
from typing import Annotated, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

Identity = Annotated[str, Field(pattern=r"^[a-f0-9]{32}$")]
ServerId = Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,47}$")]
Kind = Literal["backups", "maintenance", "restores"]
Phase = Literal[
    "planned",
    "preparing",
    "publishing",
    "published",
    "acknowledging",
    "incomplete",
    "complete",
    "cancelled",
    "stop-requested",
    "stopped",
    "start-requested",
    "applying",
    "staged",
]
SUPPORTED = frozenset(
    f"{kind}.{action}"
    for kind, actions in {
        "backups": ["plan", "run", "status", "finish", "cancel"],
        "maintenance": ["plan", "stop", "status", "start", "reconcile", "cancel"],
        "restores": ["plan", "apply", "verify", "status"],
    }.items()
    for action in actions
)
PHASES = {
    "backups": {
        "planned",
        "preparing",
        "publishing",
        "published",
        "acknowledging",
        "incomplete",
        "complete",
        "cancelled",
    },
    "maintenance": {
        "planned",
        "stop-requested",
        "stopped",
        "start-requested",
        "complete",
        "cancelled",
    },
    "restores": {"planned", "applying", "incomplete", "staged"},
}
TERMINAL = {
    "backups": {"complete", "cancelled"},
    "maintenance": {"complete", "cancelled"},
    "restores": {"staged"},
}
ErrorCode = Literal[
    "invalid_configuration",
    "owner_busy",
    "operation_rejected",
    "io_failure",
    "operation_failed",
    "invalid_service_result",
    "unsupported_action",
]
MESSAGES = {
    "invalid_configuration": "Check the private operator configuration and its permissions.",
    "owner_busy": "Another owner operation holds the lock; inspect before proceeding.",
    "operation_rejected": "The service refused or could not complete the operation; inspect its journal.",
    "io_failure": "I/O or process communication failed; inspect the recorded operation.",
    "operation_failed": "The operation failed; inspect its journal and configuration.",
    "invalid_service_result": "The service result does not match this contract; inspect before proceeding.",
    "unsupported_action": "This action is not part of owner result contract version 1.",
}


class OperationView(BaseModel):
    """Represent the current phase and state of an owner operation."""

    model_config = ConfigDict(extra="forbid", strict=True)

    id: Identity
    kind: Kind
    server_id: ServerId | None
    phase: Phase | None
    terminal: bool | None
    backup_operation_id: Identity | None = None

    @model_validator(mode="after")
    def consistent_phase(self) -> Self:
        """Reject phase and status combinations that contradict the result contract."""
        if self.phase is None:
            if self.terminal is not None:
                raise ValueError("Unknown phase requires unknown terminal status")
        elif self.phase not in PHASES[self.kind] or self.terminal is not (
            self.phase in TERMINAL[self.kind]
        ):
            raise ValueError("Phase or terminal status differs from operation kind")
        return self


class Failure(BaseModel):
    """Describe a failed owner action with a safe message and diagnostic code."""

    model_config = ConfigDict(extra="forbid", strict=True)

    code: ErrorCode
    message: Annotated[str, Field(max_length=256)]
    effect: Literal["none", "unknown"]
    next_step: Literal[
        "fix_configuration", "wait_then_inspect", "inspect_operation", "none"
    ]


class OwnerResult(BaseModel):
    """Envelope an owner CLI result for the terminal interface."""

    model_config = ConfigDict(extra="forbid", strict=True)

    schema_version: Literal[1]
    action: Annotated[str, Field(pattern=r"^[a-z][a-z0-9.\-]{0,79}$")]
    ok: bool
    status: Literal["succeeded", "failed", "unknown"]
    operation: OperationView | None
    error: Failure | None

    @field_validator("schema_version", mode="before")
    @classmethod
    def integer_version(cls, value):
        """Validate the supported integer version of the output schema."""
        if type(value) is not int:
            raise ValueError("Protocol version must be an integer")
        return value

    @model_validator(mode="after")
    def consistent_result(self) -> Self:
        """Check that success, failure and operation metadata agree."""
        if self.ok:
            if (
                self.status != "succeeded"
                or self.error is not None
                or self.operation is None
                or self.operation.phase is None
                or self.action not in SUPPORTED
            ):
                raise ValueError("Invalid successful result")
        elif self.status == "succeeded" or self.error is None:
            raise ValueError("Invalid unsuccessful result")
        return self


def request_view(action, args):
    """A supplied ID is a lookup reference, never evidence that an operation exists."""
    kind = action.split(".")[0]
    if kind not in PHASES:
        return None
    try:
        return OperationView(
            id=getattr(args, "operation", None),
            kind=kind,
            server_id=getattr(args, "server", None),
            phase=None,
            terminal=None,
        )
    except ValidationError:
        return None


def failure(action, args, code):
    next_step = "inspect_operation"
    if code == "invalid_configuration":
        next_step = "fix_configuration"
    elif code == "owner_busy":
        next_step = "wait_then_inspect"
    elif code == "unsupported_action":
        next_step = "none"
    no_effect = action.endswith(".status") or code in {
        "invalid_configuration",
        "owner_busy",
        "unsupported_action",
    }
    return OwnerResult(
        schema_version=1,
        action=action,
        ok=False,
        status="unknown" if code == "invalid_service_result" else "failed",
        operation=request_view(action, args),
        error=Failure(
            code=code,
            message=MESSAGES[code],
            effect="none" if no_effect else "unknown",
            next_step=next_step,
        ),
    ).model_dump(mode="json")


def error_code(error, *, configuring):
    from omk.owner.admin import AdminError  # noqa: PLC0415
    from omk.owner.admin_backups import OwnerBusy  # noqa: PLC0415

    if configuring:
        return "invalid_configuration"
    if isinstance(error, OwnerBusy):
        return "owner_busy"
    if isinstance(error, AdminError):
        return "operation_rejected"
    if isinstance(error, (OSError, subprocess.SubprocessError)):
        return "io_failure"
    return "operation_failed"


def success_view(action, args, value):
    operation = value["operation"]
    requested = getattr(args, "operation", None)
    if requested is not None and requested != operation:
        raise ValueError("Service returned another operation")
    server = value.get("server", getattr(args, "server", None))
    requested_server = getattr(args, "server", None)
    if requested_server is not None and requested_server != server:
        raise ValueError("Service returned another server")
    kind = action.split(".")[0]
    return OperationView(
        id=operation,
        kind=kind,
        server_id=server,
        phase=value["stage"],
        terminal=value["stage"] in TERMINAL[kind],
        backup_operation_id=value.get("backup_operation"),
    )


def project(action, args, value, *, error=None, configuring=False):
    """Project existing service output without copying private journals or error input."""
    if error is not None:
        return failure(action, args, error_code(error, configuring=configuring))
    if not isinstance(value, dict) or type(value.get("ok")) is not bool:
        return failure(action, args, "invalid_service_result")
    if not value["ok"]:
        return failure(action, args, "operation_failed")
    try:
        return OwnerResult(
            schema_version=1,
            action=action,
            ok=True,
            status="succeeded",
            error=None,
            operation=success_view(action, args, value),
        ).model_dump(mode="json")
    except KeyError, TypeError, ValueError:
        return failure(action, args, "invalid_service_result")


def json_schema():
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "urn:omkalitycraft:owner-result:1",
        "x-supported-actions": sorted(SUPPORTED),
        "$comment": (
            "Shape schema; consumers also enforce the phase/terminal and "
            "ok/status/error invariants documented in OWNER_RESULT.md."
        ),
        "x-phases-by-kind": {kind: sorted(phases) for kind, phases in PHASES.items()},
        "x-terminal-phases-by-kind": {
            kind: sorted(phases) for kind, phases in TERMINAL.items()
        },
        **OwnerResult.model_json_schema(),
    }
