import hashlib
import json

from omk.profiles import PROJECT_ROOT


def test_bundled_font_and_license_bytes_match_pinned_upstream_artifacts():
    folder = PROJECT_ROOT / "launcher/assets/fonts"
    provenance = json.loads((folder / "provenance.json").read_text(encoding="utf-8"))
    for artifact in provenance["artifacts"]:
        assert (
            hashlib.sha256((folder / artifact["file"]).read_bytes()).hexdigest()
            == artifact["sha256"]
        )
