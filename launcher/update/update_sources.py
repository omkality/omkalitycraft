"""Narrow public release-asset policy; trust still comes from signed TUF metadata."""

import re
from urllib.parse import urlsplit

from launcher.releases import PLATFORMS

GITHUB_RELEASES = "https://github.com/omkality/omkalitycraft/releases/download/"
GITHUB_ASSET_HOST = "release-assets.githubusercontent.com"


def github_asset_url(value: str, version: str, platform: str) -> str:
    """Accept our versioned portable bundle only, never latest or an API response."""
    if (
        not isinstance(value, str)
        or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.+_-]{0,79}", version)
        or platform not in PLATFORMS
    ):
        raise ValueError("Invalid GitHub launcher asset")
    filename = f"OmkalityCraft-{version}-{platform}.zip"
    expected = {
        f"{GITHUB_RELEASES}{tag}/{filename}"
        for tag in (f"v{version}", f"launcher-v{version}")
    }
    if value not in expected:
        raise ValueError("Expected a versioned OmkalityCraft launcher release asset")
    return value


def github_asset_redirect(value: str) -> str:
    """GitHub's public asset CDN only; no credentials, downgrade or other hosts."""
    if (
        not isinstance(value, str)
        or len(value) > 8192
        or "#" in value
        or any(ord(char) <= 32 or ord(char) >= 127 or char == "\\" for char in value)
    ):
        raise ValueError("Invalid GitHub asset redirect")
    parts = urlsplit(value)
    if (
        parts.scheme != "https"
        or parts.hostname != GITHUB_ASSET_HOST
        or parts.port not in {None, 443}
        or parts.username is not None
        or parts.password is not None
        or parts.fragment
    ):
        raise ValueError("Untrusted GitHub asset redirect")
    return value
