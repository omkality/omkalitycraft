from pathlib import Path

import pytest
import yaml

from scripts.tui_sandbox import prepare


def test_prepare_refuses_existing_data_before_reading_or_downloading(
    tmp_path, monkeypatch
):
    root = tmp_path / "fixture"
    root.mkdir()
    marker = root / "valuable-file"
    marker.write_bytes(b"keep-this-state")
    monkeypatch.setattr(
        "urllib.request.urlopen", lambda *a, **k: pytest.fail("network opened")
    )
    with pytest.raises(ValueError, match="never overwrites"):
        prepare(root, tmp_path / "missing-source")
    assert list(root.iterdir()) == [marker]
    assert marker.read_bytes() == b"keep-this-state"


def test_persistent_fixture_stays_local_and_resource_bounded():
    root = Path(__file__).parents[3]
    value = yaml.safe_load(
        (root / "deploy/tui-lab/compose.yaml").read_text(encoding="utf-8")
    )
    services = value["services"]
    assert set(services) == {"alpha", "beta", "prometheus", "agent"}
    for service in services.values():
        assert service["restart"] == "unless-stopped"
        assert service["cpus"] <= 1
        assert "ALL" in service["cap_drop"]
        assert all(port.startswith("127.0.0.1:") for port in service.get("ports", []))
        assert all("docker.sock" not in mount for mount in service["volumes"])
    assert services["alpha"]["mem_limit"] == services["beta"]["mem_limit"] == "768m"
    assert services["alpha"]["volumes"][0] != services["beta"]["volumes"][0]
