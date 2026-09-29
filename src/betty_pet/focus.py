"""Pomodoro-style focus sessions, sat through together with the pet.

A focus session is companionship with a purpose: the pet goes quiet for a set
stretch, then celebrates when the stretch is over. It is also the **first
affection source that is not an item**, which closes a gap the roadmap called
out (好感度只由道具驱动，还没有别的来源).

Pure state machine - no Tkinter, no Scheduler, no clock of its own. The window
feeds it elapsed milliseconds and reads back the phase, so the whole thing is
testable without running an event loop.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["BREAK", "FOCUS", "IDLE", "FocusTimer", "format_mmss"]

FOCUS = "focus"
BREAK = "break"
IDLE = "idle"


def format_mmss(milliseconds: int) -> str:
    """``mm:ss``, rounded up so a live timer never reads 00:00 while running."""
    seconds = (max(0, int(milliseconds)) + 999) // 1000
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


@dataclass
class FocusTimer:
    """One focus/break cycle. ``focus`` rolls into ``break`` automatically."""

    focus_ms: int = 25 * 60 * 1000
    break_ms: int = 5 * 60 * 1000
    phase: str = IDLE
    elapsed_ms: int = 0
    completed_sessions: int = 0

    @property
    def active(self) -> bool:
        return self.phase != IDLE

    def duration_ms(self) -> int:
        return self.focus_ms if self.phase == FOCUS else self.break_ms

    def remaining_ms(self) -> int:
        if not self.active:
            return 0
        return max(0, self.duration_ms() - self.elapsed_ms)

    def start(self) -> bool:
        """Begin a focus stretch. ``False`` when one is already running."""
        if self.active:
            return False
        self.phase = FOCUS
        self.elapsed_ms = 0
        return True

    def stop(self) -> None:
        self.phase = IDLE
        self.elapsed_ms = 0

    def tick(self, delta_ms: int) -> str | None:
        """Advance the timer and return the phase that **just ended**, if any.

        Transitions happen in here: finishing ``focus`` rolls straight into
        ``break`` and counts the session; finishing ``break`` ends the cycle.
        """
        if not self.active or delta_ms <= 0:
            return None
        self.elapsed_ms += delta_ms
        if self.elapsed_ms < self.duration_ms():
            return None
        finished = self.phase
        if finished == FOCUS:
            self.phase = BREAK
            self.elapsed_ms = 0
            self.completed_sessions += 1
        else:
            self.phase = IDLE
            self.elapsed_ms = 0
        return finished
