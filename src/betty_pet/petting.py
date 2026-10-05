"""Light interactions: a poke or a stroke earns a little affection.

Affection used to come only from items, then from sitting through a focus
session. Both are deliberate acts reached through a menu, while the everyday
contact of poking the cat earned nothing - that is the gap this closes.

It is also by far the easiest affection source to farm, so the whole thing is
gated twice: a cooldown between grants and a shared daily cap over both kinds.
:func:`evaluate_petting` holds the entire policy and is pure, so tests can pin
it without an event loop; the window only applies the verdict.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["CLICK", "DAILY_KEY", "STROKE", "KINDS", "PettingDecision", "PettingRules", "evaluate_petting"]

CLICK = "click"
STROKE = "stroke"
KINDS = (CLICK, STROKE)

#: ``daily_usage`` key the two kinds share. One cap, because to the cat being
#: poked and being stroked are the same event happening too often.
DAILY_KEY = "pet_affection"


@dataclass(frozen=True)
class PettingRules:
    """Tuning knobs: how much each kind gives, and how hard it is to farm."""

    click_affection: float = 1.0
    stroke_affection: float = 2.0
    daily_limit: int = 10
    cooldown_s: float = 60.0

    def affection_for(self, kind: str) -> float:
        if kind not in KINDS:
            raise ValueError(f"unknown petting kind: {kind!r}")
        return self.stroke_affection if kind == STROKE else self.click_affection


@dataclass(frozen=True)
class PettingDecision:
    """The verdict for one interaction, ready for the window to apply."""

    kind: str
    granted: bool
    #: ``None`` when granted, else why it was refused.
    reason: str | None
    #: 0.0 unless granted.
    affection: float
    #: Daily count *after* a grant, or the unchanged count when refused.
    daily_count: int


def evaluate_petting(
    kind: str,
    *,
    used_today: int,
    seconds_since_last: float | None,
    rules: PettingRules = PettingRules(),
) -> PettingDecision:
    """Decide whether this poke or stroke is worth affection right now.

    ``seconds_since_last`` is ``None`` when the pet has not been touched in
    this run - the cooldown must never block the very first contact of a run.
    A ``daily_limit`` of zero disables the feature entirely, which is a switch
    rather than a special case.
    """
    rules.affection_for(kind)  # fail loudly on a typo instead of silently paying click rates
    if used_today >= rules.daily_limit:
        return PettingDecision(kind, False, "limit", 0.0, used_today)
    if seconds_since_last is not None and seconds_since_last < rules.cooldown_s:
        return PettingDecision(kind, False, "cooldown", 0.0, used_today)
    return PettingDecision(kind, True, None, rules.affection_for(kind), used_today + 1)
