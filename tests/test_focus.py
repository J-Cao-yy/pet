"""Focus sessions: a pure state machine, so it is tested without a window."""

from __future__ import annotations

import pytest

from betty_pet.focus import (
    BREAK,
    FOCUS,
    IDLE,
    FocusTimer,
    format_mmss,
    summarize_focus_events,
)


# -- format_mmss --------------------------------------------------------------


@pytest.mark.parametrize(
    "milliseconds, expected",
    [
        (0, "00:00"),
        (1, "00:01"),  # rounds up: a live timer never shows 00:00 while running
        (999, "00:01"),
        (1_000, "00:01"),
        (59_999, "01:00"),
        (60_000, "01:00"),
        (25 * 60_000, "25:00"),
        (90 * 60_000, "90:00"),  # no hour rollover, minutes just keep counting
    ],
)
def test_format_mmss(milliseconds, expected):
    assert format_mmss(milliseconds) == expected


def test_format_mmss_clamps_negative():
    assert format_mmss(-5_000) == "00:00"


# -- lifecycle ----------------------------------------------------------------


def test_starts_idle():
    timer = FocusTimer()
    assert timer.phase == IDLE
    assert not timer.active
    assert timer.remaining_ms() == 0
    assert timer.completed_sessions == 0


def test_start_begins_focus_and_refuses_a_second_start():
    timer = FocusTimer(focus_ms=60_000)
    assert timer.start() is True
    assert timer.phase == FOCUS
    assert timer.active
    assert timer.remaining_ms() == 60_000
    assert timer.start() is False  # already running
    assert timer.phase == FOCUS


def test_stop_ends_early_without_counting():
    timer = FocusTimer(focus_ms=60_000)
    timer.start()
    timer.tick(30_000)
    timer.stop()
    assert timer.phase == IDLE
    assert not timer.active
    assert timer.completed_sessions == 0  # an abandoned stretch is worth nothing
    assert timer.remaining_ms() == 0


# -- ticking ------------------------------------------------------------------


def test_tick_while_idle_does_nothing():
    timer = FocusTimer()
    assert timer.tick(999_999) is None
    assert timer.phase == IDLE


def test_tick_ignores_non_positive_delta():
    timer = FocusTimer(focus_ms=60_000)
    timer.start()
    assert timer.tick(0) is None
    assert timer.tick(-100) is None
    assert timer.elapsed_ms == 0
    assert timer.phase == FOCUS


def test_partial_tick_counts_down_without_transitioning():
    timer = FocusTimer(focus_ms=60_000)
    timer.start()
    assert timer.tick(20_000) is None
    assert timer.phase == FOCUS
    assert timer.remaining_ms() == 40_000


def test_finishing_focus_rolls_into_break_and_counts_the_session():
    timer = FocusTimer(focus_ms=60_000, break_ms=10_000)
    timer.start()
    assert timer.tick(60_000) == FOCUS
    assert timer.phase == BREAK
    assert timer.active
    assert timer.completed_sessions == 1
    assert timer.remaining_ms() == 10_000


def test_finishing_break_ends_the_cycle():
    timer = FocusTimer(focus_ms=60_000, break_ms=10_000)
    timer.start()
    timer.tick(60_000)
    assert timer.tick(10_000) == BREAK
    assert timer.phase == IDLE
    assert not timer.active
    assert timer.completed_sessions == 1


def test_one_tick_advances_at_most_one_phase():
    """A long stall (sleep, drag) drops the overflow rather than racing ahead."""
    timer = FocusTimer(focus_ms=60_000, break_ms=10_000)
    timer.start()
    # 10x the whole cycle in a single delta: still only focus -> break.
    assert timer.tick(1_000_000) == FOCUS
    assert timer.phase == BREAK
    assert timer.completed_sessions == 1


def test_durations_follow_the_active_phase():
    timer = FocusTimer(focus_ms=60_000, break_ms=10_000)
    timer.start()
    assert timer.duration_ms() == 60_000
    timer.tick(60_000)
    assert timer.duration_ms() == 10_000


def test_second_session_counts_again():
    timer = FocusTimer(focus_ms=60_000, break_ms=10_000)
    timer.start()
    timer.tick(60_000)  # focus -> break
    timer.tick(10_000)  # break -> idle
    assert timer.start() is True
    timer.tick(60_000)
    assert timer.completed_sessions == 2


# -- several rounds ------------------------------------------------------------


def test_rounds_default_to_the_original_single_cycle():
    timer = FocusTimer(focus_ms=60_000, break_ms=10_000)
    assert timer.rounds == 1
    timer.start()
    assert timer.tick(60_000) == FOCUS
    assert timer.tick(10_000) == BREAK
    assert timer.phase == IDLE


def test_two_rounds_run_two_cycles_then_stop():
    timer = FocusTimer(focus_ms=60_000, break_ms=10_000, rounds=2)
    timer.start()
    assert timer.tick(60_000) == FOCUS  # round 1 focus
    assert timer.tick(10_000) == BREAK  # round 1 break rolls into round 2
    assert timer.phase == FOCUS
    assert timer.tick(60_000) == FOCUS  # round 2 focus
    assert timer.tick(10_000) == BREAK  # round 2 break
    assert timer.phase == IDLE
    assert not timer.active
    assert timer.completed_sessions == 2


def test_the_final_break_still_happens():
    """A round is a focus *plus* its break, including the last one."""
    timer = FocusTimer(focus_ms=60_000, break_ms=10_000, rounds=2)
    timer.start()
    timer.tick(60_000)
    timer.tick(10_000)
    timer.tick(60_000)
    assert timer.phase == BREAK
    assert timer.rounds_remaining() == 0
    assert timer.remaining_ms() == 10_000


