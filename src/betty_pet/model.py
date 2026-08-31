from __future__ import annotations

from dataclasses import dataclass
import random


@dataclass(frozen=True)
class Action:
    name: str
    once: bool = True


class PetModel:
    """UI-independent state machine for the current action and frame."""

    def __init__(self, actions: tuple[str, ...], rng: random.Random | None = None) -> None:
        self.actions = actions
        self.rng = rng or random.Random()
        self.current = Action("idle", once=False)
        self.frame_index = 0

    def set_action(self, name: str, *, once: bool = True) -> Action:
        if name not in self.actions:
            name = "idle"
        self.current = Action(name, once=once)
        self.frame_index = 0
        return self.current

    def next_frame(self, frame_count: int) -> int:
        if frame_count <= 1:
            return 0
        if self.frame_index >= frame_count - 1:
            if self.current.once:
                return self.frame_index
            self.frame_index = 0
            return 0
        self.frame_index += 1
        return self.frame_index

    def random_action(self) -> Action:
        candidates = [name for name in self.actions if name not in {"idle", "click"}]
        return self.set_action(self.rng.choice(candidates or ["idle"]))

