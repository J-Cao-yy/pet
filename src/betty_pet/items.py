"""Items the pet can be given, and the rules for actually using them.

The three recovery effects that used to be hardcoded in the window are now a
declarative table (:func:`default_items`). The point is not variety for its own
sake - it is that an item can now *refuse* to work. Being told "I'm full" is
what makes the pet feel like it has a body instead of a button panel.

There is deliberately no currency and no stock count. Without an earning loop
(item -> work -> money -> item) a count is just a number that runs out and
never refills, which reads as a bug rather than as a mechanic. When an earning
loop exists, add a ``count`` field here and let :class:`Inventory` own it.
"""

from __future__ import annotations

from dataclasses import dataclass

from .state import PetState

__all__ = ["Item", "ItemOutcome", "apply_item", "default_items", "items_by_group"]

REFUSAL_FULL = "full"
REFUSAL_LIMIT = "limit"

GROUP_LABELS: dict[str, str] = {"feed": "喂食", "play": "玩耍", "rest": "休息"}


@dataclass(frozen=True)
class Item:
    """One thing the pet can be given.

    ``hunger`` is inverted (larger means hungrier), so food passes a negative
    delta. ``full_at`` is the hunger value at or below which the pet refuses
    the item: ``full_at=20`` means "only eat when more than 20 hungry".
    """

    id: str
    name: str
    group: str
    hunger: float = 0.0
    mood: float = 0.0
    energy: float = 0.0
    affection: float = 0.0
    dialogue_key: str | None = None
    animation: str | None = None
    cooldown_ms: int = 4_000
    daily_limit: int | None = None
    full_at: float | None = None

    @property
    def deltas(self) -> dict[str, float]:
        values = {"hunger": self.hunger, "mood": self.mood, "energy": self.energy}
        return {key: value for key, value in values.items() if value}

    def refusal(self, state: PetState, used_today: int) -> str | None:
        """Why the pet will not accept this item right now, if it won't."""
        if self.full_at is not None and state.stats.hunger <= self.full_at:
            return REFUSAL_FULL
        if self.daily_limit is not None and used_today >= self.daily_limit:
            return REFUSAL_LIMIT
        return None


@dataclass(frozen=True)
class ItemOutcome:
    """What actually happened, so the UI can narrate it."""

    item_id: str
    applied: bool
    changes: dict[str, float]
    affection_gain: float = 0.0
    dialogue_key: str | None = None
    refusal: str | None = None
    level_before: int = 0
    level_after: int = 0

    @property
    def levelled_up(self) -> bool:
        return self.applied and self.level_after > self.level_before


def apply_item(item: Item, state: PetState, used_today: int = 0) -> ItemOutcome:
    """Apply an item unless the pet refuses it.

    Callers are responsible for recording the daily usage afterwards; this
    function only decides and mutates stats.
    """
    refusal = item.refusal(state, used_today)
    if refusal is not None:
        return ItemOutcome(item.id, False, {}, dialogue_key=item.dialogue_key, refusal=refusal)

    before = {"hunger": state.stats.hunger, "mood": state.stats.mood, "energy": state.stats.energy}
    state.stats.adjust(hunger=item.hunger, mood=item.mood, energy=item.energy)
    changes = {
        key: getattr(state.stats, key) - value for key, value in before.items()
    }
    changes = {key: value for key, value in changes.items() if value}

    level_before = state.level
    level_after = state.gain_affection(item.affection)
    return ItemOutcome(
        item_id=item.id,
        applied=True,
        changes=changes,
        affection_gain=item.affection,
        dialogue_key=item.dialogue_key,
        level_before=level_before,
        level_after=level_after,
    )


def default_items() -> dict[str, Item]:
    return {
        "cookie": Item(
            "cookie", "饼干", "feed",
            hunger=-18, mood=3, affection=1,
            dialogue_key="eat_cookie", animation="wipe_mouth",
            daily_limit=6, full_at=20,
        ),
        "fish": Item(
            "fish", "小鱼干", "feed",
            hunger=-35, mood=6, affection=2,
            dialogue_key="eat_fish", animation="happy",
            daily_limit=3, full_at=20,
        ),
        "tea": Item(
            "tea", "热茶", "feed",
            hunger=-10, energy=10, mood=3, affection=1,
            dialogue_key="drink_tea", animation="wave",
            daily_limit=5, full_at=10,
        ),
        "yarn": Item(
            "yarn", "毛线球", "play",
            mood=16, energy=-8, affection=2,
            dialogue_key="play_yarn", animation="happy",
            daily_limit=4,
        ),
        "feather": Item(
            "feather", "逗猫棒", "play",
            mood=12, energy=-5, affection=3,
            dialogue_key="play_feather", animation="wave",
            daily_limit=5,
        ),
        "nap": Item(
            "nap", "打个盹", "rest",
            energy=35, mood=2, affection=1,
            dialogue_key="nap", animation="sleep",
            cooldown_ms=8_000, daily_limit=3,
        ),
    }


def items_by_group(items: dict[str, Item]) -> dict[str, tuple[Item, ...]]:
    """Group items for menu construction, preserving declaration order."""
    grouped: dict[str, list[Item]] = {}
    for item in items.values():
        grouped.setdefault(item.group, []).append(item)
    return {group: tuple(members) for group, members in grouped.items()}
