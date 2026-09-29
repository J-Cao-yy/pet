"""Climbing: clinging is a different regime from standing.

The point of these tests is the thing the design draft got wrong first time
round - you cannot reach "hanging from the ceiling" by rotating the coordinate
system, because standing is pressed onto the surface by gravity while clinging
is pulled *off* it. So a clinging pet gets no gravity, and the surface pin comes
from a zero-thickness :class:`Bounds` rather than from new motion code.
"""

from __future__ import annotations

import pytest

from betty_pet.physics import (
    Bounds,
    MotionState,
    PhysicsConfig,
    Surface,
    attach,
    detach,
    step,
    surface_bounds,
)

CONFIG = PhysicsConfig()

# The rectangle a pet of some size may move its top-left corner within.
AREA = Bounds(left=0.0, top=0.0, right=500.0, bottom=1000.0)


# -- the enum itself ----------------------------------------------------------


def test_only_the_floor_counts_as_standing():
    assert Surface.FLOOR.clinging is False
    assert Surface.CEILING.clinging is True
    assert Surface.WALL_LEFT.clinging is True
    assert Surface.WALL_RIGHT.clinging is True


def test_surface_travels_along_the_right_axis():
    assert Surface.FLOOR.along == "x"
    assert Surface.CEILING.along == "x"
    assert Surface.WALL_LEFT.along == "y"
    assert Surface.WALL_RIGHT.along == "y"


def test_surface_prints_as_its_plain_value():
    # It subclasses str, so logs and JSON do not grow a "Surface." prefix.
    assert str(Surface.WALL_LEFT) == "wall_left"
    assert f"{Surface.CEILING}" == "ceiling"
    assert Surface("wall_right") is Surface.WALL_RIGHT


# -- pinning geometry ---------------------------------------------------------


def test_floor_geometry_is_left_alone():
    assert surface_bounds(AREA, Surface.FLOOR) == AREA


def test_ceiling_collapses_the_rectangle_to_a_line_at_the_top():
    pinned = surface_bounds(AREA, Surface.CEILING)
    assert pinned.top == pinned.bottom == AREA.top
    assert (pinned.left, pinned.right) == (AREA.left, AREA.right)


def test_walls_collapse_the_rectangle_to_a_vertical_line():
    left = surface_bounds(AREA, Surface.WALL_LEFT)
    right = surface_bounds(AREA, Surface.WALL_RIGHT)
    assert left.left == left.right == AREA.left
    assert right.left == right.right == AREA.right
    # The travel range along the wall is untouched either way.
    assert (left.top, left.bottom) == (AREA.top, AREA.bottom)
    assert (right.top, right.bottom) == (AREA.top, AREA.bottom)


# -- attach / detach ----------------------------------------------------------


def test_attaching_stops_the_pet_dead():
    moving = MotionState(x=10.0, y=20.0, vx=300.0, vy=-150.0, grounded=False)
    grabbed = attach(moving, Surface.WALL_LEFT)
    assert (grabbed.vx, grabbed.vy) == (0.0, 0.0)
    assert grabbed.grounded is True
    assert grabbed.surface is Surface.WALL_LEFT
    # Position is not reinterpreted - the caller re-bounds it, not attach().
    assert (grabbed.x, grabbed.y) == (10.0, 20.0)


def test_attaching_does_not_report_a_spurious_landing():
    bounds = surface_bounds(AREA, Surface.WALL_LEFT)
    grabbed = attach(MotionState(x=0.0, y=500.0), Surface.WALL_LEFT)
    _moved, events = step(grabbed, 0.016, bounds, CONFIG)
    assert events.landed is False


def test_setting_the_surface_without_attaching_does_report_a_landing():
    """Why attach() exists: a bare surface swap looks like a landing."""
    bounds = surface_bounds(AREA, Surface.WALL_LEFT)
    swapped = MotionState(x=0.0, y=500.0, grounded=False, surface=Surface.WALL_LEFT)
    _moved, events = step(swapped, 0.016, bounds, CONFIG)
    assert events.landed is True


def test_detaching_hands_the_pet_back_to_gravity():
    grabbed = attach(MotionState(x=0.0, y=300.0), Surface.WALL_LEFT)
    loose = detach(grabbed)
    assert loose.surface is Surface.FLOOR
    assert loose.grounded is False
    assert loose.airborne_time == 0.0

    fell, _events = step(loose, 0.1, AREA, CONFIG)
    assert fell.vy == pytest.approx(180.0)
    assert fell.y > 300.0


