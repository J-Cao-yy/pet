"""Screen-space physics for the pet window.

No Tkinter here, so motion can be unit tested. The model is deliberately
small - gravity, terminal velocity, drag, ground friction and a damped bounce -
but it covers the three physics behaviours every desktop mascot needs. Shimeji
lists exactly those three as mandatory alongside mouse chasing: ``Fall``,
``Dragged`` and ``Thrown`` (see docs/EXTERNAL_REFERENCES.md).

Units are pixels and seconds. The caller drives :func:`step` at a fixed
timestep and moves the window to the returned position.

Standing and clinging are *not* the same physics. On the floor gravity presses
the pet into the surface; on a ceiling or a wall gravity pulls it away and only
its grip holds it there. So a clinging pet (:class:`Surface`) gets no gravity
and is pinned to the surface by a zero-thickness :class:`Bounds` rather than by
a rotation of the coordinate system. See docs/CLIMBING_DESIGN.md.
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, replace
from enum import Enum

__all__ = [
    "Bounds",
    "DragTracker",
    "MotionEvents",
    "MotionState",
    "PhysicsConfig",
    "Surface",
    "attach",
    "bounds_for",
    "clamp_to_bounds",
    "clamp_speed",
    "detach",
    "step",
    "surface_bounds",
]


class Surface(str, Enum):
    """The surface the pet is currently held by.

    ``FLOOR`` is the default and the only one where gravity is helpful: it
    presses the pet onto the surface. Everywhere else gravity pulls the pet
    *off* the surface, so a clinging pet gets no gravity at all - what keeps it
    there is its grip, not the physics.
    """

    FLOOR = "floor"
    CEILING = "ceiling"
    WALL_LEFT = "wall_left"
    WALL_RIGHT = "wall_right"

    def __str__(self) -> str:
        return self.value

    @property
    def clinging(self) -> bool:
        """True when the pet is holding on rather than standing on something."""
        return self is not Surface.FLOOR

    @property
    def along(self) -> str:
        """Axis the pet travels along the surface: ``"x"`` or ``"y"``."""
        return "y" if self in (Surface.WALL_LEFT, Surface.WALL_RIGHT) else "x"


@dataclass(frozen=True)
class PhysicsConfig:
    """Tunables for the motion model."""

    gravity: float = 1800.0
    terminal_velocity: float = 1600.0
    air_drag: float = 0.6
    ground_friction: float = 6.0
    bounce: float = 0.45
    min_bounce_velocity: float = 260.0
    max_throw_speed: float = 2400.0
    throw_threshold: float = 180.0


@dataclass(frozen=True)
class Bounds:
    """Movement rectangle in screen coordinates, already accounting for size."""

    left: float = 0.0
    top: float = 0.0
    right: float = 0.0
    bottom: float = 0.0

    @property
    def width(self) -> float:
        return self.right - self.left

    @property
    def height(self) -> float:
        return self.bottom - self.top


@dataclass
class MotionState:
    """Position and velocity of the pet window."""

    x: float = 0.0
    y: float = 0.0
    vx: float = 0.0
    vy: float = 0.0
    grounded: bool = True
    airborne_time: float = 0.0
    surface: Surface = Surface.FLOOR

    def settled(self) -> bool:
        """True when nothing more will happen without external input."""
        return self.grounded and abs(self.vx) < 1.0 and abs(self.vy) < 1.0

    def speed(self) -> float:
        return math.hypot(self.vx, self.vy)


@dataclass(frozen=True)
class MotionEvents:
    """What happened during one step, so the UI can react."""

    landed: bool = False
    bounced: bool = False
    left_wall: bool = False
    right_wall: bool = False
    ceiling: bool = False

    @property
    def hit_wall(self) -> bool:
        return self.left_wall or self.right_wall


def bounds_for(
    screen_width: int,
    screen_height: int,
    pet_width: int,
    pet_height: int,
    floor_offset: int = 0,
) -> Bounds:
    """Build the movement rectangle for a pet of the given size.

    ``floor_offset`` reserves room for the taskbar: Tkinter cannot report its
    height, so it is configured explicitly in :class:`AppConfig`.
    """
    return Bounds(
        left=0.0,
        top=0.0,
        right=float(max(0, screen_width - pet_width)),
        bottom=float(max(0, screen_height - pet_height - floor_offset)),
    )


def clamp_to_bounds(state: MotionState, bounds: Bounds) -> MotionState:
    """Pull a state back inside the rectangle, e.g. after the pet is resized."""
    return replace(
        state,
        x=min(max(state.x, bounds.left), bounds.right),
        y=min(max(state.y, bounds.top), bounds.bottom),
    )


def clamp_speed(vx: float, vy: float, limit: float) -> tuple[float, float]:
    """Scale a velocity vector down so its magnitude never exceeds ``limit``."""
    magnitude = math.hypot(vx, vy)
    if magnitude <= limit or magnitude == 0:
        return vx, vy
    scale = limit / magnitude
    return vx * scale, vy * scale


def surface_bounds(area: Bounds, surface: Surface, *, band: float = 0.0) -> Bounds:
    """Collapse ``area`` onto ``surface`` so a clinging pet is pinned to it.

    No new motion code is needed to hold a pet against a surface: :func:`step`
    already snaps a state onto ``bounds.bottom`` and refuses to let it out of
    the rectangle. Making the rectangle zero-thickness turns that into "pinned
    to a line, free to slide along it":

    * ceiling  -> zero height (pin ``y``)
    * walls    -> zero width  (pin ``x``)

    ``band`` thickens a wall into a **climbable strip** instead of a line: the
    pet may move ``band`` pixels inwards and is only clamped at the strip's
    inner edge. That is the difference between "the wall is a line" and "the
    wall is a band you can shuffle around on" - see
    ``docs/CLIMBING_DESIGN.md`` §7. The ceiling stays a line: walking it means
    moving *along* it, and a hanging pet has nowhere sensible to drift.

    ``FLOOR`` is returned untouched - standing is what ``area`` already means.
    """
    if surface is Surface.CEILING:
        return replace(area, bottom=area.top)
    if surface is Surface.WALL_LEFT:
        return replace(area, right=min(area.left + max(0.0, band), area.right))
    if surface is Surface.WALL_RIGHT:
        return replace(area, left=max(area.right - max(0.0, band), area.left))
    return area


def attach(state: MotionState, surface: Surface) -> MotionState:
    """Cling to ``surface``: stop dead and hand the geometry to the caller.

    Both velocities are dropped because grabbing a surface is a new grip, not a
    continuation of whatever the pet was doing. ``grounded`` is set so the first
    :func:`step` does not report a spurious landing.
    """
    return replace(state, vx=0.0, vy=0.0, grounded=True, surface=surface)


def detach(state: MotionState) -> MotionState:
    """Let go: normal gravity takes over again."""
    return replace(state, grounded=False, surface=Surface.FLOOR, airborne_time=0.0)


def step(
    state: MotionState,
    dt: float,
    bounds: Bounds,
    config: PhysicsConfig,
    *,
    drive_vx: float | None = None,
    drive_vy: float | None = None,
) -> tuple[MotionState, MotionEvents]:
    """Advance the motion model by ``dt`` seconds.

    ``drive_vx`` / ``drive_vy`` are how walking and climbing are expressed: when
    given, that axis' velocity is set to it directly (a controller), otherwise
    it decays on its own. ``drive_vy`` is what lets a pet climb *up* a wall -
    on the floor it is normally left as ``None`` and gravity owns the axis.

    A clinging state (``state.surface``) is held by the surface instead of by
    gravity, so gravity is skipped and the pet counts as supported.
    """
    if dt <= 0:
        return state, MotionEvents()

    clinging = state.surface.clinging

    vx, vy = state.vx, state.vy
    if drive_vx is not None:
        vx = drive_vx
    elif state.grounded:
        vx *= max(0.0, 1.0 - config.ground_friction * dt)
    else:
        vx *= max(0.0, 1.0 - config.air_drag * dt)

    if drive_vy is not None:
        vy = drive_vy
    elif clinging:
        # Gripping a surface is friction, not free fall: letting go of the
        # controls stops the pet where it is instead of dropping it.
        vy *= max(0.0, 1.0 - config.ground_friction * dt)
    elif not state.grounded:
        vy = min(state.vy + config.gravity * dt, config.terminal_velocity)

    x = state.x + vx * dt
    y = state.y + vy * dt

    landed = bounced = left_wall = right_wall = ceiling = False

    if x < bounds.left:
        x, left_wall = bounds.left, True
    elif x > bounds.right:
        x, right_wall = bounds.right, True
    if left_wall or right_wall:
        if not state.grounded and abs(vx) > config.min_bounce_velocity:
            vx, bounced = -vx * config.bounce, True
        else:
            vx = 0.0

    if y <= bounds.top:
        y, ceiling = bounds.top, True
        vy = -vy * config.bounce if abs(vy) > config.min_bounce_velocity else 0.0
    elif y >= bounds.bottom:
        y = bounds.bottom
        if vy > config.min_bounce_velocity and not state.grounded:
            vy, bounced = -vy * config.bounce, True
        else:
            vy = 0.0

    if clinging:
        # The surface's degenerate bounds already pin the pet; do *not* snap it
        # onto ``bottom`` here, or a pet halfway up a wall would teleport to the
        # floor. It is supported by definition, which also stops the physics
        # loop from spinning while it just hangs there.
        grounded = True
    else:
        grounded = y >= bounds.bottom - 0.05 and vy >= 0.0
        if grounded:
            y = bounds.bottom
    landed = grounded and not state.grounded
    airborne_time = 0.0 if grounded else state.airborne_time + dt

    return (
        MotionState(
            x=x,
            y=y,
            vx=vx,
            vy=vy,
            grounded=grounded,
            airborne_time=airborne_time,
            surface=state.surface,
        ),
        MotionEvents(
            landed=landed,
            bounced=bounced,
            left_wall=left_wall,
            right_wall=right_wall,
            ceiling=ceiling,
        ),
    )


class DragTracker:
    """Turns a drag gesture into a throw.

    Only the last ``history_seconds`` of cursor samples count, so a long, slow
    drag releases at rest while a short flick becomes a throw.
    """

    def __init__(self, history_seconds: float = 0.12) -> None:
        self.history_seconds = history_seconds
        self._samples: deque[tuple[float, float, float]] = deque()

    def clear(self) -> None:
        self._samples.clear()

    def add(self, now: float, x: float, y: float) -> None:
        self._samples.append((float(now), float(x), float(y)))
        cutoff = now - 1.0
        while self._samples and self._samples[0][0] < cutoff:
            self._samples.popleft()

    @property
    def samples(self) -> tuple[tuple[float, float, float], ...]:
        return tuple(self._samples)

    def release_velocity(self, now: float, config: PhysicsConfig) -> tuple[float, float]:
        recent = [sample for sample in self._samples if now - sample[0] <= self.history_seconds]
        if len(recent) < 2:
            return 0.0, 0.0
        t0, x0, y0 = recent[0]
        t1, x1, y1 = recent[-1]
        elapsed = t1 - t0
        if elapsed <= 0:
            return 0.0, 0.0
        return clamp_speed((x1 - x0) / elapsed, (y1 - y0) / elapsed, config.max_throw_speed)
