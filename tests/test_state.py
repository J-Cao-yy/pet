from datetime import datetime, timedelta, timezone

from betty_pet.state import (
    AFFECTION_PER_LEVEL,
    AFFECTION_TITLES,
    PetState,
    PetStats,
    affection_level,
    affection_title,
    affection_to_next_level,
)


def test_stats_are_clamped_and_decay_over_time() -> None:
    stats = PetStats(hunger=99, mood=1, energy=1)
    stats.decay(120)
    assert stats.hunger == 100
    assert stats.mood == 0.5
    assert stats.energy == 0


def test_state_update_elapsed_uses_last_timestamp() -> None:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    state = PetState(PetStats(hunger=20), last_updated=start)
    state.update_elapsed(start + timedelta(minutes=2))
    assert state.stats.hunger == 22


def test_affection_never_decays_with_time() -> None:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    state = PetState(last_updated=start)
    state.gain_affection(120)
    state.update_elapsed(start + timedelta(days=3))
    assert state.affection == 120


def test_affection_levels_step_every_fifty_points() -> None:
    assert affection_level(0) == 0
    assert affection_level(49.9) == 0
    assert affection_level(50) == 1
    assert affection_level(249) == 4
    assert affection_level(10_000) == len(AFFECTION_TITLES) - 1


def test_affection_gain_returns_the_level_reached() -> None:
    state = PetState(affection=AFFECTION_PER_LEVEL - 2)
    assert state.gain_affection(2) == 1
    assert state.title == affection_title(1)
    assert state.gain_affection(1) == 1


def test_affection_cannot_go_negative() -> None:
    state = PetState(affection=5)
    assert state.gain_affection(-50) == 0
    assert state.affection == 0


def test_affection_to_next_level_counts_down_and_stops_at_the_top() -> None:
    assert affection_to_next_level(10) == 40
    assert affection_to_next_level(50) == 50
    top = (len(AFFECTION_TITLES) - 1) * AFFECTION_PER_LEVEL
    assert affection_to_next_level(top) == 0
    assert affection_to_next_level(top + 500) == 0
