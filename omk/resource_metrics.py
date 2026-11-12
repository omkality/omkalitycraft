"""Allowlisted Linux counters, with no Docker socket, process lists or log scraping."""

import hashlib
import math
import os
import re
import stat
from pathlib import Path, PurePosixPath
from uuid import UUID

LIMIT = 1024 * 1024
NAME = re.compile(r"[a-z][a-z0-9_-]{0,47}")


def read(path):
    path = Path(path)
    if path.resolve() != path.absolute():
        raise ValueError("Linked metric input")
    fd = os.open(
        path, os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_NOFOLLOW", 0)
    )
    with os.fdopen(fd, "rb") as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise ValueError("Metric input is not a regular kernel file")
        raw = stream.read(LIMIT + 1)
    if len(raw) > LIMIT:
        raise ValueError("Metric input exceeds bound")
    return raw.decode("ascii")


def integer(raw):
    if not re.fullmatch(r"[0-9]{1,24}", raw):
        raise ValueError("Invalid kernel counter")
    return int(raw)


def pairs(raw):
    result = {}
    for line in raw.splitlines():
        key, value = line.split()
        if key in result:
            raise ValueError("Duplicate kernel counter")
        result[key] = integer(value)
    return result


def validate_config(config):
    if (
        not isinstance(config, dict)
        or not {"schema", "host", "disks", "interfaces", "filesystems", "services"}
        <= set(config)
        or set(config)
        - {"schema", "host", "disks", "interfaces", "filesystems", "services", "games"}
        or type(config["schema"]) is not int
        or config["schema"] != 1
        or not isinstance(config["host"], str)
        or not NAME.fullmatch(config["host"])
    ):
        raise ValueError("Invalid resource history configuration")
    for key in ("disks", "interfaces"):
        values = config[key]
        if (
            not isinstance(values, list)
            or len(values) > 32
            or any(
                not isinstance(v, str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,32}", v)
                for v in values
            )
            or len(set(values)) != len(values)
        ):
            raise ValueError("Invalid device allowlist")
    for key in ("filesystems", "services"):
        values = config[key]
        if not isinstance(values, dict) or len(values) > 32:
            raise ValueError("Invalid metric source allowlist")
        for name, entry in values.items():
            if not isinstance(name, str) or not NAME.fullmatch(name):
                raise ValueError("Invalid metric source label")
            if key == "filesystems":
                if not isinstance(entry, str) or not NAME.fullmatch(entry):
                    raise ValueError("Invalid storage mount label")
                continue
            if not isinstance(entry, dict) or set(entry) != {"cgroup", "release"}:
                raise ValueError("Invalid service metrics configuration")
            relative = entry["cgroup"]
            if (
                not isinstance(relative, str)
                or len(relative) > 240
                or not relative
                or any(
                    not re.fullmatch(r"[A-Za-z0-9_.-]{1,120}", p) or p in {".", ".."}
                    for p in relative.split("/")
                )
                or PurePosixPath(relative).is_absolute()
                or not isinstance(entry["release"], str)
                or not re.fullmatch(r"[A-Za-z0-9_.+-]{1,80}", entry["release"])
            ):
                raise ValueError("Invalid service metrics configuration")
    validate_games(config.get("games", {}))
    return config


def validate_games(games):
    if not isinstance(games, dict) or len(games) > 4:
        raise ValueError("Invalid game metrics allowlist")
    for label, entry in games.items():
        if (
            not isinstance(label, str)
            or not NAME.fullmatch(label)
            or not isinstance(entry, dict)
            or set(entry) != {"mount", "profile", "core_version", "max_age_seconds"}
        ):
            raise ValueError("Invalid game metric configuration")
        if (
            not isinstance(entry["mount"], str)
            or not NAME.fullmatch(entry["mount"])
            or not isinstance(entry["profile"], str)
            or not re.fullmatch(r"[a-z0-9_.-]{1,80}", entry["profile"])
            or not isinstance(entry["core_version"], str)
            or not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", entry["core_version"])
            or type(entry["max_age_seconds"]) is not int
            or not 10 <= entry["max_age_seconds"] <= 3600
        ):
            raise ValueError("Invalid game metric configuration")


