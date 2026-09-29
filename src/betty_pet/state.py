"""Pet domain state: needs, affection and their passive decay.

This module deliberately has no Tkinter dependency so it can be used by a
future settings panel, scheduler, or local-model integration. Anything that
*acts* on the state (items, dialogue) lives in :mod:`betty_pet.items`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


def _clamp(value: float) -> float:
    return max(0.0, min(100.0, float(value)))


AFFECTION_PER_LEVEL = 50.0

AFFECTION_TITLES: tuple[str, ...] = ("陌生", "熟悉", "朋友", "好友", "亲密", "挚友")


def affection_level(affection: float) -> int:
    """Zero-based level index for an affection value, capped at the last title."""
    return max(0, min(len(AFFECTION_TITLES) - 1, int(max(0.0, affection) // AFFECTION_PER_LEVEL)))


def affection_title(level: int) -> str:
    return AFFECTION_TITLES[max(0, min(len(AFFECTION_TITLES) - 1, level))]


def affection_to_next_level(affection: float) -> float:
    """How many more points until the next title, or 0 at the top level."""
    level = affection_level(affection)
    if level >= len(AFFECTION_TITLES) - 1:
        return 0.0
    return (level + 1) * AFFECTION_PER_LEVEL - max(0.0, affection)


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
    """Needs plus the accumulated relationship, which never decays."""

    stats: PetStats = field(default_factory=PetStats)
    affection: float = 0.0
    last_updated: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def update_elapsed(self, now: datetime | None = None) -> PetStats:
        now = now or datetime.now(timezone.utc)
        elapsed = max(0.0, (now - self.last_updated).total_seconds())
        self.stats.decay(elapsed)
        self.last_updated = now
        return self.stats

    def gain_affection(self, amount: float) -> int:
        """Add affection and return the level index reached."""
        if amount:
            self.affection = max(0.0, self.affection + amount)
        return affection_level(self.affection)

    @property
    def level(self) -> int:
        return affection_level(self.affection)

    @property
    def title(self) -> str:
        return affection_title(self.level)
