from betty_pet.scheduler import ManualClock, Scheduler


def test_job_fires_after_its_delay() -> None:
    clock, scheduler, runs = ManualClock(), None, []
    scheduler = Scheduler(clock)
    scheduler.schedule("later", 100, lambda: runs.append("later"))
    assert clock.advance(99) == 0
    assert runs == []
    assert clock.advance(1) == 1
    assert runs == ["later"]


def test_cancel_removes_a_pending_job() -> None:
    scheduler = Scheduler(ManualClock())
    scheduler.schedule("later", 100, lambda: None)
    assert scheduler.is_pending("later")
    assert scheduler.cancel("later") is True
    assert scheduler.pending() == ()


def test_cancel_group_only_drops_that_group() -> None:
    scheduler = Scheduler(ManualClock())
    scheduler.schedule("step", 10, lambda: None, group="motion")
    scheduler.schedule("tick", 10, lambda: None, group="animation")
    assert scheduler.cancel_group("motion") == 1
    assert scheduler.pending() == ("tick",)


def test_weaker_job_cannot_replace_a_stronger_pending_one() -> None:
    clock, runs = ManualClock(), []
    scheduler = Scheduler(clock)
    scheduler.schedule("action", 100, lambda: runs.append("strong"), priority=5)
    assert scheduler.schedule("action", 10, lambda: runs.append("weak"), priority=1) is False
    clock.advance(100)
    assert runs == ["strong"]


def test_cancel_below_interrupts_weaker_jobs() -> None:
    scheduler = Scheduler(ManualClock())
    scheduler.schedule("idle", 10, lambda: None, priority=0, group="action")
    scheduler.schedule("click", 10, lambda: None, priority=5, group="action")
    assert scheduler.cancel_below(5) == 1
    assert scheduler.pending() == ("click",)


def test_cooldown_blocks_immediate_reschedule() -> None:
    clock, runs = ManualClock(), []
    scheduler = Scheduler(clock)
    scheduler.schedule("feed", 10, lambda: runs.append("feed"), cooldown_ms=5_000)
    clock.advance(10)
    assert runs == ["feed"]
    assert scheduler.schedule("feed", 10, lambda: runs.append("feed"), cooldown_ms=5_000) is False
    clock.advance(5_000)
    assert scheduler.schedule("feed", 10, lambda: runs.append("feed"), cooldown_ms=5_000) is True


def test_repeat_keeps_rescheduling_itself() -> None:
    clock, runs = ManualClock(), []
    scheduler = Scheduler(clock)
    scheduler.repeat("tick", 100, lambda: runs.append("tick"))
    assert clock.advance(350) == 3
    assert runs == ["tick", "tick", "tick"]
    assert scheduler.is_pending("tick")


def test_repeat_stops_when_its_own_callback_cancels_it() -> None:
    clock, runs = ManualClock(), []
    scheduler = Scheduler(clock)

    def tick() -> None:
        runs.append("tick")
        scheduler.cancel_group("loop")

    scheduler.repeat("tick", 100, tick, group="loop")
    assert clock.advance(500) == 1
    assert runs == ["tick"]
    assert scheduler.pending() == ()


def test_fire_runs_a_job_before_its_delay() -> None:
    scheduler, runs = Scheduler(ManualClock()), []
    scheduler.schedule("later", 1_000, lambda: runs.append("now"))
    assert scheduler.fire("later") is True
    assert runs == ["now"]
    assert scheduler.pending() == ()
