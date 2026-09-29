"""System tray icon built directly on pywin32.

Deliberately dependency-free: ``win32gui`` can create a shell notification icon
on its own, so the tray costs no new package and never touches the user's Python
environment.

The icon hosts a tiny message-only window on its own daemon thread, because
``PumpMessages`` blocks and Tk owns the main thread. **Tray actions never touch
Tk directly** - they are pushed onto a :class:`queue.Queue` that the window
layer drains from a Scheduler job, so every UI mutation still happens on the
main thread (Tkinter is not thread-safe).

If pywin32 is missing, or any part of the setup fails, :meth:`TrayIcon.start`
returns ``False`` and the caller carries on without a tray. A broken tray must
never stop the pet from running.
"""

from __future__ import annotations

import queue
import threading
from pathlib import Path

__all__ = ["TrayAction", "TrayIcon", "NullTray", "make_tray"]


class TrayAction:
    """Actions the tray can request, drained by the window layer."""

    TOGGLE_VISIBLE = "toggle_visible"
    TOGGLE_FOLLOW = "toggle_follow"
    QUIT = "quit"


_ID_VISIBLE = 1001
_ID_FOLLOW = 1002
_ID_QUIT = 1003
_CLASS_NAME = "BettyPetTrayWindow"
_CALLBACK_MESSAGE = 0x0400 + 20  # WM_USER + 20

try:  # pragma: no cover - depends on the platform
    import win32con
    import win32gui
except ImportError:  # pragma: no cover - non-Windows, or pywin32 not installed
    win32con = None  # type: ignore[assignment]
    win32gui = None  # type: ignore[assignment]


class NullTray:
    """Used when a tray cannot exist. Keeps call sites free of ``if``s."""

    def start(self) -> bool:
        return False

    def stop(self) -> None:
        return None

    def available(self) -> bool:
        return False

    def set_tooltip(self, text: str) -> None:
        return None


