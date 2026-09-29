import pytest

from betty_pet.physics import (
    Bounds,
    DragTracker,
    MotionState,
    PhysicsConfig,
    bounds_for,
    clamp_speed,
    clamp_to_bounds,
    step,
)

CONFIG = PhysicsConfig()
FLOOR = Bounds(left=0.0, top=0.0, right=500.0, bottom=1000.0)


def test_gravity_accelerates_a_falling_pet() -> None:
    state = MotionState(x=0.0, y=0.0, grounded=False)
    moved, events = step(state, 0.1, FLOOR, CONFIG)
    assert moved.vy == pytest.approx(180.0)
    assert moved.y == pytest.approx(18.0)
    assert events.landed is False


def test_terminal_velocity_caps_fall_speed() -> None:
    state = MotionState(x=0.0, y=0.0, vy=3000.0, grounded=False)
    moved, _events = step(state, 0.1, FLOOR, CONFIG)
    assert moved.vy == CONFIG.terminal_velocity


def test_gentle_landing_stops_the_pet_and_reports_the_event() -> None:
    state = MotionState(x=0.0, y=1000.0, vy=0.0, grounded=False)
    moved, events = step(state, 0.016, FLOOR, CONFIG)
    assert moved.y == 1000.0
    assert moved.vy == 0.0
    assert moved.grounded is True
    assert events.landed is True
    assert events.bounced is False
    assert moved.settled()


def test_fast_impact_bounces_with_damped_energy() -> None:
    impact = 600.0
    state = MotionState(x=0.0, y=1000.0, vy=impact, grounded=False)
    moved, events = step(state, 0.016, FLOOR, CONFIG)
    assert events.bounced is True
    assert events.landed is False
    assert moved.y == 1000.0
    assert moved.grounded is False
    expected = -(impact + CONFIG.gravity * 0.016) * CONFIG.bounce
    assert moved.vy == pytest.approx(expected)
    assert abs(moved.vy) < impact


def test_a_bounced_pet_loses_height_each_time() -> None:
    peaks = []
    state = MotionState(x=0.0, y=1000.0, vy=-600.0, grounded=False)
    for _ in range(400):
        state, _events = step(state, 0.016, FLOOR, CONFIG)
        if state.vy >= 0 and state.y < 1000.0:
            peaks.append(state.y)
    assert peaks, "the pet should have come off the floor at least once"
    assert state.settled()


def test_ground_friction_brings_a_sliding_pet_to_rest() -> None:
    state = MotionState(x=100.0, y=1000.0, vx=300.0)
    for _ in range(120):
        state, _events = step(state, 0.016, FLOOR, CONFIG)
    assert state.vx == pytest.approx(0.0, abs=1.0)
    assert state.x > 100.0


def test_walking_velocity_is_driven_not_accumulated() -> None:
    state = MotionState(x=100.0, y=1000.0, vx=0.0)
    state, _events = step(state, 0.1, FLOOR, CONFIG, drive_vx=150.0)
    assert state.vx == 150.0
    assert state.x == pytest.approx(115.0)


def test_walking_stops_at_the_wall_without_bouncing() -> None:
    state = MotionState(x=495.0, y=1000.0, vx=150.0)
    moved, events = step(state, 0.1, FLOOR, CONFIG, drive_vx=150.0)
    assert events.right_wall is True
    assert moved.x == 500.0
    assert moved.vx == 0.0
    assert events.bounced is False


def test_an_airborne_pet_bounces_off_a_side_wall() -> None:
    impact = 400.0
    state = MotionState(x=495.0, y=400.0, vx=impact, grounded=False)
    moved, events = step(state, 0.1, FLOOR, CONFIG)
    assert events.bounced is True
    assert events.right_wall is True
    assert moved.x == 500.0
    dragged = impact * (1.0 - CONFIG.air_drag * 0.1)
    assert moved.vx == pytest.approx(-dragged * CONFIG.bounce)


def test_clamp_speed_scales_a_vector_to_the_limit() -> None:
    vx, vy = clamp_speed(3000.0, 4000.0, 2400.0)
    assert (vx, vy) == pytest.approx((1440.0, 1920.0))
    assert clamp_speed(10.0, 0.0, 2400.0) == (10.0, 0.0)


def test_bounds_reserve_room_for_the_taskbar() -> None:
    box = bounds_for(1920, 1080, 128, 128, floor_offset=48)
    assert (box.right, box.bottom) == (1792.0, 904.0)


def test_clamp_to_bounds_pulls_a_resized_pet_back_in() -> None:
    state = MotionState(x=900.0, y=1200.0)
    clamped = clamp_to_bounds(state, FLOOR)
    assert (clamped.x, clamped.y) == (500.0, 1000.0)


def test_drag_tracker_turns_a_flick_into_a_throw() -> None:
    tracker = DragTracker()
    tracker.add(0.0, 0, 0)
    tracker.add(0.05, 50, 10)
    tracker.add(0.10, 100, 20)
    assert tracker.release_velocity(0.10, CONFIG) == pytest.approx((1000.0, 200.0))


def test_drag_tracker_ignores_a_slow_drag() -> None:
    tracker = DragTracker()
    tracker.add(0.0, 0, 0)
    tracker.add(0.5, 10, 0)
    assert tracker.release_velocity(0.5, CONFIG) == (0.0, 0.0)


def test_drag_tracker_reports_a_slow_but_recent_drag_as_small() -> None:
    tracker = DragTracker()
    tracker.add(0.40, 0, 0)
    tracker.add(0.45, 2, 0)
    tracker.add(0.50, 4, 0)
    vx, vy = tracker.release_velocity(0.50, CONFIG)
    assert 0.0 < vx < CONFIG.throw_threshold
    assert vy == 0.0


def test_drag_tracker_respects_the_throw_speed_cap() -> None:
    tracker = DragTracker()
    tracker.add(0.0, 0, 0)
    tracker.add(0.01, 500, 500)
    vx, vy = tracker.release_velocity(0.01, CONFIG)
    assert abs(vx) <= CONFIG.max_throw_speed
    assert abs(vy) <= CONFIG.max_throw_speed


def test_drag_tracker_clear_drops_history() -> None:
    tracker = DragTracker()
    tracker.add(0.0, 0, 0)
    tracker.add(0.05, 100, 0)
    tracker.clear()
    assert tracker.samples == ()
    assert tracker.release_velocity(0.05, CONFIG) == (0.0, 0.0)
