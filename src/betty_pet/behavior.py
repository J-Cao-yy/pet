"""Threshold-based behavior selection and language extension points."""

from __future__ import annotations

from dataclasses import dataclass
import random
from typing import Protocol

from .state import PetState


@dataclass(frozen=True)
class BehaviorAction:
    """A presentation-neutral action that can map to a manifest animation."""

    name: str
    animation: str | None = None
    dialogue_key: str | None = None
    once: bool = True
    priority: int = 0

    @property
    def animation_name(self) -> str:
        return self.animation or self.name


@dataclass(frozen=True)
class BehaviorRule:
    action: BehaviorAction
    hunger_at_least: float | None = None
    hunger_at_most: float | None = None
    mood_at_least: float | None = None
    mood_at_most: float | None = None
    energy_at_least: float | None = None
    energy_at_most: float | None = None
    weight: float = 1.0

    def matches(self, state: PetState) -> bool:
        stats = state.stats
        checks = (
            self.hunger_at_least is None or stats.hunger >= self.hunger_at_least,
            self.hunger_at_most is None or stats.hunger <= self.hunger_at_most,
            self.mood_at_least is None or stats.mood >= self.mood_at_least,
            self.mood_at_most is None or stats.mood <= self.mood_at_most,
            self.energy_at_least is None or stats.energy >= self.energy_at_least,
            self.energy_at_most is None or stats.energy <= self.energy_at_most,
        )
        return all(checks) and self.weight > 0


class BehaviorEngine(Protocol):
    def choose(self, state: PetState) -> BehaviorAction: ...


class ThresholdBehaviorEngine:
    """Weighted random behavior engine driven by stat thresholds."""

    def __init__(
        self,
        rules: tuple[BehaviorRule, ...] | list[BehaviorRule],
        *,
        available_actions: set[str] | None = None,
        rng: random.Random | None = None,
    ) -> None:
        self.rules = tuple(rules)
        self.available_actions = available_actions
        self.rng = rng or random.Random()

    def choose(self, state: PetState) -> BehaviorAction:
        candidates = [
            rule
            for rule in self.rules
            if rule.matches(state)
            and (self.available_actions is None or rule.action.animation_name in self.available_actions)
        ]
        if not candidates:
            return BehaviorAction("idle", animation="idle", once=False)
        return self.rng.choices(candidates, weights=[rule.weight for rule in candidates], k=1)[0].action


def default_behavior_rules() -> tuple[BehaviorRule, ...]:
    """Starter rules; projects can replace or extend this list in config."""
    return (
        BehaviorRule(BehaviorAction("sleep", dialogue_key="sleep"), energy_at_most=20, weight=5),
        BehaviorRule(BehaviorAction("wipe_mouth", dialogue_key="hungry"), hunger_at_least=75, weight=4),
        BehaviorRule(BehaviorAction("sit", dialogue_key="tired"), energy_at_most=40, weight=2),
        BehaviorRule(BehaviorAction("happy", dialogue_key="happy"), mood_at_least=85, weight=2),
        BehaviorRule(BehaviorAction("wave", dialogue_key="greet"), mood_at_least=60, energy_at_least=50, weight=1),
    )


@dataclass(frozen=True)
class DialogueContext:
    state: PetState
    action: BehaviorAction | None = None
    recovery: str | None = None


class LanguageProvider(Protocol):
    """Language interface for templates, local LLMs, or remote providers."""

    def reply(self, context: DialogueContext) -> str | None: ...


class TemplateLanguageProvider:
    def __init__(self, templates: dict[str, tuple[str, ...]], *, rng: random.Random | None = None) -> None:
        self.templates = templates
        self.rng = rng or random.Random()

    def reply(self, context: DialogueContext) -> str | None:
        key = context.action.dialogue_key if context.action else context.recovery
        choices = self.templates.get(key or "")
        return self.rng.choice(choices) if choices else None

