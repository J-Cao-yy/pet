# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for Betty Pet — build the single-file exe with:

    .venv-build/Scripts/python.exe -m PyInstaller --noconfirm BettyPet.spec

OneFile so the pet is one portable exe; Windowed so no console flashes.

``assets/`` is **pre-processed at build time**: the 2048x2048 source frames are
resized to 512px (the window shows ~160px and scale tops out at 2.5x, so 512
is generous) — bundling the originals made the exe ~100 MB, mostly art. The
processed copies land in ``build/bundle_assets`` and are resolved at runtime
via ``sys._MEIPASS`` (see ``config.PROJECT_ROOT``). The SQLite save keeps
living in ``~/.betty_pet/state.db`` regardless.
"""

import shutil
from pathlib import Path

from PIL import Image

SRC = Path(SPECPATH) / "assets"
MAX_FRAME_PX = 512
bundle = Path(SPECPATH) / "build" / "bundle_assets"
bundle.mkdir(parents=True, exist_ok=True)

for png in SRC.glob("*.png"):
    target = bundle / png.name
    image = Image.open(png).convert("RGBA")
    if max(image.size) > MAX_FRAME_PX:
        image.thumbnail((MAX_FRAME_PX, MAX_FRAME_PX), Image.Resampling.LANCZOS)
    image.save(target, optimize=True)
shutil.copy(SRC / "manifest.json", bundle / "manifest.json")
shutil.copy(SRC / "BettyPet.ico", bundle / "BettyPet.ico")
sounds = bundle / "sounds"
sounds.mkdir(exist_ok=True)
for wav in (SRC / "sounds").glob("*.wav"):
    shutil.copy(wav, sounds / wav.name)

a = Analysis(
    ["main.py"],
    pathex=["src"],
    binaries=[],
    datas=[(str(bundle), "assets")],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["PIL._avif"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="BettyPet",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="assets/BettyPet.ico",
)
