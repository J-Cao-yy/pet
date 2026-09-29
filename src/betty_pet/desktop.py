"""Finding OS windows the pet can stand on.

The pet can perch on the top edge of another window (a "window perch", the
feature xiaohei-desktop-pet and Shimeji both have). Locating that window is an
OS concern, so it stays behind :class:`WindowProbe` and never leaks into the
motion code: the window layer turns a :class:`WindowRect` into a plain
:class:`~betty_pet.physics.Bounds` and feeds it to the *existing* physics step.
Gravity, walk-off-the-edge and fall-back-to-the-floor all come for free, which
is why perching needs no change to :mod:`betty_pet.physics`.

Only the foreground window is reported. Enumerating every window would let the
pet climb onto dialogs and tooltips it cannot actually reach, and a window has
to be brought forward before "stand on it" means anything to the user anyway.

Off Windows - or with pywin32 missing - everything degrades to
:class:`NullWindowProbe`, so no other module ever asks which OS it is on.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Protocol

from .physics import Bounds

__all__ = [
    "MIN_PERCH_WIDTH",
    "NullWindowProbe",
    "WindowProbe",
    "WindowRect",
    "Win32WindowProbe",
    "make_probe",
    "perch_bounds",
]


# A window narrower than this is not a platform worth standing on.
MIN_PERCH_WIDTH = 96

try:  # pragma: no cover - depends on the platform
    import win32gui
    import win32process
except ImportError:  # pragma: no cover - non-Windows, or pywin32 not installed
    win32gui = None  # type: ignore[assignment]
    win32process = None  # type: ignore[assignment]


# Shell plumbing rather than an application: the pet must not try to stand on
# the desktop, the taskbar, or the tray overflow window.
_SHELL_CLASSES = frozenset({"Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd"})


@dataclass(frozen=True)
class WindowRect:
    """Geometry of one application window, in screen pixels."""

    handle: int
    left: int
    top: int
    right: int
    bottom: int
    title: str = ""

    @property
    def width(self) -> int:
        return self.right - self.left

    @property
    def height(self) -> int:
        return self.bottom - self.top

    def usable(self) -> bool:
        """Wide and tall enough to be a perch surface."""
        return self.width >= MIN_PERCH_WIDTH and self.height > 0


class WindowProbe(Protocol):
    """Reports the window the pet may perch on, if there is one."""

    def available(self) -> bool: ...

    def foreground(self) -> WindowRect | None: ...


class NullWindowProbe:
    """Fallback used off Windows: perching is simply not offered."""

    def available(self) -> bool:
        return False

    def foreground(self) -> WindowRect | None:
        return None


class Win32WindowProbe:
    """Foreground-window probe backed by pywin32.

    ``exclude_pids`` keeps the pet's own windows out of the result. This matters
    because the pet *is* the foreground window while the user interacts with it,
    and "perch on yourself" is nonsense. The pid is the reliable filter: an
    ``overrideredirect`` Tk window has no caption to match on.
    """

    def __init__(self, exclude_pids: frozenset[int] | None = None) -> None:
        self.exclude_pids = exclude_pids if exclude_pids is not None else frozenset({os.getpid()})

    def available(self) -> bool:
        return win32gui is not None

    def foreground(self) -> WindowRect | None:
        if win32gui is None:
            return None
        try:
            handle = win32gui.GetForegroundWindow()
        except Exception:  # pragma: no cover - defensive
            return None
        return self.inspect(handle)

    def inspect(self, handle: int) -> WindowRect | None:
        """Geometry of ``handle`` if it is a window the pet may stand on."""
        if win32gui is None or not handle:
            return None
        try:
            if handle == win32gui.GetDesktopWindow():
                return None
            if not win32gui.IsWindowVisible(handle) or win32gui.IsIconic(handle):
                return None
            if win32gui.GetClassName(handle) in _SHELL_CLASSES:
                return None
            if self._is_own(handle):
                return None
            left, top, right, bottom = win32gui.GetWindowRect(handle)
        except Exception:  # pragma: no cover - window vanished mid-query
            return None
        rect = WindowRect(handle, left, top, right, bottom, self._title(handle))
        return rect if rect.usable() else None

    def _is_own(self, handle: int) -> bool:
        if win32process is None:  # pragma: no cover - defensive
            return False
        try:
            _, pid = win32process.GetWindowThreadProcessId(handle)
        except Exception:  # pragma: no cover - defensive
            return False
        return pid in self.exclude_pids

    @staticmethod
    def _title(handle: int) -> str:
        try:
            return win32gui.GetWindowText(handle) or ""  # type: ignore[union-attr]
        except Exception:  # pragma: no cover - defensive
            return ""


def make_probe(exclude_pids: frozenset[int] | None = None) -> WindowProbe:
    """The best probe this machine can offer. Never returns ``None``."""
    probe = Win32WindowProbe(exclude_pids)
    return probe if probe.available() else NullWindowProbe()


def perch_bounds(rect: WindowRect, pet_width: int, pet_height: int, screen: Bounds) -> Bounds | None:
    """Turn ``rect``'s top edge into the pet's floor.

    Returns ``None`` when the window cannot host the pet. The important refusal
    is a **maximised** window: its top edge sits at the top of the screen, so
    there is nowhere above it to stand. Instead of letting the pet overlap the
    window's title bar (and its close button) we decline.
    """
    if not rect.usable():
        return None
    bottom = float(rect.top - pet_height)
    if bottom < screen.top:
        return None
    left = max(float(rect.left), screen.left)
    right = min(float(rect.right - pet_width), screen.right)
    if right < left:
        # Window narrower than the pet: pin it to the window's left edge rather
        # than inventing a negative-width surface.
        left = right = max(float(rect.left), screen.left)
    return Bounds(left=left, top=screen.top, right=right, bottom=bottom)
