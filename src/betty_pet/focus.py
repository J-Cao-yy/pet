"""Pomodoro-style focus sessions, sat through together with the pet.

A focus session is companionship with a purpose: the pet goes quiet for a set
stretch, then celebrates when the stretch is over. It is also the **first
affection source that is not an item**, which closes a gap the roadmap called
out (好感度只由道具驱动，还没有别的来源).

One session is a focus stretch plus the break that follows it. ``rounds`` lets
a single "专注" run several of those back to back, with every Nth break a long
one - the classic pomodoro rhythm. ``rounds = 1`` (the default) is exactly the
original single-cycle behaviour, so nothing else had to change.

Pure state machine - no Tkinter, no Scheduler, no clock of its own. The window
feeds it elapsed milliseconds and reads back the phase, so the whole thing is
testable without running an event loop. ``completed_sessions`` is a lifetime
counter: the window seeds it from the save file and writes it back, because a
record that resets on restart is not a record.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta

__all__ = [
    "BREAK",
    "FOCUS",
    "IDLE",
    "FocusSummary",
    "FocusTimer",
    "format_mmss",
    "summarize_focus_events",
]

FOCUS = "focus"
BREAK = "break"
IDLE = "idle"


def format_mmss(milliseconds: int) -> str:
    """``mm:ss``, rounded up so a live timer never reads 00:00 while running."""
    seconds = (max(0, int(milliseconds)) + 999) // 1000
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


@dataclass(frozen=True)
class FocusSummary:
    """Aggregated focus statistics over the last few calendar days.

    ``per_day`` is ordered newest first and always spans exactly ``days``
    entries (zero included) - a stats view should show quiet days as 0, not
    paper over them.
    """

    today: int
    week: int
    per_day: tuple[tuple[str, int], ...]


def summarize_focus_events(
    rows,
    *,
    today: date,
    days: int = 7,
    local_tz=None,
) -> FocusSummary:
    """Count completed focus stretches per local day from event-log rows.

    ``rows`` are ``(ts, kind, detail)`` triplets as returned by
    ``recent_events``; ``ts`` is an ISO timestamp stored in **UTC**, so each
    one is converted to the local zone (``local_tz`` overrides it for tests)
    before its day is taken - otherwise a morning focus session lands on the
    previous day for UTC+8. Only ``kind == "focus"`` counts: starting a run is
    intent, finishing a stretch is the statistic. Malformed timestamps are
    skipped, never raised.
    """
    counts: dict[str, int] = {}
    for ts, kind, _detail in rows:
        if kind != "focus" or not isinstance(ts, str):
            continue
        try:
            day = datetime.fromisoformat(ts).astimezone(local_tz).date().isoformat()
        except ValueError:
            continue
        counts[day] = counts.get(day, 0) + 1
    per_day: list[tuple[str, int]] = []
    for offset in range(max(0, days)):
        day = today - timedelta(days=offset)
        n = counts.get(day.isoformat(), 0)
        per_day.append((day.isoformat(), n))
    return FocusSummary(today=per_day[0][1] if per_day else 0, week=sum(n for _, n in per_day), per_day=tuple(per_day))


@dataclass
class FocusTimer:
    """One focus run: ``rounds`` focus/break cycles, then back to normal.

    ``long_break_every`` (with a non-zero ``long_break_ms``) makes every Nth
    break of this run a long one. The cadence counts **this run's** sessions,
    not the lifetime total, so a saved ``completed_sessions`` figure never
    decides how the next run paces its breaks.
    """

    focus_ms: int = 25 * 60 * 1000
    break_ms: int = 5 * 60 * 1000
    rounds: int = 1
    long_break_ms: int = 0
    long_break_every: int = 0
    phase: str = IDLE
    elapsed_ms: int = 0
    completed_sessions: int = 0
    rounds_done: int = 0

    @property
    def active(self) -> bool:
        return self.phase != IDLE

    def rounds_remaining(self) -> int:
        """Focus stretches still to sit through in this run."""
        return max(0, self.rounds - self.rounds_done)

    def break_is_long(self) -> bool:
        """Whether the break currently being sat (or about to start) is a long one."""
        if self.long_break_every <= 0 or self.long_break_ms <= 0:
            return False
        return self.rounds_done > 0 and self.rounds_done % self.long_break_every == 0

    def duration_ms(self) -> int:
        if self.phase == FOCUS:
            return self.focus_ms
        return self.long_break_ms if self.break_is_long() else self.break_ms

    def remaining_ms(self) -> int:
        if not self.active:
            return 0
        return max(0, self.duration_ms() - self.elapsed_ms)

    def start(self) -> bool:
        """Begin a focus run. ``False`` when one is already running."""
        if self.active:
            return False
        self.phase = FOCUS
        self.elapsed_ms = 0
        self.rounds_done = 0
        return True

    def stop(self) -> None:
        self.phase = IDLE
        self.elapsed_ms = 0
        self.rounds_done = 0

    def tick(self, delta_ms: int) -> str | None:
        """Advance the timer and return the phase that **just ended**, if any.

        Transitions happen in here: finishing ``focus`` counts the session and
        rolls into ``break``; finishing ``break`` either starts the next round
        or ends the run. One tick advances at most one phase, so a long stall
        drops the overflow instead of racing through several rounds.
        """
        if not self.active or delta_ms <= 0:
            return None
        self.elapsed_ms += delta_ms
        if self.elapsed_ms < self.duration_ms():
            return None
        finished = self.phase
        self.elapsed_ms = 0
        if finished == FOCUS:
            self.completed_sessions += 1
            self.rounds_done += 1
            self.phase = BREAK
        elif self.rounds_remaining() > 0:
            self.phase = FOCUS
        else:
            self.phase = IDLE
        return finished
