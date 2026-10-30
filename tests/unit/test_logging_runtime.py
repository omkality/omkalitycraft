import io

import pytest

from omk.logging_runtime import logging_classpath, logging_pins, stage_logging_runtime


def test_classpath_removes_all_old_log4j_versions_and_places_pinned_pair_first():
    paths = [
        "forge.jar",
        "libraries/org/apache/logging/log4j/log4j-api/2.8.1/log4j-api-2.8.1.jar",
        "libraries/org/apache/logging/log4j/log4j-core/2.15.0/log4j-core-2.15.0.jar",
        "other.jar",
    ]
    result = logging_classpath(paths)
    assert result[:2] == [a["path"] for a in logging_pins()["artifacts"]]
    assert result[2:] == ["forge.jar", "other.jar"]


def test_runtime_staging_refuses_corrupt_download_without_writing_jar(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(
        "omk.logging_runtime.urlopen", lambda *a, **kw: io.BytesIO(b"wrong artifact")
    )
    with pytest.raises(ValueError, match="artifact mismatch"):
        stage_logging_runtime(tmp_path)
    assert not list(tmp_path.rglob("*.jar"))


def test_runtime_staging_refuses_modified_existing_jar_without_network(
    tmp_path, monkeypatch
):
    artifact = logging_pins()["artifacts"][0]
    path = tmp_path / artifact["path"]
    path.parent.mkdir(parents=True)
    path.write_bytes(b"modified")
    monkeypatch.setattr(
        "omk.logging_runtime.urlopen", lambda *a, **kw: pytest.fail("network requested")
    )
    with pytest.raises(ValueError, match="artifact mismatch"):
        stage_logging_runtime(tmp_path)
    assert path.read_bytes() == b"modified"
