"""Per-pack heap policy: leave memory for the OS, launcher and Java native allocations."""

import json
from dataclasses import dataclass
from pathlib import Path

import psutil

from launcher.files import atomic_write
from omk.shared.profiles import ServerProfile

STEP_MB = 256
MIN_MB = 1024
LOW_MEMORY_HOST_MB = 16 * 1024
MIN_SYSTEM_RESERVE_MB = 2 * 1024


@dataclass(frozen=True)
class MemorySnapshot:
    """Capture total and available physical memory for heap selection."""

    total_mb: int
    available_mb: int

    @classmethod
    def read(cls):
        """Measure the host's memory at the point of configuration."""
        memory = psutil.virtual_memory()
        return cls(memory.total // 1024**2, memory.available // 1024**2)


@dataclass(frozen=True)
class MemoryChoice:
    """Describe the selected heap, its limit and any memory warning."""

    selected_mb: int
    maximum_mb: int
    recommended_mb: int
    warning: str


def choose_memory(
    profile: ServerProfile, machine: MemorySnapshot, requested_mb: int | None = None
) -> MemoryChoice:
    """Use the saved heap or select a default within the host's memory budget."""
    reserve = max(MIN_SYSTEM_RESERVE_MB, machine.total_mb // 4 + 1024)
    recommended_room = min(
        profile.memory_recommended_mb, machine.total_mb - MIN_SYSTEM_RESERVE_MB
    )
    maximum = min(
        profile.memory_max_mb, max(0, machine.total_mb - reserve, recommended_room)
    )
    maximum = maximum // STEP_MB * STEP_MB
    default_mb = profile.memory_default_mb
    if machine.total_mb <= LOW_MEMORY_HOST_MB:
        default_mb = min(default_mb, profile.memory_recommended_mb)
    requested = requested_mb if type(requested_mb) is int else default_mb
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
    """Load and persist per-pack launcher settings beside the portable session."""

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
        """Persist one pack's heap setting while retaining all existing choices."""
        if type(value) is not int or not MIN_MB <= value <= 16384:
            raise ValueError("Invalid heap setting")
        updated = {**self.memory, pack_id: value}
        if self.path is not None:
            atomic_write(
                self.path, json.dumps({"schema": 1, "memory": updated}).encode()
            )
        self.memory = updated
