"""The tray's Tk-facing half: the action queue and the fallback.

The win32 side (icon creation, message pump, popup menu) needs a real desktop
session and is covered by hand, not here. What matters for the tests is that
nothing touches Tk from the tray thread, and that a missing pywin32 degrades
instead of exploding.
"""

from __future__ import annotations

import queue

import pytest

from betty_pet import tray as tray_module
from betty_pet.tray import NullTray, TrayAction, TrayIcon, make_tray


def test_null_tray_is_inert():
    tray = NullTray()
    assert tray.start() is False
    assert tray.available() is False
    assert tray.stop() is None
    assert tray.set_tooltip("anything") is None


def test_make_tray_falls_back_without_pywin32(monkeypatch):
    monkeypatch.setattr(tray_module, "win32gui", None)
    assert isinstance(make_tray(), NullTray)


def test_tray_never_raises_without_pywin32(monkeypatch):
    monkeypatch.setattr(tray_module, "win32gui", None)
    tray = TrayIcon("提示")
    assert tray.start() is False
    tray.stop()
    tray.set_tooltip("改了也没事")


def test_menu_commands_become_actions():
    tray = TrayIcon()
    tray._dispatch(tray_module._ID_VISIBLE)
    tray._dispatch(tray_module._ID_FOLLOW)
    tray._dispatch(tray_module._ID_QUIT)
    assert tray.actions.get_nowait() == TrayAction.TOGGLE_VISIBLE
    assert tray.actions.get_nowait() == TrayAction.TOGGLE_FOLLOW
    assert tray.actions.get_nowait() == TrayAction.QUIT


def test_unknown_command_is_ignored():
    tray = TrayIcon()
    tray._dispatch(9999)
    with pytest.raises(queue.Empty):
        tray.actions.get_nowait()


def test_tooltip_is_truncated_to_the_shell_buffer():
    tray = TrayIcon("x" * 500)
    assert len(tray.tooltip) == 127