def test_rounds_remaining_counts_down():
    timer = FocusTimer(focus_ms=60_000, break_ms=10_000, rounds=3)
    timer.start()
    assert timer.rounds_remaining() == 3
    timer.tick(60_000)
    assert timer.rounds_remaining() == 2


def test_start_resets_the_round_counter():
    timer = FocusTimer(focus_ms=60_000, break_ms=10_000, rounds=2)
    timer.start()
    timer.tick(60_000)
    assert timer.rounds_done == 1
    timer.tick(10_000)
    timer.tick(60_000)
    timer.stop()
    assert timer.rounds_done == 0
    timer.start()
    assert timer.rounds_done == 0
    assert timer.rounds_remaining() == 2


def test_one_tick_still_advances_at_most_one_phase_across_rounds():
    timer = FocusTimer(focus_ms=60_000, break_ms=10_000, rounds=3)
    timer.start()
    assert timer.tick(10_000_000) == FOCUS
    assert timer.phase == BREAK
    assert timer.completed_sessions == 1


# -- long breaks ---------------------------------------------------------------


def test_every_nth_break_is_a_long_one():
    timer = FocusTimer(
        focus_ms=60_000, break_ms=10_000, rounds=3, long_break_ms=30_000, long_break_every=2
    )
    timer.start()
    timer.tick(60_000)
    assert timer.break_is_long() is False  # after the 1st session
    assert timer.duration_ms() == 10_000

    timer.tick(10_000)
    timer.tick(60_000)
    assert timer.break_is_long() is True  # after the 2nd session
    assert timer.duration_ms() == 30_000
    assert timer.remaining_ms() == 30_000

    timer.tick(30_000)
    timer.tick(60_000)
    assert timer.break_is_long() is False  # after the 3rd session
    assert timer.duration_ms() == 10_000


def test_long_break_cadence_counts_this_run_not_the_lifetime_total():
    """A saved record must not decide how the next run paces its breaks."""
    timer = FocusTimer(
        focus_ms=60_000, break_ms=10_000, rounds=2, long_break_ms=30_000, long_break_every=2,
        completed_sessions=4,  # survived a restart
    )
    timer.start()
    timer.tick(60_000)
    assert timer.break_is_long() is False
    assert timer.duration_ms() == 10_000


def test_long_breaks_can_be_disabled():
    timer = FocusTimer(focus_ms=60_000, break_ms=10_000, long_break_ms=30_000, long_break_every=0)
    timer.start()
    timer.tick(60_000)
    assert timer.break_is_long() is False
    assert timer.duration_ms() == 10_000


def test_a_long_break_without_a_duration_is_also_disabled():
    timer = FocusTimer(focus_ms=60_000, break_ms=10_000, long_break_ms=0, long_break_every=2)
    timer.start()
    timer.tick(60_000)
    timer.tick(10_000)
    timer.tick(60_000)
    assert timer.break_is_long() is False
    assert timer.duration_ms() == 10_000


def test_completed_sessions_can_be_seeded_from_the_save_file():
    """The lifetime record survives a restart; it is handed back in here."""
    timer = FocusTimer(focus_ms=60_000, completed_sessions=7)
    assert timer.completed_sessions == 7
    timer.start()
    timer.tick(60_000)
    assert timer.completed_sessions == 8


# -- 统计聚合（专注统计展示的数据层） ---------------------------------------


def _events(*pairs):
    """(utc_ts, kind) pairs -> event rows with a placeholder detail."""
    return [(ts, kind, "{}") for ts, kind in pairs]


def test_summary_counts_only_completed_focus_events():
    from datetime import date

    today = date(2026, 10, 6)
    rows = _events(
        ("2026-10-06T01:00:00+00:00", "focus"),
        ("2026-10-06T05:00:00+00:00", "focus"),
        ("2026-10-06T06:00:00+00:00", "focus_start"),  # 开始不算完成
        ("2026-10-05T09:00:00+00:00", "focus"),
        ("2026-10-05T10:00:00+00:00", "pet"),
    )
    summary = summarize_focus_events(rows, today=today, days=7)
    assert summary.today == 2
    assert summary.week == 3
    assert summary.per_day[0] == ("2026-10-06", 2)
    assert summary.per_day[1] == ("2026-10-05", 1)


def test_summary_converts_utc_to_the_local_day():
    """A 00:30 local (UTC+8) finish is 16:30 UTC the previous day - it must
    still land on the local today, not the UTC day."""
    from datetime import date, timedelta, timezone

    summary = summarize_focus_events(
        _events(("2026-10-05T16:30:00+00:00", "focus")),
        today=date(2026, 10, 6),
        days=7,
        local_tz=timezone(timedelta(hours=8)),
    )
    assert summary.today == 1
    assert summary.per_day[1] == ("2026-10-05", 0)


def test_summary_spans_all_days_with_zeros():
    from datetime import date

    summary = summarize_focus_events([], today=date(2026, 10, 6), days=7)
    assert len(summary.per_day) == 7
    assert all(count == 0 for _, count in summary.per_day)
    assert summary.today == 0 and summary.week == 0


def test_summary_skips_malformed_timestamps():
    from datetime import date

    summary = summarize_focus_events(
        _events(("不是时间戳", "focus"), ("2026-10-06T02:00:00+00:00", "focus")),
        today=date(2026, 10, 6),
        days=3,
    )
    assert summary.today == 1
