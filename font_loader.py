from __future__ import annotations

import os
import sys
from pathlib import Path

import pygame


def _windows_font_files() -> list[Path]:
    windir = Path(os.environ.get("WINDIR", r"C:\Windows"))
    fonts_dir = windir / "Fonts"
    # 按常见中文显示优先级；直接 Font(path) 不走 SysFont 注册表扫描，避免部分环境闪退
    names = (
        "msyh.ttc",
        "msyhbd.ttc",
        "simhei.ttf",
        "simsun.ttc",
        "msyhl.ttc",
        "arial.ttf",
    )
    return [fonts_dir / n for n in names]


def load_ui_font(size: int) -> pygame.font.Font:
    """
    加载界面用字体。优先 Windows 字体文件，避免 pygame.font.SysFont 在个别系统上枚举注册表崩溃
    （TypeError: expected str, bytes or os.PathLike object, not int）。
    """
    custom = os.environ.get("PYGAME_UI_FONT", "").strip()
    if custom:
        p = Path(custom)
        if p.is_file():
            try:
                return pygame.font.Font(str(p), size)
            except Exception:
                pass

    if sys.platform == "win32":
        for path in _windows_font_files():
            if path.is_file():
                try:
                    return pygame.font.Font(str(path), size)
                except Exception:
                    continue

    try:
        font = pygame.font.SysFont("arial", size)
        if font.get_height() > 0:
            return font
    except Exception:
        pass

    return pygame.font.Font(None, size)
