"""
一键运行入口（请在「integrated_td_ai」目录下执行，或与批处理同目录双击）。

  python run.py              显示说明
  python run.py install      安装依赖（pip install -r requirements.txt）
  python run.py play         打开塔防游戏窗口
  python run.py train        训练 Q 表（可接训练脚本参数）
  python run.py test         兼容性测试（无窗口）
  python run.py check        快速集成检查（无窗口）

示例：
  python run.py train --episodes 3000 --seed 1
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TOWER = ROOT / "tower_defense_ai"
SCRIPTS = ROOT / "scripts"
PVZ_COURSE = ROOT / "auto_PVZ_v1" / "pvz_ai_course"


def _ensure_course_env() -> None:
    if os.environ.get("PVZLIB_COURSE_DIR"):
        return
    if (PVZ_COURSE / "pvzlib").is_dir():
        os.environ["PVZLIB_COURSE_DIR"] = str(PVZ_COURSE)


def _run_play() -> int:
    if not (TOWER / "main.py").is_file():
        print("找不到 tower_defense_ai/main.py")
        return 1
    env = os.environ.copy()
    # 避免之前跑 test 时设的 dummy 驱动导致黑屏/无窗口
    env.pop("SDL_VIDEODRIVER", None)
    env.pop("SDL_AUDIODRIVER", None)
    return subprocess.call(
        [sys.executable, str(TOWER / "main.py")],
        cwd=str(TOWER),
        env=env,
    )


def _run_train(argv_tail: list[str]) -> int:
    script = SCRIPTS / "train_tower_qlearning.py"
    if not script.is_file():
        print(f"找不到 {script}")
        return 1
    return subprocess.call([sys.executable, str(script), *argv_tail], cwd=str(ROOT))


def _run_test() -> int:
    script = TOWER / "test_env_compatibility.py"
    if not script.is_file():
        print(f"找不到 {script}")
        return 1
    _ensure_course_env()
    env = os.environ.copy()
    env.setdefault("SDL_VIDEODRIVER", "dummy")
    env.setdefault("SDL_AUDIODRIVER", "dummy")
    return subprocess.call([sys.executable, str(script)], cwd=str(TOWER), env=env)


def _run_check() -> int:
    script = SCRIPTS / "check_integration.py"
    if not script.is_file():
        print(f"找不到 {script}")
        return 1
    env = os.environ.copy()
    env.setdefault("SDL_VIDEODRIVER", "dummy")
    env.setdefault("SDL_AUDIODRIVER", "dummy")
    return subprocess.call([sys.executable, str(script)], cwd=str(ROOT), env=env)


def _run_install() -> int:
    req = ROOT / "requirements.txt"
    if not req.is_file():
        print(f"找不到 {req}")
        return 1
    return subprocess.call([sys.executable, "-m", "pip", "install", "-r", str(req)])


def _print_help() -> None:
    print(__doc__ or "")
    print(f"项目根目录: {ROOT}")
    print(f"课程路径(自动设置 PVZLIB_COURSE_DIR): {PVZ_COURSE}")


def main() -> int:
    if len(sys.argv) < 2:
        _print_help()
        return 0

    cmd = sys.argv[1].lower()
    tail = sys.argv[2:]

    if cmd in ("-h", "--help", "help"):
        _print_help()
        return 0
    if cmd == "install":
        return _run_install()
    if cmd == "play":
        return _run_play()
    if cmd == "train":
        return _run_train(tail)
    if cmd == "test":
        return _run_test()
    if cmd == "check":
        return _run_check()

    print(f"未知命令: {cmd}\n")
    _print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
