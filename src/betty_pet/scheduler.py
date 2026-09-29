"""Centralised deferred-callback scheduling.

Every timer in the app should go through a :class:`Scheduler` instead of
calling ``root.after`` directly. Doing that buys three things the previous
scattered timers could not give us:

* **Priority** - a user click can refuse to be interrupted by a random action.
* **Cancellation by group** - motion, animation and dialog timers are separate
  concerns and can be torn down independently.
* **Cooldown** - repeatable actions (feeding, playing) cannot be spammed.

Nothing here imports Tkinter. The UI injects a :class:`Clock` that knows how to
defer work, so the same scheduler can be driven by a manual clock in tests.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable, Protocol

__all__ = ["Clock", "ManualClock", "TkClock", "Scheduler", "Job"]


class Clock(Protocol):
    """Backend that can defer a callback and cancel it again."""

    def now(self) -> float:
        """Current time in seconds. Only used for cooldown comparisons."""

    def call_later(self, delay_ms: int, callback: Callable[[], None]) -> object:
        """Defer ``callback`` and return an opaque handle."""

    def cancel(self, handle: object) -> None:
        """Cancel a handle returned by :meth:`call_later`."""


@dataclass
class Job:
    """A pending timer tracked by the scheduler."""

    name: str
    callback: Callable[[], None]
    priority: int = 0
    group: str = "default"
    handle: object = None


class Scheduler:
    """Owns named timers with priority, grouping and cooldown."""

    def __init__(self, clock: Clock) -> None:
        self._clock = clock
        self._jobs: dict[str, Job] = {}
        self._cooldown_until: dict[str, float] = {}
        self._repeat_tokens: dict[str, object] = {}
        self._firing: Job | None = None

    def pending(self) -> tuple[str, ...]:
        return tuple(self._jobs)

    def is_pending(self, name: str) -> bool:
        return name in self._jobs

    def cooldown_remaining_ms(self, name: str) -> float:
        remaining = self._cooldown_until.get(name, 0.0) - self._clock.now()
        return max(0.0, remaining * 1000.0)

    def schedule(
        self,
        name: str,
        delay_ms: int,
        callback: Callable[[], None],
        *,
        priority: int = 0,
        group: str = "default",
        cooldown_ms: int = 0,
        replace: bool = True,
    ) -> bool:
        """Register a timer. Returns ``False`` when the request was refused."""
        if delay_ms < 0:
            raise ValueError("delay_ms must not be negative")
        if self.cooldown_remaining_ms(name) > 0:
            return False
        existing = self._jobs.get(name)
        if existing is not None:
            if not replace or priority < existing.priority:
                return False
            self.cancel(name)
        handle = self._clock.call_later(delay_ms, lambda: self._fire(name))
        self._jobs[name] = Job(name=name, callback=callback, priority=priority, group=group, handle=handle)
        if cooldown_ms > 0:
            self._cooldown_until[name] = self._clock.now() + cooldown_ms / 1000.0
        return True

    def repeat(
        self,
        name: str,
        interval_ms: int,
        callback: Callable[[], None],
        *,
        priority: int = 0,
        group: str = "default",
    ) -> bool:
        """Schedule a self-rescheduling timer. Cooldown is not supported here.

        The callback may cancel its own timer (``cancel(name)`` or
        ``cancel_group(group)``) and the loop will stop instead of resurrecting
        itself.
        """
        token = object()
        self._repeat_tokens[name] = token

        def loop() -> None:
            callback()
            if self._repeat_tokens.get(name) is token:
                self.schedule(name, interval_ms, loop, priority=priority, group=group)

        return self.schedule(name, interval_ms, loop, priority=priority, group=group)

    def fire(self, name: str) -> bool:
        """Run a pending timer immediately, bypassing its delay."""
        if name not in self._jobs:
            return False
        self._fire(name)
        return True

    def cancel(self, name: str) -> bool:
        self._repeat_tokens.pop(name, None)
        job = self._jobs.pop(name, None)
        if job is None:
            return False
        self._clock.cancel(job.handle)
        return True

    def cancel_group(self, group: str) -> int:
        """Cancel every pending timer in a group. Returns how many were dropped."""
        names = self._matching(lambda job: job.group == group)
        for name in names:
            self.cancel(name)
        return len(names)

    def cancel_below(self, priority: int, group: str | None = None) -> int:
        """Cancel pending timers weaker than ``priority`` (interruption rule)."""
        names = self._matching(
            lambda job: job.priority < priority and (group is None or job.group == group)
        )
        for name in names:
            self.cancel(name)
        return len(names)

    def cancel_all(self) -> int:
        names = self._matching(lambda _job: True)
        for name in names:
            self.cancel(name)
        return len(names)

    def _matching(self, predicate) -> list[str]:
        """Names of pending jobs matching ``predicate``.

        A job that is running right now has already left ``_jobs``, but the
        callback may still want to cancel itself - so it is included too.
        """
        names = [name for name, job in self._jobs.items() if predicate(job)]
        firing = self._firing
        if firing is not None and predicate(firing) and firing.name not in names:
            names.append(firing.name)
        return names

    def _fire(self, name: str) -> None:
        job = self._jobs.pop(name, None)
        if job is None:
            return
        previous, self._firing = self._firing, job
        try:
            job.callback()
        finally:
            self._firing = previous


class ManualClock:
    """Deterministic clock for tests: time only moves when you say so."""

    def __init__(self) -> None:
        self.now_ms = 0.0
        self._next_handle = 0
        self._queue: dict[int, tuple[float, Callable[[], None]]] = {}

    def now(self) -> float:
        return self.now_ms / 1000.0

    def call_later(self, delay_ms: int, callback: Callable[[], None]) -> object:
        self._next_handle += 1
        self._queue[self._next_handle] = (self.now_ms + delay_ms, callback)
        return self._next_handle

    def cancel(self, handle: object) -> None:
        self._queue.pop(handle, None)

    def advance(self, ms: float, *, limit: int = 10_000) -> int:
        """Run every callback due within ``ms``, oldest first. Returns the count."""
        target = self.now_ms + ms
        runs = 0
        while runs < limit:
            due = [(at, handle) for handle, (at, _) in self._queue.items() if at <= target]
            if not due:
                break
            at, handle = min(due)
            self.now_ms = max(self.now_ms, at)
            _deadline, callback = self._queue.pop(handle)
            callback()
            runs += 1
        self.now_ms = target
        return runs


class TkClock:
    """Clock backed by a Tk widget's ``after`` / ``after_cancel``."""

    def __init__(self, root) -> None:
        self._root = root

    def now(self) -> float:
        return time.monotonic()

    def call_later(self, delay_ms: int, callback: Callable[[], None]) -> object:
        return self._root.after(max(0, int(delay_ms)), callback)

    def cancel(self, handle: object) -> None:
        if handle is not None:
            self._root.after_cancel(handle)
