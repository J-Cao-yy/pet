import random

from betty_pet.movement import MovementPlan, MovementPlanner, horizontal_target


def test_planner_generates_reproducible_random_distance() -> None:
    planner = MovementPlanner((10, 20), rng=random.Random(1))
    assert planner.plan("right").distance == 12


def test_horizontal_target_clamps_to_walls() -> None:
    plan = MovementPlan("left", distance=50)
    assert horizontal_target(20, 100, 500, plan) == (0, True)
    plan = MovementPlan("right", distance=50)
    assert horizontal_target(350, 100, 500, plan) == (400, False)

