"""Window movement planning primitives.

The planner is UI-independent so future falling, teleporting, and window
collision behaviors can reuse the same motion descriptions.
"""

from __future__ import annotations

from dataclasses import dataclass
import random
from typing import Literal


Direction = Literal["left", "right"]


@dataclass(frozen=True)
class MovementPlan:
    direction: Direction
    distance: int
    speed_px: int = 6
    interval_ms: int = 40
    wall_action: str = "climb"


class MovementPlanner:
    """Creates bounded horizontal movement plans for behavior actions."""

    def __init__(
        self,
        distance_range: tuple[int, int] = (80, 240),
        *,
        speed_px: int = 6,
        interval_ms: int = 40,
        rng: random.Random | None = None,
    ) -> None:
        minimum, maximum = distance_range
        if minimum < 0 or maximum < minimum:
            raise ValueError("distance_range must be non-negative and ordered")
        if speed_px <= 0 or interval_ms <= 0:
            raise ValueError("speed_px and interval_ms must be positive")
        self.distance_range = (minimum, maximum)
        self.speed_px = speed_px
        self.interval_ms = interval_ms
        self.rng = rng or random.Random()

    def plan(self, direction: Direction) -> MovementPlan:
        if direction not in ("left", "right"):
            raise ValueError(f"unsupported direction: {direction}")
        return MovementPlan(
            direction=direction,
            distance=self.rng.randint(*self.distance_range),
            speed_px=self.speed_px,
            interval_ms=self.interval_ms,
        )


def horizontal_target(
    current_x: int,
    window_width: int,
    screen_width: int,
    plan: MovementPlan,
) -> tuple[int, bool]:
    """Return the clamped target x and whether the requested move hits a wall."""
    sign = -1 if plan.direction == "left" else 1
    requested = current_x + sign * plan.distance
    maximum_x = max(0, screen_width - window_width)
    target = max(0, min(maximum_x, requested))
    return target, target != requested


def chase_direction(
    actor_center: float,
    target_center: float,
    *,
    deadzone: float = 24.0,
) -> Direction | None:
    """Which way to walk to close the gap, or ``None`` when close enough.

    The deadzone is what stops a chasing pet from jittering left and right when
    the cursor sits right on top of it. Shimeji and Oneko both behave this way.
    """
    delta = target_center - actor_center
    if abs(delta) <= deadzone:
        return None
    return "right" if delta > 0 else "left"

