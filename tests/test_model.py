import random

from betty_pet.model import PetModel


def test_unknown_action_falls_back_to_idle() -> None:
    model = PetModel(("idle", "click"))
    assert model.set_action("unknown").name == "idle"


def test_looping_and_one_shot_frames() -> None:
    model = PetModel(("idle", "wave"))
    model.set_action("idle", once=False)
    assert [model.next_frame(2) for _ in range(3)] == [1, 0, 1]
    model.set_action("wave")
    assert [model.next_frame(2) for _ in range(3)] == [1, 1, 1]


def test_random_action_excludes_click_and_idle() -> None:
    model = PetModel(("idle", "click", "wave"), random.Random(1))
    assert model.random_action().name == "wave"