# -- clinging holds -----------------------------------------------------------


def test_a_clinging_pet_hangs_instead_of_falling():
    bounds = surface_bounds(AREA, Surface.WALL_LEFT)
    state = attach(MotionState(x=0.0, y=500.0), Surface.WALL_LEFT)
    for _ in range(60):
        state, _events = step(state, 0.016, bounds, CONFIG)
    assert state.y == pytest.approx(500.0)
    assert state.vy == 0.0
    assert state.grounded is True


def test_a_clinging_pet_counts_as_settled_so_the_loop_can_stop():
    """Otherwise the physics loop spins forever on a pet that is just holding on."""
    bounds = surface_bounds(AREA, Surface.WALL_LEFT)
    state = attach(MotionState(x=0.0, y=500.0), Surface.WALL_LEFT)
    for _ in range(5):
        state, _events = step(state, 0.016, bounds, CONFIG)
    assert state.settled() is True


def test_releasing_the_climb_stops_the_pet_instead_of_dropping_it():
    bounds = surface_bounds(AREA, Surface.WALL_LEFT)
    state = attach(MotionState(x=0.0, y=500.0), Surface.WALL_LEFT)
    state, _events = step(state, 0.1, bounds, CONFIG, drive_vy=-120.0)
    highest = state.y
    # Let go of the controls: gripping is friction, so it coasts briefly and
    # stops. It must never slide back down the wall.
    for _ in range(60):
        state, _events = step(state, 0.016, bounds, CONFIG)
    assert state.y <= highest
    assert state.vy == pytest.approx(0.0, abs=1.0)


# -- climbing a wall ----------------------------------------------------------


def test_climbing_up_moves_against_gravity_and_keeps_the_pet_on_the_wall():
    bounds = surface_bounds(AREA, Surface.WALL_LEFT)
    state = attach(MotionState(x=0.0, y=500.0), Surface.WALL_LEFT)
    for _ in range(10):
        state, _events = step(state, 0.1, bounds, CONFIG, drive_vy=-120.0)
    assert state.y == pytest.approx(380.0)
    assert state.x == 0.0  # pinned to the wall line
    assert state.vy == -120.0
    assert state.surface is Surface.WALL_LEFT


def test_climbing_down_a_wall_stops_at_the_floor_line():
    bounds = surface_bounds(AREA, Surface.WALL_LEFT)
    state = attach(MotionState(x=0.0, y=900.0), Surface.WALL_LEFT)
    state, _events = step(state, 1.0, bounds, CONFIG, drive_vy=200.0)
    assert state.y == bounds.bottom
    assert state.vy == 0.0


def test_climbing_off_the_top_reports_the_ceiling():
    """The window layer turns this event into "attach to the ceiling"."""
    bounds = surface_bounds(AREA, Surface.WALL_LEFT)
    state = attach(MotionState(x=0.0, y=40.0), Surface.WALL_LEFT)
    state, events = step(state, 1.0, bounds, CONFIG, drive_vy=-200.0)
    assert state.y == bounds.top
    assert events.ceiling is True


def test_the_right_wall_pins_to_the_other_edge():
    bounds = surface_bounds(AREA, Surface.WALL_RIGHT)
    state = attach(MotionState(x=AREA.right, y=500.0), Surface.WALL_RIGHT)
    for _ in range(10):
        state, _events = step(state, 0.1, bounds, CONFIG, drive_vy=-120.0)
    assert state.x == AREA.right
    assert state.y == pytest.approx(380.0)


# -- walking a ceiling --------------------------------------------------------


def test_walking_along_the_ceiling():
    bounds = surface_bounds(AREA, Surface.CEILING)
    state = attach(MotionState(x=100.0, y=AREA.top), Surface.CEILING)
    for _ in range(10):
        state, _events = step(state, 0.1, bounds, CONFIG, drive_vx=80.0)
    assert state.x == pytest.approx(180.0)
    assert state.y == AREA.top
    assert state.grounded is True


def test_the_ceiling_does_not_drag_the_pet_down_mid_walk():
    """No gravity on the clinging axis, even with a big dt."""
    bounds = surface_bounds(AREA, Surface.CEILING)
    state = attach(MotionState(x=0.0, y=AREA.top), Surface.CEILING)
    state, _events = step(state, 1.0, bounds, CONFIG)
    assert state.y == AREA.top
    assert state.vy == 0.0


