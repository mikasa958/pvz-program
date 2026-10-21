# PVZ Roguelike Defense

项目仓库：[mikasa958/pvz-program](https://github.com/mikasa958/pvz-program)。

基于 Python / Pygame 的塔防游戏与强化学习实验环境。支持手动操作、规则 AI、局内三选一强化，以及可复现的 Q-learning 训练。

本仓库以 v5 为维护版本：5×9 棋盘、3 种植物、15 波战役，以及撑杆、铁桶等敌人。训练使用独立的简化配置，可在没有显示器的环境中运行。

## 快速开始

建议使用 Python 3.11–3.13。在仓库根目录执行：

```bash
python -m venv .venv
```

Windows PowerShell 激活虚拟环境：

```powershell
.\.venv\Scripts\Activate.ps1
```

macOS / Linux：

```bash
source .venv/bin/activate
```

安装依赖并启动：

```bash
python -m pip install -r requirements.txt
python main.py
```

Python 3.13 及以上通过 `pygame-ce` 提供 `pygame` 模块，较早版本使用 `pygame`。运行游戏需要图形桌面。

## 操作

| 按键 / 操作 | 功能 |
| --- | --- |
| 鼠标左键 | 放置植物、收集阳光、选择强化 |
| Q / W / E | 选择豌豆射手 / 向日葵 / 坚果墙 |
| S | 切换铲子工具 |
| 1 / 2 / 3 | 选择强化卡片 |
| F1 / F2 / F3 | 手动 / 规则 AI / 模型策略接口 |
| P | 暂停或继续 |
| R / Esc | 重开 / 退出 |

`MODEL AI` 当前是策略接入占位接口，默认执行等待动作；仓库没有自动加载的预训练 v5 模型。训练脚本保存的 Q 表也不会自动接入图形演示。

## 训练与接口

运行训练冒烟检查：

```bash
python scripts/train_q_table_smoke.py
```

训练并将 Q 表保存为 JSON：

```bash
python scripts/train_q_table.py --episodes 100 --stage 0 --save outputs/q_table.json
```

`--stage` 支持 `0`、`1`、`2`。日志、训练输出和模型文件默认不进入 Git。

```python
from config import build_training_stage_0_config
from env import TowerDefenseEnv
from training_adapter import FastCompatibilityEnv

env = FastCompatibilityEnv(
    TowerDefenseEnv(build_training_stage_0_config(seed=42)),
    seed=42,
    step_dt=1.0,
    state_mode="compact",
)
state = env.reset(seed=42)
next_state, reward, done, info = env.step(env.valid_actions()[0])
```

只从 `valid_actions()` 中选择动作。完整接口与状态空间说明见 [强化学习接口](docs/rl-interface.md)。

## 开发与验证

```bash
python -m pip install -r requirements-dev.txt
python -m pytest
python -m ruff check .
python -m tests.test_env_compatibility
```

测试使用 SDL 的 dummy 驱动，不需要打开游戏窗口。最后一条命令包含独立的兼容性回归检查；可选外部 `pvzlib` 未安装时会明确跳过其 Q-learning 集成检查。

Windows 打包：

```powershell
powershell -ExecutionPolicy Bypass -File .\build_exe.ps1
```

输出为 `dist/TowerDefense.exe`。打包工具与产物不提交到仓库。

## 目录

```text
.
├── main.py                 # 图形演示入口
├── env.py                  # 环境、奖励、状态与波次推进
├── config.py               # 实际使用的 Python 配置
├── agents.py               # 规则 AI 与模型策略接口
├── waves.py                # 战役和随机波次
├── tower.py / enemy.py     # 战斗实体
├── upgrades.py             # 三选一强化
├── map_effects.py          # 地图效果
├── renderer.py             # Pygame 渲染
├── logger.py / database.py # 对局记录
├── training_adapter.py     # 训练环境适配
├── rl_training.py          # 紧凑状态与宏动作
├── config/                 # 保留的 YAML 配置参考
├── scripts/                # Q-learning 训练脚本
├── tests/                  # 现有测试与兼容性检查
├── docs/                   # 操作说明、方案和汇报资料
└── .github/workflows/      # 自动验证
```

运行配置由 `config.py` 中的构建函数生成；`config/default.yaml` 保留作参考，当前代码不会自动读取它。

## 项目资料与 GitHub 上传

- [游戏说明书](docs/user-guide.md)
- [整理记录与验证结果](docs/repository-cleanup.md)
- `docs/plans/`：历史设计方案；`docs/reports/`：原始汇报文件。
- `.local-archive/`：本机保留的历史整合项目、旧模型、安装包、演示程序、视频和原始日志，已通过 `.gitignore` 排除。此目录不会出现在 GitHub 克隆中。

使用 Git 上传时，在根目录执行 `git add .` 会遵循忽略规则。通过网页上传时，请使用整理生成的源码 ZIP 解压后的内容，避免选中 `.local-archive/` 或 `.venv/`。发布 Windows 可执行程序时，可将 `dist/TowerDefense.exe` 作为独立发行附件。

本项目是教学与实验作品，与商业原作无关联。项目目前未指定开源许可证；公开源码本身不等于授予开源授权。
