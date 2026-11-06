from pathlib import Path

import pytest

from omk.cli import main
from omk.territory_policy import (
    FIELDS,
    POLICY_FILE,
    territory_plan,
    write_territory_policy,
)


def test_exclusive_policy_and_environment_override(tmp_path):
    environment = {
        "OMK_DJ2_TERRITORIES_PER_MEMBER": "6",
        "OMK_DJ2_CLAIM_REQUEST_CHUNKS": "64",
    }
    plan = write_territory_policy(tmp_path, environment)
    assert plan == {
        "schema": 1,
        "regions_per_member": 6,
        "max_request_chunks": 64,
        "max_graph_chunks": 20000,
    }
    original = (tmp_path / POLICY_FILE).read_bytes()
    with pytest.raises(FileExistsError):
        write_territory_policy(tmp_path, {})
    assert (tmp_path / POLICY_FILE).read_bytes() == original


@pytest.mark.parametrize("key", FIELDS)
@pytest.mark.parametrize("bad", ["", "-1", "0", "1000000", " 3", "3.0", None])
def test_invalid_environment_does_not_write(tmp_path, key, bad):
    with pytest.raises(ValueError):
        write_territory_policy(tmp_path, {key: bad})
    assert not (tmp_path / POLICY_FILE).exists()


def test_graph_bound_minimum():
    with pytest.raises(ValueError):
        territory_plan({"OMK_DJ2_TERRITORY_GRAPH_CHUNKS": "49"})


def test_linked_directory_rejected(tmp_path):
    actual = tmp_path / "actual"
    actual.mkdir()
    link = tmp_path / "link"
    try:
        link.symlink_to(actual, target_is_directory=True)
    except OSError:
        pytest.skip("Symlink creation unavailable")
    with pytest.raises(ValueError):
        write_territory_policy(link, {})
    assert not (actual / POLICY_FILE).exists()


def test_policy_cli_plan_is_readonly(monkeypatch, capsys, tmp_path):
    for name in FIELDS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.chdir(tmp_path)
    assert main(["policy", "dj2-territories"]) == 0
    assert '"regions_per_member": 3' in capsys.readouterr().out
    assert list(tmp_path.iterdir()) == []


def test_policy_cli_writes_only_new_file(monkeypatch, capsys, tmp_path):
    for name in FIELDS:
        monkeypatch.delenv(name, raising=False)
    assert main(["policy", "dj2-territories", "--config-directory", str(tmp_path)]) == 0
    assert Path(tmp_path / POLICY_FILE).is_file()
    assert '"exclusive_create": true' in capsys.readouterr().out
