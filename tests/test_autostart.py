"""Autostart launcher generation. Writes only into a temporary APPDATA."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from betty_pet import autostart


@pytest.fixture
def fake_appdata(monkeypatch, tmp_path):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    return tmp_path


def test_startup_dir_hangs_off_appdata(fake_appdata):
    assert autostart.startup_dir() == (
        fake_appdata / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
    )


def test_target_path_uses_the_launcher_name(fake_appdata):
    assert autostart.target_path().name == autostart.LAUNCHER_NAME


def test_launcher_prefers_pythonw_and_quotes_both_paths(tmp_path):
    script = autostart.launcher_script(tmp_path)
    assert "WScript.Shell" in script
    assert str(tmp_path / "main.py") in script
    # pythonw keeps the boot-time launch console-free; fall back to whatever
    # interpreter is running if it is missing.
    expected = Path(sys.executable).with_name("pythonw.exe")
    if expected.is_file():
        assert "pythonw.exe" in script
    else:
        assert Path(sys.executable).name in script


def test_install_then_uninstall_round_trip(fake_appdata):
    assert autostart.is_installed() is False
    path = autostart.install()
    assert path.is_file()
    assert autostart.is_installed() is True
    assert autostart.uninstall() is True
    assert autostart.is_installed() is False
    assert autostart.uninstall() is False


def test_install_is_idempotent(fake_appdata):
    first = autostart.install().read_text(encoding="utf-8")
    second = autostart.install().read_text(encoding="utf-8")
    assert first == second


def test_install_refuses_on_non_windows(fake_appdata, monkeypatch):
    monkeypatch.setattr(autostart.sys, "platform", "linux")
    with pytest.raises(RuntimeError):
        autostart.install()
