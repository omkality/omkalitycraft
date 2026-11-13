"""Operational Log4j settings must not change trust pins or unrelated packs."""

import os
import xml.etree.ElementTree as ET

import pytest

from launcher.log_policy import FORGE_112, forge_log_settings, prepare_logging
from omk.profiles import PROJECT_ROOT


def test_process_environment_changes_only_rolling_limits(monkeypatch, tmp_path):
    monkeypatch.setenv("OMK_FORGE_LOG_MIB", "1")
    monkeypatch.setenv("OMK_FORGE_LOG_FILES", "2")
    path = prepare_logging("1.12.2", tmp_path / "logging")
    tree = ET.fromstring(path.read_text(encoding="utf-8"))
    file = tree.find("Appenders/RollingRandomAccessFile")
    assert file.find("Policies/SizeBasedTriggeringPolicy").get("size") == "1MB"
    assert file.find("DefaultRolloverStrategy").get("max") == "2"


def test_defaults_are_byte_compatible_and_do_not_rewrite_unchanged_config(tmp_path):
    folder = tmp_path / "logging"
    path = prepare_logging("1.12.2", folder, environment={})
    assert path.read_text(encoding="utf-8") == FORGE_112
    before = path.stat().st_mtime_ns
    assert prepare_logging("1.12.2", folder, environment={}) == path
    assert path.stat().st_mtime_ns == before


@pytest.mark.parametrize(
    "settings",
    [
        {"OMK_FORGE_LOG_MIB": "1", "OMK_FORGE_LOG_FILES": "1"},
        {"OMK_FORGE_LOG_MIB": "64", "OMK_FORGE_LOG_FILES": "10"},
    ],
)
def test_valid_overrides_keep_paths_filters_level_and_charset(tmp_path, settings):
    path = prepare_logging("1.12.2", tmp_path / "logging", environment=settings)
    text = path.read_text(encoding="utf-8")
    baseline = ET.fromstring(FORGE_112)
    tree = ET.fromstring(text)
    file = tree.find("Appenders/RollingRandomAccessFile")
    assert file.get("fileName") == "logs/latest.log"
    assert file.get("filePattern") == "logs/latest-%i.log.gz"
    assert tree.find("Loggers/Root").get("level") == "info"
    assert file.find("PatternLayout").get("charset") == "UTF-8"
    assert ET.tostring(tree.find("Loggers")) == ET.tostring(baseline.find("Loggers"))
    assert (
        file.find("Policies/SizeBasedTriggeringPolicy").get("size")
        == settings["OMK_FORGE_LOG_MIB"] + "MB"
    )
    assert (
        file.find("DefaultRolloverStrategy").get("max")
        == settings["OMK_FORGE_LOG_FILES"]
    )


@pytest.mark.parametrize(
    "name,bad",
    [
        ("OMK_FORGE_LOG_MIB", "0"),
        ("OMK_FORGE_LOG_MIB", "65"),
        ("OMK_FORGE_LOG_MIB", "-1"),
        ("OMK_FORGE_LOG_MIB", "1.5"),
        ("OMK_FORGE_LOG_MIB", " 2"),
        ("OMK_FORGE_LOG_MIB", "2\n"),
        ("OMK_FORGE_LOG_MIB", "２"),
        ("OMK_FORGE_LOG_MIB", None),
        ("OMK_FORGE_LOG_MIB", "secret<xml>"),
        ("OMK_FORGE_LOG_FILES", "0"),
        ("OMK_FORGE_LOG_FILES", "11"),
    ],
)
def test_bad_values_reject_before_filesystem_changes_without_echoing_input(
    tmp_path, name, bad
):
    folder = tmp_path / "logging"
    with pytest.raises(ValueError, match="Invalid " + name) as caught:
        prepare_logging("1.12.2", folder, environment={name: bad})
    assert "secret<xml>" not in str(caught.value)
    assert not folder.exists()


def test_invalid_override_preserves_existing_configuration(tmp_path):
    folder = tmp_path / "logging"
    path = prepare_logging("1.12.2", folder, environment={})
    before = path.read_bytes(), path.stat().st_mtime_ns
    with pytest.raises(ValueError):
        prepare_logging("1.12.2", folder, environment={"OMK_FORGE_LOG_MIB": "invalid"})
    assert (path.read_bytes(), path.stat().st_mtime_ns) == before


def test_unrelated_version_keeps_its_declared_logging_even_with_invalid_env(tmp_path):
    assert (
        prepare_logging(
            "1.7.10", tmp_path / "logging", environment={"OMK_FORGE_LOG_MIB": "invalid"}
        )
        is None
    )
    assert not (tmp_path / "logging").exists()


def test_linked_logging_folder_is_rejected(tmp_path):
    if os.name == "nt":
        pytest.skip("Linux symlink acceptance")
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    link.symlink_to(real, target_is_directory=True)
    with pytest.raises(OSError):
        prepare_logging("1.12.2", link, environment={})
    assert list(real.iterdir()) == []


def test_env_example_matches_the_consumed_defaults():
    text = (PROJECT_ROOT / "deploy/forge-logging.example.env").read_text(
        encoding="utf-8"
    )
    values = dict(
        line.split("=", 1)
        for line in text.splitlines()
        if line.startswith("OMK_FORGE_LOG_")
    )
    assert len(values) == 2 and forge_log_settings(values) == forge_log_settings({})