# -- the floor still behaves --------------------------------------------------


def test_a_grounded_pet_ignores_a_zero_vertical_drive():
    state = MotionState(x=100.0, y=AREA.bottom, vx=50.0)
    moved, _events = step(state, 0.1, AREA, CONFIG, drive_vx=50.0, drive_vy=0.0)
    assert moved.y == AREA.bottom
    assert moved.grounded is True
    assert moved.x > 100.0


def test_the_floor_still_falls_and_lands_when_nothing_drives_vertically():
    state = MotionState(x=0.0, y=0.0, grounded=False)
    fell, _events = step(state, 0.5, AREA, CONFIG)
    assert fell.vy > 0
    assert fell.y > 0
    assert fell.surface is Surface.FLOOR


# -- a wall can be a band, not a line ----------------------------------------
#
# "允许墙上横向挪动" read as "the edge is a climbable strip": the pet may move
# inwards and outwards inside the strip and is only clamped at its inner edge.
# This is pure geometry - the window layer decides when a grip gives.


def test_a_zero_band_is_the_plain_wall_line():
    banded = surface_bounds(AREA, Surface.WALL_LEFT, band=0.0)
    assert banded == surface_bounds(AREA, Surface.WALL_LEFT)


def test_a_band_puts_a_floor_on_the_wall():
    left = surface_bounds(AREA, Surface.WALL_LEFT, band=60.0)
    assert (left.left, left.right) == (AREA.left, AREA.left + 60.0)
    # The band only widens the wall; the travel range along it is untouched.
    assert (left.top, left.bottom) == (AREA.top, AREA.bottom)

    right = surface_bounds(AREA, Surface.WALL_RIGHT, band=60.0)
    assert (right.left, right.right) == (AREA.right - 60.0, AREA.right)


def test_a_band_wider_than_the_screen_cannot_invert_the_rectangle():
    left = surface_bounds(AREA, Surface.WALL_LEFT, band=9999.0)
    assert (left.left, left.right) == (AREA.left, AREA.right)
    right = surface_bounds(AREA, Surface.WALL_RIGHT, band=9999.0)
    assert (right.left, right.right) == (AREA.left, AREA.right)


def test_a_negative_band_is_treated_as_no_band():
    assert surface_bounds(AREA, Surface.WALL_LEFT, band=-40.0) == surface_bounds(
        AREA, Surface.WALL_LEFT
    )


def test_the_ceiling_ignores_the_band():
    """A hanging pet has nowhere sensible to drift, so it stays a line."""
    banded = surface_bounds(AREA, Surface.CEILING, band=60.0)
    assert banded.top == banded.bottom == AREA.top


def test_the_floor_ignores_the_band():
    assert surface_bounds(AREA, Surface.FLOOR, band=60.0) == AREA


def test_a_banded_wall_lets_the_pet_roam_inwards_and_clamps_it():
    bounds = surface_bounds(AREA, Surface.WALL_LEFT, band=60.0)
    state = attach(MotionState(x=0.0, y=500.0), Surface.WALL_LEFT)

    # Lean inwards for a fifth of a second: it really moves, it is not pinned.
    state, _events = step(state, 0.2, bounds, CONFIG, drive_vx=100.0)
    assert state.x == pytest.approx(20.0)

    # Keep leaning: it stops at the inner edge instead of leaving the wall.
    state, _events = step(state, 1.0, bounds, CONFIG, drive_vx=100.0)
    assert state.x == bounds.right == AREA.left + 60.0

    # And it can hug its way back to the screen edge.
    for _ in range(10):
        state, _events = step(state, 0.1, bounds, CONFIG, drive_vx=-100.0)
    assert state.x == AREA.left


def test_a_banded_wall_still_holds_the_pet_against_gravity():
    bounds = surface_bounds(AREA, Surface.WALL_RIGHT, band=60.0)
    state = attach(MotionState(x=AREA.right - 30.0, y=500.0), Surface.WALL_RIGHT)
    for _ in range(60):
        state, _events = step(state, 0.016, bounds, CONFIG)
    assert state.y == pytest.approx(500.0)
    assert state.x == pytest.approx(AREA.right - 30.0)
    assert state.grounded is True

