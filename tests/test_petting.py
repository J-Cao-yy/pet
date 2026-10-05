"""The policy behind light interactions, pinned down without an event loop."""

from __future__ import annotations

import pytest

from betty_pet.petting import CLICK, STROKE, PettingRules, evaluate_petting

RULES = PettingRules(click_affection=1.0, stroke_affection=2.0, daily_limit=3, cooldown_s=60.0)


def test_the_first_contact_of_a_run_is_never_blocked_by_the_cooldown():
    decision = evaluate_petting(CLICK, used_today=0, seconds_since_last=None, rules=RULES)
    assert decision.granted is True
    assert decision.reason is None
    assert decision.affection == 1.0
    assert decision.daily_count == 1


def test_a_stroke_is_worth_more_than_a_poke():
    poked = evaluate_petting(CLICK, used_today=0, seconds_since_last=None, rules=RULES)
    stroked = evaluate_petting(STROKE, used_today=0, seconds_since_last=None, rules=RULES)
    assert stroked.affection == 2.0 > poked.affection == 1.0


def test_contact_within_the_cooldown_is_refused_without_spending_the_cap():
    decision = evaluate_petting(CLICK, used_today=1, seconds_since_last=30.0, rules=RULES)
    assert decision.granted is False
    assert decision.reason == "cooldown"
    assert decision.affection == 0.0
    assert decision.daily_count == 1


def test_the_cooldown_expires_exactly_on_the_limit():
    decision = evaluate_petting(CLICK, used_today=1, seconds_since_last=60.0, rules=RULES)
    assert decision.granted is True


def test_the_daily_cap_refuses_and_keeps_the_count():
    decision = evaluate_petting(STROKE, used_today=3, seconds_since_last=None, rules=RULES)
    assert decision.granted is False
    assert decision.reason == "limit"
    assert decision.daily_count == 3


def test_the_cap_still_counts_pokes_and_strokes_together():
    """One cap over both kinds: they are the same event happening too often."""
    after_two = evaluate_petting(CLICK, used_today=2, seconds_since_last=None, rules=RULES)
    assert after_two.granted is True
    assert after_two.daily_count == 3

    blocked = evaluate_petting(STROKE, used_today=3, seconds_since_last=None, rules=RULES)
    assert blocked.granted is False


def test_a_zero_limit_disables_the_whole_feature():
    off = PettingRules(daily_limit=0)
    decision = evaluate_petting(CLICK, used_today=0, seconds_since_last=None, rules=off)
    assert decision.granted is False
    assert decision.reason == "limit"


def test_the_last_grant_before_the_cap_still_goes_through():
    decision = evaluate_petting(CLICK, used_today=2, seconds_since_last=999.0, rules=RULES)
    assert decision.granted is True
    assert decision.daily_count == 3


def test_an_unknown_kind_is_a_typo_not_a_free_poke():
    with pytest.raises(ValueError):
        evaluate_petting("scratch", used_today=0, seconds_since_last=None, rules=RULES)
