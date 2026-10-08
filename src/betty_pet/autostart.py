"""Registering the pet to start with Windows - opt-in, never automatic.

Nothing in here runs on its own. The module is driven only by the explicit CLI
flags ``--install-autostart`` / ``--uninstall-autostart``, because writing to
someone's startup folder changes *their machine*, not this project. Anything
that does that should take a deliberate command, and be trivially reversible.

The entry is a ``.vbs`` shim in the per-user Startup folder rather than a
registry value, for three reasons:

* it is visible in Explorer, so "what did it install?" has an answer;
* deleting one file is a complete uninstall;
* ``WScript.Shell`` can launch ``pythonw.exe`` hidden, so no console window
  flashes on every boot.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from .config import PROJECT_ROOT

__all__ = [
    "LAUNCHER_NAME",
    "install",
    "is_installed",
    "launcher_script",
    "startup_dir",
    "target_path",
    "uninstall",
]

LAUNCHER_NAME = "BettyPet.vbs"


def startup_dir() -> Path:
    """The per-user Startup folder. Read from the environment, no win32 needed."""
    appdata = os.environ.get("APPDATA")
    if appdata:
        return Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
    return Path.home() / "AppData" / "Roaming" / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"


def target_path() -> Path:
    return startup_dir() / LAUNCHER_NAME


def launch_command(project_root: Path | None = None) -> tuple[str, str]:
    """``(executable, script)`` the launcher will run.

    ``pythonw.exe`` is preferred so no console window appears at login.
    When running from a PyInstaller bundle the executable *is* the pet, so
    there is no script argument.
    """
    executable = Path(sys.executable)
    if getattr(sys, "frozen", False):
        return str(executable), ""
    windowed = executable.with_name("pythonw.exe")
    if windowed.is_file():
        executable = windowed
    root = project_root or PROJECT_ROOT
    return str(executable), str(root / "main.py")


def launcher_script(project_root: Path | None = None) -> str:
    """The VBS launcher text. Pure function so it can be asserted in tests."""
    executable, script = launch_command(project_root)
    if script:
        run_args = f'""{executable}"" ""{script}""'
    else:
        run_args = f'""{executable}""'
    return (
        "' Betty Pet 开机自启启动器（自动生成；删除本文件即可取消）\n"
        "Set shell = CreateObject(\"WScript.Shell\")\n"
        f"shell.Run {run_args}, 0, False\n"
    )


def is_installed() -> bool:
    return target_path().is_file()


def install(project_root: Path | None = None) -> Path:
    """Write the launcher. Raises on non-Windows; overwrites in place."""
    if sys.platform != "win32":
        raise RuntimeError("开机自启只支持 Windows。")
    path = target_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(launcher_script(project_root), encoding="utf-8")
    return path


def uninstall() -> bool:
    """Remove the launcher. Returns whether a file was actually removed."""
    path = target_path()
    if not path.is_file():
        return False
    path.unlink()
    return True
