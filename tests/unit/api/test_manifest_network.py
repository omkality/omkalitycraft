import socket

import pytest

from launcher.install import ReleaseClient
from launcher.releases import ReleaseError


def test_closed_loopback_manifest_endpoint_returns_readable_network_error():
    with socket.socket() as offline:
        offline.bind(("127.0.0.1", 0))
        with pytest.raises(ReleaseError, match="Проверьте соединение"):
            ReleaseClient(f"http://127.0.0.1:{offline.getsockname()[1]}", {}).fetch(
                "dj2"
            )
