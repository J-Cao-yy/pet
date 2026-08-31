import random

from betty_pet.behavior import (
    BehaviorAction,
    BehaviorRule,
    DialogueContext,
    TemplateLanguageProvider,
    ThresholdBehaviorEngine,
)
from betty_pet.state import PetState, PetStats


def test_threshold_engine_selects_matching_action() -> None:
    engine = ThresholdBehaviorEngine(
        (BehaviorRule(BehaviorAction("sleep"), energy_at_most=20),),
        rng=random.Random(1),
    )
    assert engine.choose(PetState(PetStats(energy=10))).name == "sleep"
    assert engine.choose(PetState(PetStats(energy=80))).name == "idle"


def test_language_provider_is_replaceable_and_has_fallback() -> None:
    action = BehaviorAction("wave", dialogue_key="greet")
    provider = TemplateLanguageProvider({"greet": ("你好",)}, rng=random.Random(1))
    assert provider.reply(DialogueContext(PetState(), action=action)) == "你好"
    assert provider.reply(DialogueContext(PetState(), action=BehaviorAction("idle"))) is None

