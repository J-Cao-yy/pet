"""Screen-space physics for the pet window.

No Tkinter here, so motion can be unit tested. The model is deliberately
small - gravity, terminal velocity, drag, ground friction and a damped bounce -
but it covers the three physics behaviours every desktop mascot needs. Shimeji
lists exactly those three as mandatory alongside mouse chasing: ``Fall``,
``Dragged`` and ``Thrown`` (see docs/EXTERNAL_REFERENCES.md).

Units are pixels and seconds. The caller drives :func:`step` at a fixed
timestep and moves the window to the returned position.
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, replace

__all__ = [
    "Bounds",
    "DragTracker",
    "MotionEvents",
    "MotionState",
    "PhysicsConfig",
    "bounds_for",
    "clamp_to_bounds",
    "clamp_speed",
    "step",
]


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


def step(
    state: MotionState,
    dt: float,
    bounds: Bounds,
    config: PhysicsConfig,
    *,
    drive_vx: float | None = None,
) -> tuple[MotionState, MotionEvents]:
    """Advance the motion model by ``dt`` seconds.

    ``drive_vx`` is how walking is expressed: when given, horizontal velocity is
    set to it directly (a controller), otherwise velocity decays on its own.
    """
    if dt <= 0:
        return state, MotionEvents()

    vx, vy = state.vx, state.vy
    if drive_vx is not None:
        vx = drive_vx
    elif state.grounded:
        vx *= max(0.0, 1.0 - config.ground_friction * dt)
    else:
        vx *= max(0.0, 1.0 - config.air_drag * dt)

    if not state.grounded:
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

    grounded = y >= bounds.bottom - 0.05 and vy >= 0.0
    if grounded:
        y = bounds.bottom
    landed = grounded and not state.grounded
    airborne_time = 0.0 if grounded else state.airborne_time + dt

    return (
        MotionState(x=x, y=y, vx=vx, vy=vy, grounded=grounded, airborne_time=airborne_time),
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
