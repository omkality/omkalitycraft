"""Render configuration for standard monitoring tools; no collector or database."""

import json
import os
import re
from pathlib import Path


def setting(env, key, default, minimum, maximum):
    value = env.get("OMK_METRICS_" + key, str(default))
    if (
        not isinstance(value, str)
        or not re.fullmatch(r"[0-9]{1,7}", value)
        or not minimum <= int(value) <= maximum
    ):
        raise ValueError("Invalid monitoring setting: " + key)
    return int(value)


def render(config, environment=None):
    env = os.environ if environment is None else environment
    interval = setting(env, "INTERVAL_SECONDS", 30, 5, 300)
    days = setting(env, "RETENTION_DAYS", 180, 1, 730)
    mib = setting(env, "RETENTION_MIB", 1024, 256, 65536)
    expiry = interval * 3
    name = r"[a-z][a-z0-9_-]{0,47}"
    if (
        not isinstance(config, dict)
        or set(config) != {"schema", "host", "services"}
        or type(config["schema"]) is not int
        or config["schema"] != 2
        or not isinstance(config["host"], str)
        or not re.fullmatch(name, config["host"])
        or not isinstance(config["services"], dict)
        or not 1 <= len(config["services"]) <= 16
    ):
        raise ValueError("Invalid monitoring configuration")
    q = json.dumps  # JSON strings are also valid TOML basic strings.
    agent = [
        "[agent]",
        f'  interval="{interval}s"',
        f'  flush_interval="{interval}s"',
        "  omit_hostname=true",
        "  metric_batch_size=1000",
        "  metric_buffer_limit=10000",
        "[global_tags]",
        "  host=" + q(config["host"]),
        "[[inputs.cpu]]",
        "  percpu=false",
        "  totalcpu=true",
        "  collect_cpu_time=true",
        "[[inputs.mem]]",
        "[[inputs.swap]]",
        "[[inputs.kernel_vmstat]]",
        "[[inputs.diskio]]",
        "[[inputs.net]]",
        "[[inputs.disk]]",
        '  mount_points=["/storage/project"]',
        '  ignore_fs=["tmpfs","devtmpfs","proc","sysfs"]',
        "[[inputs.cgroup]]",
        '  name_override="pressure"',
        '  paths=["/host/proc/pressure"]',
        '  files=["cpu","memory","io"]',
    ]
    jobs = [{"job_name": "host", "static_configs": [{"targets": ["agent:9273"]}]}]
    exporters = {}
    for service, entry in config["services"].items():
        if (
            not isinstance(service, str)
            or not re.fullmatch(name, service)
            or service == "host"
            or not isinstance(entry, dict)
            or set(entry) != {"cgroup", "target", "release", "dimension_aliases"}
            or any(not isinstance(entry[k], str) for k in ("cgroup", "release"))
            or not re.fullmatch(
                r"[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+){0,7}", entry["cgroup"]
            )
            or any(p in {".", ".."} for p in entry["cgroup"].split("/"))
            or (
                entry["target"] is not None
                and (
                    not isinstance(entry["target"], str)
                    or not re.fullmatch(r"[A-Za-z0-9_.-]+:[0-9]{1,5}", entry["target"])
                    or not 1 <= int(entry["target"].rsplit(":", 1)[1]) <= 65535
                )
            )
            or (entry["target"] is None and entry["dimension_aliases"])
            or not re.fullmatch(r"[A-Za-z0-9_.+-]{1,100}", entry["release"])
            or not isinstance(entry["dimension_aliases"], dict)
            or len(entry["dimension_aliases"]) > 64
        ):
            raise ValueError("Invalid monitoring service")
        relabel = [
            {
                "source_labels": ["__name__"],
                "regex": "mc_dimension_chunks_loaded",
                "action": "drop",
            },
            {
                "source_labels": ["__name__", "id"],
                "regex": "mc_dimension_.*;(-?[0-9]+)",
                "target_label": "dimension_type",
                "replacement": "$1",
            },
        ]
        for source, target in entry["dimension_aliases"].items():
            if any(
                not isinstance(v, str)
                or not re.fullmatch(r"-?(0|[1-9][0-9]{0,9})", v)
                or not -(2**31) <= int(v) < 2**31
                or v == "-0"
                for v in (source, target)
            ):
                raise ValueError("Invalid dimension alias")
            relabel.append(
                {
                    "source_labels": ["__name__", "id"],
                    "regex": "mc_dimension_.*;" + source,
                    "target_label": "dimension",
                    "replacement": target,
                }
            )
        if entry["target"] is not None:
            jobs.append(
                {
                    "job_name": service,
                    "static_configs": [
                        {
                            "targets": [entry["target"]],
                            "labels": {
                                "service": service,
                                "host": config["host"],
                                "release": entry["release"],
                            },
                        }
                    ],
                    "metric_relabel_configs": relabel,
                    "sample_limit": 20000,
                    "body_size_limit": "2MB",
                }
            )
        agent += [
            "[[inputs.cgroup]]",
            "  paths=" + q(["/cgroups/" + entry["cgroup"]]),
            '  files=["cpu.stat","memory.current","memory.events","cgroup.events","io.stat"]',
            "  [inputs.cgroup.tags]",
            "    service=" + q(service),
            "    release=" + q(entry["release"]),
        ]
        if entry["target"] is not None:
            port = int(entry["target"].rsplit(":", 1)[1])
            exporters[service + ".exporter.cfg"] = (
                "collector {\n    B:jvm=true\n    B:mc=true\n}\n"
                "web {\n    S:listen_address=0.0.0.0\n"
                f"    I:listen_port={port}\n}}\n"
            )
    agent += [
        "[[outputs.prometheus_client]]",
        '  listen=":9273"',
        "  metric_version=2",
        f'  expiration_interval="{expiry}s"',
        '  path="/metrics"',
        "  export_timestamp=false",
        "  string_as_label=false",
    ]
    live = " and on(job,instance) (up == 1)"
    rules = {
        "groups": [
            {
                "name": "omk-game",
                "rules": [
                    {
                        "record": "omk_game_online",
                        "expr": '(sum without(id,name) (mc_player_list) or (up{job!="host"} * 0))'
                        + live,
                    },
                    {
                        "record": "omk_game_tps",
                        "expr": f"clamp_max(rate(mc_server_tick_seconds_count[{expiry}s]),20)"
                        + live,
                    },
                    {
                        "record": "omk_game_tick_mean_ms",
                        "expr": f"1000 * rate(mc_server_tick_seconds_sum[{expiry}s]) / "
                        f"rate(mc_server_tick_seconds_count[{expiry}s])" + live,
                    },
                    {
                        "record": "omk_game_progress_observed",
                        "expr": f"(changes(mc_server_tick_seconds_count[{expiry}s]) > bool 0)"
                        + live,
                    },
                ],
            }
        ]
    }
    prometheus = {
        "global": {
            "scrape_interval": f"{interval}s",
            "evaluation_interval": f"{interval}s",
        },
        "storage": {"tsdb": {"retention": {"time": f"{days}d", "size": f"{mib}MB"}}},
        "rule_files": ["/etc/omk-metrics/rules.json"],
        "scrape_configs": jobs,
    }
    return {
        "prometheus.json": json.dumps(prometheus, indent=2) + "\n",
        "rules.json": json.dumps(rules, indent=2) + "\n",
        "telegraf.conf": "\n".join(agent) + "\n",
        **exporters,
    }


def main():
    try:
        raw = Path("/run/metrics/config.json").read_bytes()
        if len(raw) > 16384:
            raise ValueError("Configuration exceeds bound")
        files = render(json.loads(raw))
        output = Path("/etc/omk-metrics")
        for name, value in files.items():
            pending = output / (name + ".pending")
            pending.write_text(value, encoding="utf-8", newline="\n")
            pending.replace(output / name)
    except ValueError, TypeError, KeyError, OSError:
        raise SystemExit("Monitoring configuration rejected") from None


if __name__ == "__main__":
    main()
