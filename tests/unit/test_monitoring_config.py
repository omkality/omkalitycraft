import copy
import json
import tomllib

import pytest

from omk.monitoring_config import render


@pytest.fixture
def config():
    return {
        "schema": 2,
        "host": "owner-host",
        "services": {
            "dj2": {
                "cgroup": "omk-dj2",
                "target": "dj2:19565",
                "release": "candidate-1",
                "dimension_aliases": {"-11": "2"},
            }
        },
    }


def test_standard_tools_receive_valid_data_and_actual_dimension_mapping(config):
    files = render(config, {})
    prometheus = json.loads(files["prometheus.json"])
    agent = tomllib.loads(files["telegraf.conf"])
    rules = json.loads(files["rules.json"])
    assert prometheus["storage"]["tsdb"]["retention"] == {
        "time": "180d",
        "size": "1024MB",
    }
    assert prometheus["scrape_configs"][1]["metric_relabel_configs"][-1] == {
        "source_labels": ["__name__", "id"],
        "regex": "mc_dimension_.*;-11",
        "target_label": "dimension",
        "replacement": "2",
    }
    assert prometheus["scrape_configs"][1]["metric_relabel_configs"][0] == {
        "source_labels": ["__name__"],
        "regex": "mc_dimension_chunks_loaded",
        "action": "drop",
    }
    assert (
        prometheus["scrape_configs"][1]["metric_relabel_configs"][1]["target_label"]
        == "dimension_type"
    )
    assert agent["inputs"]["cgroup"][1]["paths"] == ["/cgroups/omk-dj2"]
    assert "memory.events" in agent["inputs"]["cgroup"][1]["files"]
    assert agent["outputs"]["prometheus_client"][0]["expiration_interval"] == "90s"
    assert {r["record"] for r in rules["groups"][0]["rules"]} == {
        "omk_game_online",
        "omk_game_tps",
        "omk_game_tick_mean_ms",
        "omk_game_progress_observed",
    }
    assert "I:listen_port=19565" in files["dj2.exporter.cfg"]


def test_overrides_are_rendered_without_mutating_profile(config):
    before = copy.deepcopy(config)
    files = render(
        config,
        {
            "OMK_METRICS_INTERVAL_SECONDS": "5",
            "OMK_METRICS_RETENTION_DAYS": "7",
            "OMK_METRICS_RETENTION_MIB": "256",
        },
    )
    assert config == before
    assert json.loads(files["prometheus.json"])["global"]["scrape_interval"] == "5s"
    assert "15s" in files["rules.json"]
    assert tomllib.loads(files["telegraf.conf"])["agent"]["interval"] == "5s"


def test_non_game_service_gets_cgroup_metrics_without_fabricated_game_online(config):
    config["services"]["auth"] = {
        "cgroup": "omkauth.slice",
        "release": "configured-auth-release",
        "target": None,
        "dimension_aliases": {},
    }
    files = render(config, {})
    jobs = json.loads(files["prometheus.json"])["scrape_configs"]
    assert [job["job_name"] for job in jobs] == ["host", "dj2"]
    assert "auth.exporter.cfg" not in files
    agent = tomllib.loads(files["telegraf.conf"])
    assert agent["inputs"]["cgroup"][-1]["tags"]["service"] == "auth"


def test_legacy_collector_profile_is_not_silently_reinterpreted(config):
    config["schema"] = 1
    with pytest.raises(ValueError, match="Invalid monitoring configuration"):
        render(config, {})


@pytest.mark.parametrize("bad", ["../escape", "/root", "x/*", "x/../secret", "x\n"])
def test_cgroup_cannot_escape_or_expand_into_other_services(config, bad):
    config["services"]["dj2"]["cgroup"] = bad
    with pytest.raises(ValueError):
        render(config, {})


@pytest.mark.parametrize(
    "bad", ["user:pass@host:123", "host:0", "host:65536", "http://x:1"]
)
def test_targets_are_plain_explicit_endpoints(config, bad):
    config["services"]["dj2"]["target"] = bad
    with pytest.raises(ValueError):
        render(config, {})


@pytest.mark.parametrize(
    "source,target", [("-0", "2"), ("2", "2147483648"), ("x", "1")]
)
def test_bad_dimension_mapping_rejected(config, source, target):
    config["services"]["dj2"]["dimension_aliases"] = {source: target}
    with pytest.raises(ValueError):
        render(config, {})


@pytest.mark.parametrize("bad", ["0", "301", "no", "30\n", "999999999999"])
def test_interval_validation_does_not_echo_value(config, bad):
    with pytest.raises(
        ValueError, match="Invalid monitoring setting: INTERVAL_SECONDS"
    ):
        render(config, {"OMK_METRICS_INTERVAL_SECONDS": bad})
