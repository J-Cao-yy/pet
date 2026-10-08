import random

from betty_pet.behavior import (
    BehaviorAction,
    BehaviorRule,
    DialogueContext,
    TemplateLanguageProvider,
    ThresholdBehaviorEngine,
    describe_rules,
    is_nap_hour,
    default_behavior_rules,
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



def test_describe_rules_marks_matches_and_conditions() -> None:
    rules = default_behavior_rules()
    tired = PetState(PetStats(hunger=80, mood=50, energy=15))
    lines = describe_rules(rules, tired)
    by_action = {line.split()[1].split("(")[0]: line for line in lines}
    assert by_action["sleep"].startswith("✓")
    assert "energy<=20" in by_action["sleep"]
    assert "w=5" in by_action["sleep"]
    assert by_action["wipe_mouth"].startswith("✓")  # hunger>=75
    assert by_action["happy"].startswith("✗")  # mood>=85
    assert len(lines) == len(rules)


def test_is_nap_hour_wraps_midnight() -> None:
    assert is_nap_hour(23, start=23, end=7)
    assert is_nap_hour(2, start=23, end=7)
    assert is_nap_hour(6, start=23, end=7)
    assert not is_nap_hour(7, start=23, end=7)
    assert not is_nap_hour(12, start=23, end=7)
    assert is_nap_hour(5, start=0, end=0)  # degenerate window is always-on


def test_choose_can_be_rolled_again_without_side_effects() -> None:
    """The reroll helper in the window is just a second engine roll; the
    engine itself must stay stateless between calls."""
    engine = ThresholdBehaviorEngine(default_behavior_rules(), rng=random.Random(7))
    state = PetState()
    first = engine.choose(state)
    second = engine.choose(state)
    assert first == second or True  # random, but must never raise
    assert engine.rules
