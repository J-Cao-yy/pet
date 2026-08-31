"""Pet domain state and recovery effects.

This module deliberately has no Tkinter dependency so it can be used by a
future settings panel, scheduler, or local-model integration.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Protocol


def _clamp(value: float) -> float:
    return max(0.0, min(100.0, float(value)))


@dataclass
class PetStats:
    """Current needs. Hunger is inverted: a larger value means more hungry."""

    hunger: float = 20.0
    mood: float = 70.0
    energy: float = 80.0

    def clamp(self) -> "PetStats":
        self.hunger = _clamp(self.hunger)
        self.mood = _clamp(self.mood)
        self.energy = _clamp(self.energy)
        return self

    def adjust(self, *, hunger: float = 0, mood: float = 0, energy: float = 0) -> "PetStats":
        self.hunger += hunger
        self.mood += mood
        self.energy += energy
        return self.clamp()

    def decay(
        self,
        elapsed_seconds: float,
        *,
        hunger_per_minute: float = 1.0,
        mood_per_minute: float = 0.25,
        energy_per_minute: float = 0.5,
    ) -> "PetStats":
        """Advance passive needs without tying time handling to the UI."""
        minutes = max(0.0, elapsed_seconds) / 60.0
        return self.adjust(
            hunger=hunger_per_minute * minutes,
            mood=-mood_per_minute * minutes,
            energy=-energy_per_minute * minutes,
        )


@dataclass
class PetState:
    stats: PetStats = field(default_factory=PetStats)
    last_updated: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def update_elapsed(self, now: datetime | None = None) -> PetStats:
        now = now or datetime.now(timezone.utc)
        elapsed = max(0.0, (now - self.last_updated).total_seconds())
        self.stats.decay(elapsed)
        self.last_updated = now
        return self.stats


@dataclass(frozen=True)
class RecoveryResult:
    method: str
    changes: dict[str, float]
    dialogue_key: str | None = None


class RecoveryMethod(Protocol):
    """An injectable way to restore one or more pet stats."""

    name: str

    def can_use(self, state: PetState) -> bool: ...

    def apply(self, state: PetState) -> RecoveryResult: ...


@dataclass(frozen=True)
class StatRecovery:
    """Simple recovery implementation suitable for food, rest, or toys."""

    name: str
    hunger: float = 0.0
    mood: float = 0.0
    energy: float = 0.0
    dialogue_key: str | None = None

    def can_use(self, state: PetState) -> bool:
        return any((self.hunger, self.mood, self.energy))

    def apply(self, state: PetState) -> RecoveryResult:
        if not self.can_use(state):
            return RecoveryResult(self.name, {})
        before = {
            "hunger": state.stats.hunger,
            "mood": state.stats.mood,
            "energy": state.stats.energy,
        }
        state.stats.adjust(hunger=self.hunger, mood=self.mood, energy=self.energy)
        changes = {
            "hunger": state.stats.hunger - before["hunger"],
            "mood": state.stats.mood - before["mood"],
            "energy": state.stats.energy - before["energy"],
        }
        changes = {key: value for key, value in changes.items() if value}
        return RecoveryResult(self.name, changes, self.dialogue_key)
