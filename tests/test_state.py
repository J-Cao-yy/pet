from datetime import datetime, timedelta, timezone

from betty_pet.state import PetState, PetStats, StatRecovery


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


def test_recovery_changes_only_declared_stats() -> None:
    state = PetState(PetStats(hunger=80, mood=30, energy=40))
    result = StatRecovery("cookie", hunger=-20, mood=10, dialogue_key="eat").apply(state)
    assert result.changes == {"hunger": -20, "mood": 10}
    assert (state.stats.hunger, state.stats.mood, state.stats.energy) == (60, 40, 40)

