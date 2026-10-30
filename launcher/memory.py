"""Per-pack heap policy: leave memory for the OS, launcher and Java native allocations."""

import json
from dataclasses import dataclass
from pathlib import Path

import psutil

from launcher.files import atomic_write
from omk.profiles import ServerProfile

STEP_MB = 256
MIN_MB = 1024


@dataclass(frozen=True)
class MemorySnapshot:
    total_mb: int
    available_mb: int

    @classmethod
    def read(cls):
        memory = psutil.virtual_memory()
        return cls(memory.total // 1024**2, memory.available // 1024**2)


@dataclass(frozen=True)
class MemoryChoice:
    selected_mb: int
    maximum_mb: int
    recommended_mb: int
    warning: str


def choose_memory(
    profile: ServerProfile, machine: MemorySnapshot, requested_mb: int | None = None
) -> MemoryChoice:
    reserve = max(2048, machine.total_mb // 4 + 1024)
    maximum = min(profile.memory_max_mb, max(0, machine.total_mb - reserve))
    maximum = maximum // STEP_MB * STEP_MB
    requested = requested_mb if type(requested_mb) is int else profile.memory_default_mb
    selected = max(0, min(max(MIN_MB, requested // STEP_MB * STEP_MB), maximum))
    if maximum < MIN_MB:
        warning = "Недостаточно памяти для запуска сборки."
    elif selected < profile.memory_recommended_mb:
        warning = (
            f"Меньше рекомендуемых {profile.memory_recommended_mb / 1024:g} ГБ: "
            "сборка может тормозить или не запуститься."
        )
    elif machine.available_mb < selected + 1024:
        warning = (
            "Сейчас мало свободной памяти. Перед игрой закройте лишние приложения."
        )
    else:
        warning = ""
    return MemoryChoice(selected, maximum, profile.memory_recommended_mb, warning)


class Preferences:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path
        self.memory: dict[str, int] = {}
        if path is not None:
            try:
                with path.open("rb") as file:
                    document = json.loads(file.read(65537))
                if document.get("schema") == 1 and isinstance(
                    document.get("memory"), dict
                ):
                    self.memory = {
                        key: value
                        for key, value in document["memory"].items()
                        if isinstance(key, str)
                        and type(value) is int
                        and MIN_MB <= value <= 16384
                    }
            except OSError, ValueError, TypeError, AttributeError:
                pass

    def save_memory(self, pack_id: str, value: int) -> None:
        if type(value) is not int or not MIN_MB <= value <= 16384:
            raise ValueError("Invalid heap setting")
        updated = {**self.memory, pack_id: value}
        if self.path is not None:
            atomic_write(
                self.path, json.dumps({"schema": 1, "memory": updated}).encode()
            )
        self.memory = updated
