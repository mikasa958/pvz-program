# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec: single-file Windows game executable.

from pathlib import Path

from PyInstaller.utils.hooks import collect_all

PROJECT_DIR = Path(SPECPATH).resolve()
ENTRY_SCRIPT = str(PROJECT_DIR / "main.py")

pygame_datas: list = []
pygame_binaries: list = []
pygame_hiddenimports: list = []
for candidate in ("pygame", "pygame_ce"):
    try:
        datas, binaries, hiddenimports = collect_all(candidate)
    except Exception:
        continue
    pygame_datas += datas
    pygame_binaries += binaries
    pygame_hiddenimports += hiddenimports

hiddenimports = sorted(
    set(
        pygame_hiddenimports
        + [
            "agents",
            "config",
            "database",
            "enemy",
            "env",
            "logger",
            "map_effects",
            "renderer",
            "tower",
            "training_adapter",
            "upgrades",
            "waves",
        ]
    )
)

a = Analysis(
    [ENTRY_SCRIPT],
    pathex=[str(PROJECT_DIR)],
    binaries=pygame_binaries,
    datas=pygame_datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["matplotlib", "numpy", "pandas", "scipy", "tkinter"],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="TowerDefense",
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
)