class TrayIcon:
    """A shell notification icon with a right-click menu.

    ``actions`` is the hand-off channel: the tray thread only ever puts strings
    on it, and the Tk side polls it. See the module docstring for why.
    """

    def __init__(self, tooltip: str = "Betty Pet", icon_path: str | Path | None = None) -> None:
        self.tooltip = tooltip[:127]  # szTip is a 128-char fixed buffer
        self.icon_path = Path(icon_path) if icon_path else None
        self.actions: queue.Queue[str] = queue.Queue()
        self._hwnd: int | None = None
        self._hicon: int = 0
        self._thread: threading.Thread | None = None
        self._started = False

    # -- lifecycle ---------------------------------------------------------

    def start(self) -> bool:
        """Create the icon. Returns ``False`` instead of raising on failure."""
        if win32gui is None:
            return False
        try:
            self._hicon = self._load_icon()
            self._hwnd = self._create_window()
            self._add_icon()
        except Exception:  # pragma: no cover - defensive: tray is optional
            self.stop()
            return False
        self._started = True
        self._thread = threading.Thread(target=self._pump, name="betty-tray", daemon=True)
        self._thread.start()
        return True

    def stop(self) -> None:
        hwnd, self._hwnd = self._hwnd, None
        self._started = False
        if win32gui is None or not hwnd:
            return
        try:
            win32gui.Shell_NotifyIcon(win32gui.NIM_DELETE, self._nid(hwnd))
        except Exception:  # pragma: no cover - defensive
            pass
        try:
            win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
        except Exception:  # pragma: no cover - defensive
            pass

    def available(self) -> bool:
        return self._started

    def set_tooltip(self, text: str) -> None:
        """Update the hover text (used to show whether chasing is on)."""
        self.tooltip = text[:127]
        if win32gui is None or not self._hwnd:
            return
        try:
            win32gui.Shell_NotifyIcon(win32gui.NIM_MODIFY, self._nid(self._hwnd))
        except Exception:  # pragma: no cover - defensive
            pass

    # -- win32 plumbing ----------------------------------------------------

    def _load_icon(self) -> int:
        if self.icon_path and self.icon_path.is_file():
            try:
                return win32gui.LoadImage(  # type: ignore[union-attr]
                    0, str(self.icon_path), win32con.IMAGE_ICON, 0, 0,
                    win32con.LR_LOADFROMFILE | win32con.LR_DEFAULTSIZE,
                )
            except Exception:  # pragma: no cover - fall back to the stock icon
                pass
        return win32gui.LoadIcon(0, win32con.IDI_APPLICATION)  # type: ignore[union-attr]

    def _create_window(self) -> int:
        wc = win32gui.WNDCLASS()  # type: ignore[union-attr]
        wc.lpfnWndProc = self._on_message
        wc.hInstance = win32gui.GetModuleHandle(None)  # type: ignore[union-attr]
        wc.lpszClassName = _CLASS_NAME
        wc.hCursor = win32gui.LoadCursor(0, win32con.IDC_ARROW)  # type: ignore[union-attr]
        wc.hbrBackground = win32con.COLOR_WINDOW
        try:
            atom = win32gui.RegisterClass(wc)  # type: ignore[union-attr]
        except Exception:
            # Class already registered (second instance in one process, or a
            # previous run): the name is enough for CreateWindow.
            atom = _CLASS_NAME
        return win32gui.CreateWindow(  # type: ignore[union-attr]
            atom, _CLASS_NAME, 0, 0, 0, 0, 0, 0, 0, wc.hInstance, None
        )

    def _nid(self, hwnd: int) -> tuple:
        flags = win32gui.NIF_ICON | win32gui.NIF_MESSAGE | win32gui.NIF_TIP  # type: ignore[union-attr]
        return (hwnd, 0, flags, _CALLBACK_MESSAGE, self._hicon, self.tooltip)

    def _add_icon(self) -> None:
        win32gui.Shell_NotifyIcon(win32gui.NIM_ADD, self._nid(self._hwnd))  # type: ignore[union-attr]

    def _pump(self) -> None:  # pragma: no cover - runs on the tray thread
        try:
            win32gui.PumpMessages()
        except Exception:
            pass

    # -- message handling --------------------------------------------------

    def _on_message(self, hwnd, msg, wparam, lparam):  # pragma: no cover - win32 callback
        if msg == _CALLBACK_MESSAGE:
            if lparam == win32con.WM_RBUTTONUP:
                self._popup_menu(hwnd)
            elif lparam == win32con.WM_LBUTTONDBLCLK:
                self.actions.put(TrayAction.TOGGLE_VISIBLE)
            return 0
        if msg == win32con.WM_COMMAND:
            self._dispatch(wparam & 0xFFFF)
            return 0
        if msg == win32con.WM_DESTROY:
            win32gui.PostQuitMessage(0)
            return 0
        return win32gui.DefWindowProc(hwnd, msg, wparam, lparam)

    def _dispatch(self, command: int) -> None:
        action = {_ID_VISIBLE: TrayAction.TOGGLE_VISIBLE,
                  _ID_FOLLOW: TrayAction.TOGGLE_FOLLOW,
                  _ID_QUIT: TrayAction.QUIT}.get(command)
        if action:
            self.actions.put(action)

    def _popup_menu(self, hwnd: int) -> None:  # pragma: no cover - win32 popup
        menu = win32gui.CreatePopupMenu()
        win32gui.AppendMenu(menu, win32con.MF_STRING, _ID_VISIBLE, "显示 / 隐藏")
        win32gui.AppendMenu(menu, win32con.MF_STRING, _ID_FOLLOW, "跟随鼠标")
        win32gui.AppendMenu(menu, win32con.MF_SEPARATOR, 0, None)
        win32gui.AppendMenu(menu, win32con.MF_STRING, _ID_QUIT, "退出")
        x, y = win32gui.GetCursorPos()
        # Without foreground the menu will not dismiss on an outside click.
        win32gui.SetForegroundWindow(hwnd)
        win32gui.TrackPopupMenu(
            menu, win32con.TPM_LEFTALIGN | win32con.TPM_RIGHTBUTTON, x, y, 0, hwnd, None
        )
        win32gui.PostMessage(hwnd, win32con.WM_NULL, 0, 0)
        win32gui.DestroyMenu(menu)


def make_tray(tooltip: str = "Betty Pet", icon_path: str | Path | None = None) -> TrayIcon | NullTray:
    """A real tray when the platform allows it, otherwise a silent stand-in."""
    if win32gui is None:
        return NullTray()
    return TrayIcon(tooltip, icon_path)
