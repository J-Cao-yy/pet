"""Window probing and perch geometry. No Tkinter and no real windows involved."""

from __future__ import annotations

import pytest

from betty_pet import desktop
from betty_pet.desktop import (
    NullWindowProbe,
    WindowRect,
    Win32WindowProbe,
    make_probe,
    perch_bounds,
)
from betty_pet.physics import Bounds

# 1920x1080 screen, a 128px pet, and 48px reserved for the taskbar.
SCREEN = Bounds(left=0.0, top=0.0, right=1792.0, bottom=904.0)
PET = (128, 128)


def window(left: int, top: int, right: int, bottom: int, handle: int = 1) -> WindowRect:
    return WindowRect(handle, left, top, right, bottom, "编辑器")


class FakeGui:
    """Stands in for the ``win32gui`` module so filtering can be tested."""

    def __init__(self, windows, *, foreground: int = 0) -> None:
        self.windows = windows
        self.foreground = foreground

    def GetForegroundWindow(self) -> int:
        return self.foreground

    def GetDesktopWindow(self) -> int:
        return 4242

    def IsWindowVisible(self, handle: int) -> bool:
        return self.windows[handle]["visible"]

    def IsIconic(self, handle: int) -> bool:
        return self.windows[handle]["iconic"]

    def GetClassName(self, handle: int) -> str:
        return self.windows[handle]["cls"]

    def GetWindowRect(self, handle: int):
        return self.windows[handle]["rect"]

    def GetWindowText(self, handle: int) -> str:
        return self.windows[handle].get("title", "")


class FakeProcess:
    def __init__(self, windows) -> None:
        self.windows = windows

    def GetWindowThreadProcessId(self, handle: int):
        return 0, self.windows[handle]["pid"]


@pytest.fixture
def probe(monkeypatch):
    """A probe wired to fake win32 modules; returns a helper to load windows."""

    def install(windows, *, foreground: int = 0) -> Win32WindowProbe:
        monkeypatch.setattr(desktop, "win32gui", FakeGui(windows, foreground=foreground))
        monkeypatch.setattr(desktop, "win32process", FakeProcess(windows))
        return Win32WindowProbe(exclude_pids=frozenset({999}))

    return install


# -- geometry ---------------------------------------------------------------


def test_usable_requires_minimum_width():
    assert not WindowRect(1, 0, 0, 80, 200).usable()
    assert WindowRect(1, 0, 0, 200, 200).usable()


def test_perch_bounds_stand_on_the_top_edge():
    surface = perch_bounds(window(100, 300, 500, 800), *PET, SCREEN)
    assert surface is not None
    # The pet's bottom rests on the window's top edge: 300 - 128 = 172.
    assert surface.bottom == 172.0
    assert (surface.left, surface.right) == (100.0, 372.0)
    assert surface.top == SCREEN.top


def test_perch_bounds_refuses_when_there_is_no_headroom():
    # A maximised window: its top edge is the top of the screen.
    assert perch_bounds(window(0, 0, 1920, 1040), *PET, SCREEN) is None


def test_perch_bounds_refuses_a_window_too_narrow_to_count():
    assert perch_bounds(window(100, 300, 150, 800), *PET, SCREEN) is None


def test_perch_bounds_pins_left_when_window_is_narrower_than_the_pet():
    surface = perch_bounds(window(100, 300, 220, 800), *PET, SCREEN)
    assert surface is not None
    assert surface.left == surface.right == 100.0
    assert surface.width == 0.0


def test_perch_bounds_clamps_a_window_hanging_off_the_screen():
    surface = perch_bounds(window(-50, 300, 500, 800), *PET, SCREEN)
    assert surface is not None
    assert surface.left == 0.0


# -- probe filtering --------------------------------------------------------


def test_probe_returns_the_foreground_window(probe):
    gui = probe({7: {"rect": (10, 300, 400, 700), "cls": "Notepad", "visible": True,
                     "iconic": False, "pid": 55, "title": "未命名"}}, foreground=7)
    found = gui.foreground()
    assert found is not None and found.title == "未命名"


def test_probe_ignores_its_own_windows(probe):
    windows = {7: {"rect": (10, 300, 400, 700), "cls": "TkTopLevel", "visible": True,
                   "iconic": False, "pid": 999}}
    assert probe(windows, foreground=7).foreground() is None


@pytest.mark.parametrize(
    "entry",
    [
        {"rect": (10, 300, 400, 700), "cls": "Notepad", "visible": True, "iconic": True, "pid": 55},
        {"rect": (10, 300, 400, 700), "cls": "Notepad", "visible": False, "iconic": False, "pid": 55},
        {"rect": (10, 300, 400, 700), "cls": "Progman", "visible": True, "iconic": False, "pid": 55},
        {"rect": (10, 300, 400, 700), "cls": "Shell_TrayWnd", "visible": True, "iconic": False, "pid": 55},
        {"rect": (10, 300, 80, 700), "cls": "Notepad", "visible": True, "iconic": False, "pid": 55},
    ],
)
def test_probe_rejects_unusable_windows(probe, entry):
    assert probe({7: entry}, foreground=7).foreground() is None


def test_probe_rejects_the_desktop_window(probe):
    entry = {"rect": (0, 0, 1920, 1080), "cls": "Notepad", "visible": True,
             "iconic": False, "pid": 55}
    assert probe({4242: entry}, foreground=4242).foreground() is None


def test_probe_never_raises_without_a_foreground_window(probe):
    assert probe({}, foreground=0).foreground() is None


def test_make_probe_falls_back_when_pywin32_is_missing(monkeypatch):
    monkeypatch.setattr(desktop, "win32gui", None)
    fallback = make_probe()
    assert isinstance(fallback, NullWindowProbe)
    assert fallback.available() is False
    assert fallback.foreground() is None