class LinuxMetrics:
    """Rates never cross host boots, source changes, resets or collector gaps."""

    def __init__(
        self,
        config,
        *,
        host=Path("/host"),
        cgroups=Path("/cgroups"),
        storage=Path("/storage"),
        max_gap=90,
    ):
        self.config = validate_config(config)
        self.host, self.cgroups, self.storage = host, cgroups, storage
        self.max_gap = max_gap
        self.previous = {}
        self.boot = None
        self.at = None

    def sample(self, monotonic):
        self.metrics, self.issues, self.sources = {}, [], {}
        boot = str(UUID(read(self.host / "boot_id").strip()))
        elapsed = None if self.at is None else monotonic - self.at
        if self.boot != boot or elapsed is None or not 0 < elapsed <= self.max_gap:
            self.previous.clear()
            elapsed = None
        self.boot, self.at, self.elapsed = boot, monotonic, elapsed
        for label, function in (
            ("host.cpu", self._cpu),
            ("host.memory", self._memory),
            ("host.vm", self._vm),
            ("disk", self._disks),
            ("net", self._network),
        ):
            self._attempt(label, function)
        for resource in ("cpu", "memory", "io"):
            self._attempt(
                "host.pressure." + resource,
                lambda resource=resource: self._pressure(resource),
            )
        for label, mount in self.config["filesystems"].items():
            self._attempt(
                "fs." + label,
                lambda label=label, mount=mount: self._filesystem(label, mount),
            )
        for label, entry in self.config["services"].items():
            self._attempt(
                "service." + label,
                lambda label=label, entry=entry: self._service(label, entry),
            )
            if label in self.sources:
                self._attempt(
                    "service." + label + ".io",
                    lambda label=label, entry=entry: self._service_io(label, entry),
                )
        return {
            "host_boot": boot,
            "interval_seconds": elapsed,
            "metrics": self.metrics,
            "issues": sorted(self.issues),
            "sources": self.sources,
        }

    def _attempt(self, label, function):
        try:
            values = function()
            self.metrics.update(values)
        except OSError, ValueError, KeyError, IndexError, OverflowError, StopIteration:
            # Fixed labels only. No paths, raw counters, env or child output.
            self.issues.append(label + ":unavailable")
            for key in list(self.previous):
                if key == label or key.startswith(label + "."):
                    del self.previous[key]

    def _rates(self, label, identity, counters, scale=1):
        before = self.previous.get(label)
        self.previous[label] = (identity, counters)
        if self.elapsed is None or before is None or identity != before[0]:
            return {}
        old = before[1]
        if set(old) != set(counters) or any(v < old[k] for k, v in counters.items()):
            return {}
        return {k: (v - old[k]) * scale / self.elapsed for k, v in counters.items()}

    def _cpu(self):
        raw = read(self.host / "stat").splitlines()
        fields = next(line for line in raw if line.startswith("cpu ")).split()[1:9]
        values = list(map(integer, fields))
        if len(values) != 8:
            raise ValueError("Incomplete CPU counters")
        delta = self._rates("host.cpu", self.boot, dict(enumerate(values)))
        result = {
            "host.cpu.logical": sum(bool(re.match(r"cpu[0-9]+ ", line)) for line in raw)
        }
        total = sum(delta.values())
        if total > 0:
            result.update(
                {
                    "host.cpu.busy_pct": sum(delta[i] for i in (0, 1, 2, 5, 6))
                    * 100
                    / total,
                    "host.cpu.iowait_pct": delta[4] * 100 / total,
                    "host.cpu.steal_pct": delta[7] * 100 / total,
                }
            )
        return result

    def _memory(self):
        values = {}
        for line in read(self.host / "meminfo").splitlines():
            key, *parts = line.split()
            if key in {"MemTotal:", "MemAvailable:", "SwapTotal:", "SwapFree:"}:
                if len(parts) != 2 or parts[1] != "kB":
                    raise ValueError("Invalid memory units")
                values[key[:-1]] = integer(parts[0]) * 1024
        return {
            "host.memory.total_bytes": values["MemTotal"],
            "host.memory.available_bytes": values["MemAvailable"],
            "host.memory.used_bytes": values["MemTotal"] - values["MemAvailable"],
            "host.swap.total_bytes": values["SwapTotal"],
            "host.swap.used_bytes": values["SwapTotal"] - values["SwapFree"],
        }

    def _vm(self):
        counters = pairs(read(self.host / "vmstat"))
        selected = {
            k: counters[k] for k in ("pswpin", "pswpout", "pgmajfault", "oom_kill")
        }
        result = {"host.vm." + k + "_total": v for k, v in selected.items()}
        result.update(
            {
                "host.vm." + k + "_per_second": v
                for k, v in self._rates("host.vm", self.boot, selected).items()
            }
        )
        return result

    def _pressure(self, resource):
        result = {}
        for line in read(self.host / ("pressure-" + resource)).splitlines():
            category, *parts = line.split()
            fields = dict(part.split("=") for part in parts)
            if category not in {"some", "full"}:
                raise ValueError("Invalid pressure category")
            value = float(fields["avg10"])
            if not math.isfinite(value) or not 0 <= value <= 100:
                raise ValueError("Invalid pressure value")
            result[f"host.pressure.{resource}.{category}_pct"] = value
        return result

    def _disks(self):
        found = {}
        for line in read(self.host / "diskstats").splitlines():
            parts = line.split()
            if len(parts) >= 14 and parts[2] in self.config["disks"]:
                found[parts[2]] = list(map(integer, parts[3:14]))
        result = {}
        for name in self.config["disks"]:
            label = "disk." + name
            if name not in found:
                self.issues.append(label + ":unavailable")
                self.previous.pop(label, None)
                continue
            fields = found[name]
            result[label + ".inflight"] = fields[8]
            counters = dict(
                zip(
                    (
                        "read_ops",
                        "read_sectors",
                        "read_ms",
                        "write_ops",
                        "write_sectors",
                        "write_ms",
                        "busy_ms",
                    ),
                    (
                        fields[0],
                        fields[2],
                        fields[3],
                        fields[4],
                        fields[6],
                        fields[7],
                        fields[9],
                    ),
                    strict=True,
                )
            )
            delta = self._rates(label, self.boot, counters)
            if delta:
                result[label + ".read_bytes_per_second"] = delta["read_sectors"] * 512
                result[label + ".write_bytes_per_second"] = delta["write_sectors"] * 512
                result[label + ".busy_pct"] = min(100, delta["busy_ms"] / 10)
                for action in ("read", "write"):
                    if delta[action + "_ops"]:
                        result[label + "." + action + "_mean_ms"] = (
                            delta[action + "_ms"] / delta[action + "_ops"]
                        )
        return result

    def _network(self):
        found = {}
        for line in read(self.host / "netdev").splitlines():
            if ":" not in line:
                continue
            name, raw = line.split(":", 1)
            if name.strip() in self.config["interfaces"]:
                fields = list(map(integer, raw.split()))
                found[name.strip()] = {
                    "rx_bytes": fields[0],
                    "tx_bytes": fields[8],
                    "rx_errors": fields[2],
                    "tx_errors": fields[10],
                    "rx_drops": fields[3],
                    "tx_drops": fields[11],
                }
        result = {}
        for name in self.config["interfaces"]:
            label = "net." + name
            if name not in found:
                self.issues.append(label + ":unavailable")
                self.previous.pop(label, None)
                continue
            result.update(
                {label + "." + k + "_total": v for k, v in found[name].items()}
            )
            result.update(
                {
                    label + "." + k + "_per_second": v
                    for k, v in self._rates(label, self.boot, found[name]).items()
                }
            )
        return result

    def _filesystem(self, label, mount):
        path = self.storage / mount
        if path.resolve() != path.absolute():
            raise ValueError("Linked storage root")
        values = os.statvfs(path)
        return {
            f"fs.{label}.total_bytes": values.f_blocks * values.f_frsize,
            f"fs.{label}.available_bytes": values.f_bavail * values.f_frsize,
            f"fs.{label}.used_bytes": (values.f_blocks - values.f_bfree)
            * values.f_frsize,
            f"fs.{label}.free_inodes": values.f_favail,
        }

    def _service(self, label, entry):
        prefix = "service." + label
        path = self.cgroups / entry["cgroup"]
        if path.resolve() != path.absolute():
            raise ValueError("Linked cgroup")
        children = []
        # One level only, bounded. Stable parent or exact leaf is supported.
        for index, child in enumerate(path.iterdir()):
            if index >= 512:
                raise ValueError("Cgroup child bound exceeded")
            if child.is_dir() and not child.is_symlink():
                children.append(child.name + ":" + str(child.stat().st_ino))
        children.sort()
        info = path.stat()
        identity = hashlib.sha256(
            (f"{info.st_dev}:{info.st_ino}:" + ",".join(children)).encode()
        ).hexdigest()
        counters = pairs(read(path / "cpu.stat"))
        events = pairs(read(path / "memory.events"))
        state = pairs(read(path / "cgroup.events"))
        current = integer(read(path / "memory.current").strip())
        swap = integer(read(path / "memory.swap.current").strip())
        result = {
            prefix + ".populated": state["populated"],
            prefix + ".memory_bytes": current,
            prefix + ".swap_bytes": swap,
        }
        memory_limit = read(path / "memory.max").strip()
        if memory_limit != "max":
            result[prefix + ".memory_limit_bytes"] = integer(memory_limit)
        selected = {
            "cpu_usec": counters["usage_usec"],
            "oom_kill": events["oom_kill"],
        }
        if "throttled_usec" in counters:
            selected["throttled_usec"] = counters["throttled_usec"]
        result[prefix + ".oom_kill_total"] = selected["oom_kill"]
        delta = self._rates(prefix, identity, selected)
        if delta:
            result[prefix + ".cpu_cores"] = delta["cpu_usec"] / 1_000_000
            if "throttled_usec" in delta:
                result[prefix + ".throttled_seconds_per_second"] = (
                    delta["throttled_usec"] / 1_000_000
                )
            result[prefix + ".oom_kills_per_second"] = delta["oom_kill"]
        self.sources[label] = identity
        return result

    def _service_io(self, label, entry):
        path = self.cgroups / entry["cgroup"] / "io.stat"
        counters = dict.fromkeys(("rbytes", "wbytes", "rios", "wios"), 0)
        for line in read(path).splitlines():
            device, *parts = line.split()
            if not re.fullmatch(r"[0-9]+:[0-9]+", device):
                raise ValueError("Invalid cgroup I/O device")
            values = dict(p.split("=") for p in parts)
            for key in counters:
                counters[key] += integer(values[key])
        prefix = "service." + label + ".io"
        result = {
            prefix + "." + key + "_total": value for key, value in counters.items()
        }
        result.update(
            {
                prefix + "." + key + "_per_second": value
                for key, value in self._rates(
                    prefix, self.sources[label], counters
                ).items()
            }
        )
        return result
