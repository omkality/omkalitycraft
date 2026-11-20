import pytest

from omk.accounts.drasl import DraslClient, DraslError
from tests.fixtures.unit.accounts.drasl_transport import auth_origin

__all__ = ["auth_origin"]


@pytest.mark.parametrize(
    "origin",
    [
        "http://example.com",
        "http://localhost.example.com",
        "https://user:password@example.com",
        "https://example.com?token=secret",
        "https://example.com#fragment",
    ],
)
def test_unsafe_auth_origin_is_rejected(origin: str) -> None:
    with pytest.raises(ValueError):
        DraslClient(origin)


def test_auth_request_does_not_follow_redirect(
    auth_origin: tuple[str, list[str]],
) -> None:
    origin, seen = auth_origin
    with pytest.raises(DraslError) as error:
        DraslClient(origin).request("GET", "/redirect", token="test-token")
    assert error.value.status == 302
    assert seen == ["/redirect"]


def test_auth_error_does_not_expose_response_body(
    auth_origin: tuple[str, list[str]],
) -> None:
    origin, _ = auth_origin
    with pytest.raises(DraslError) as error:
        DraslClient(origin).request("GET", "/error")
    assert error.value.status == 403
    assert "must-not-be-printed" not in str(error.value)
