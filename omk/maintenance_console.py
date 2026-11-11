"""Fixed graceful-stop transport; separate from account recovery privileges."""

import socket
import time

from omk.recovery_console import ConsoleError, _packet, _receive


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
