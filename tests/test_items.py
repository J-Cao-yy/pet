from betty_pet.items import REFUSAL_FULL, REFUSAL_LIMIT, Item, apply_item, default_items, items_by_group
from betty_pet.state import PetState, PetStats

ITEMS = default_items()


def test_feeding_reduces_hunger_and_grants_affection() -> None:
    state = PetState(PetStats(hunger=80.0, mood=50.0, energy=40.0))
    outcome = apply_item(ITEMS["fish"], state)
    assert outcome.applied is True
    assert outcome.changes == {"hunger": -35.0, "mood": 6.0}
    assert outcome.affection_gain == 2
    assert (state.stats.hunger, state.stats.mood) == (45.0, 56.0)
    assert state.affection == 2


def test_a_full_pet_refuses_food() -> None:
    state = PetState(PetStats(hunger=20.0))
    outcome = apply_item(ITEMS["cookie"], state)
    assert outcome.applied is False
    assert outcome.refusal == REFUSAL_FULL
    assert outcome.changes == {}
    assert state.affection == 0


def test_a_full_pet_still_accepts_play_and_rest() -> None:
    state = PetState(PetStats(hunger=5.0, energy=10.0))
    assert apply_item(ITEMS["yarn"], state).applied is True
    assert apply_item(ITEMS["nap"], state).applied is True


def test_a_partly_fed_pet_still_accepts_food() -> None:
    state = PetState(PetStats(hunger=20.1))
    assert apply_item(ITEMS["cookie"], state).applied is True


def test_daily_limit_stops_further_use() -> None:
    state = PetState(PetStats(hunger=90.0))
    limit = ITEMS["fish"].daily_limit
    assert limit == 3
    outcome = apply_item(ITEMS["fish"], state, used_today=limit)
    assert outcome.applied is False
    assert outcome.refusal == REFUSAL_LIMIT
    assert state.stats.hunger == 90.0


def test_being_full_is_checked_before_the_daily_limit() -> None:
    state = PetState(PetStats(hunger=10.0))
    assert apply_item(ITEMS["fish"], state, used_today=99).refusal == REFUSAL_FULL


def test_crossing_a_threshold_reports_a_level_up() -> None:
    state = PetState(PetStats(hunger=90.0), affection=49.0)
    outcome = apply_item(ITEMS["fish"], state)
    assert outcome.level_before == 0
    assert outcome.level_after == 1
    assert outcome.levelled_up is True


def test_staying_inside_a_level_is_not_a_level_up() -> None:
    state = PetState(PetStats(hunger=90.0), affection=10.0)
    outcome = apply_item(ITEMS["cookie"], state)
    assert outcome.affection_gain == 1
    assert outcome.levelled_up is False


def test_energy_costing_items_can_make_the_pet_tired() -> None:
    state = PetState(PetStats(energy=5.0))
    outcome = apply_item(ITEMS["yarn"], state)
    assert outcome.changes["energy"] < 0
    assert state.stats.energy == 0.0


def test_items_without_limits_are_free_to_use() -> None:
    free = Item("treat", "零嘴", "feed", mood=5)
    assert free.daily_limit is None
    assert free.full_at is None
    assert free.refusal(PetState(PetStats(hunger=0.0)), used_today=999) is None


def test_groups_keep_declaration_order() -> None:
    grouped = items_by_group(ITEMS)
    assert tuple(grouped) == ("feed", "play", "rest")
    assert [item.id for item in grouped["feed"]] == ["cookie", "fish", "tea"]


def test_every_default_item_is_named_and_narrated() -> None:
    for item_id, item in ITEMS.items():
        assert item.id == item_id
        assert item.name
        assert item.group in {"feed", "play", "rest"}
        assert item.dialogue_key
        assert item.deltas, f"{item_id} does nothing"
