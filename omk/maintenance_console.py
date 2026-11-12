"""Fixed graceful-stop transport; separate from account recovery privileges."""

import json
import re
import socket
import time

from omk.recovery_console import ConsoleError, _packet, _receive, command


class MaintenanceConsole:
    """Typed internal API for the coordinator/TUI. No new operator CLI group."""

    def __init__(self, config, password):
        self.config, self.password = config, password

    def _request(self, suffix):
        output = command(self.config, self.password, "list omk-maintenance " + suffix)
        if not output.startswith("OMK_MAINTENANCE_V1 "):
            raise ConsoleError("Server lacks a confirmed maintenance bridge response")
        try:
            value = json.loads(output[len("OMK_MAINTENANCE_V1 ") :])
        except ValueError:
            raise ConsoleError("Invalid maintenance bridge JSON") from None
        if (
            not isinstance(value, dict)
            or type(value.get("schema")) is not int
            or value.get("schema") != 1
            or value.get("main_thread") is not True
            or not isinstance(value.get("boot"), str)
            or not re.fullmatch(r"[a-f0-9]{32}", value["boot"])
        ):
            raise ConsoleError(
                "Invalid maintenance bridge schema, boot or thread proof"
            )
        return value

    def probe(self):
        value = self._request("probe")
        if set(value) != {
            "schema",
            "boot",
            "main_thread",
            "backup_adapter",
            "automatic_backups_disabled",
            "backup_running",
        } or (
            not isinstance(value["backup_adapter"], str)
            or not re.fullmatch(r"[a-z0-9][a-z0-9.-]{0,79}", value["backup_adapter"])
            or type(value["automatic_backups_disabled"]) is not bool
            or type(value["backup_running"]) is not bool
        ):
            raise ConsoleError("Invalid loaded backup policy proof")
        return value

    def ready(self, adapter, *, boot=None):
        value = self.probe()
        if (
            value["backup_adapter"] != adapter
            or not value["automatic_backups_disabled"]
            or value["backup_running"]
            or (boot is not None and value["boot"] != boot)
        ):
            raise ConsoleError("Loaded backup policy or server boot is not ready")
        return value

    def warn(self, boot, operation, seconds_before):
        if any(
            not isinstance(value, str) or not re.fullmatch(r"[a-f0-9]{32}", value)
            for value in (boot, operation)
        ) or (type(seconds_before) is not int or not 1 <= seconds_before <= 3600):
            raise ConsoleError("Invalid maintenance notice identity or countdown")
        value = self._request(f"warn {boot} {operation} {seconds_before}")
        if (
            set(value)
            != {
                "schema",
                "boot",
                "main_thread",
                "operation",
                "seconds_before",
                "delivered",
                "replayed",
            }
            or value["boot"] != boot
            or value["operation"] != operation
            or type(value["seconds_before"]) is not int
            or value["seconds_before"] != seconds_before
            or type(value["delivered"]) is not int
            or not 0 <= value["delivered"] <= 10000
            or type(value["replayed"]) is not bool
        ):
            raise ConsoleError("Invalid maintenance notice receipt")
        return value


def stop(config, password):
    if (
        not isinstance(password, str)
        or not 16 <= len(password) <= 1024
        or "\0" in password
    ):
        raise ConsoleError("Invalid maintenance console credential")
    deadline = time.monotonic() + 8
    with socket.create_connection((config.host, config.port), timeout=3) as stream:
        stream.sendall(_packet(1, 3, password))
        for _ in range(3):
            number, kind, _ = _receive(stream, deadline)
            if number == -1:
                raise ConsoleError("Maintenance console authentication failed")
            if number == 1 and kind == 2:
                break
        else:
            raise ConsoleError("Invalid maintenance console authentication response")
        # Do not send a delimiter: stop may close RCON before a response. Neither
        # sendall nor a response proves a clean stop; the controller checks Docker.
        stream.sendall(_packet(2, 2, "stop"))
