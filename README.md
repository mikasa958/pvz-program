# Python 塔防强化学习原型

本项目是一个面向 Q-learning 实验的简化塔防强化学习环境，不是完整的 PVZ 复刻。核心目标是构建一条清晰的训练闭环：

`状态感知 -> 决策选择 -> 动作执行 -> 奖励反馈`

需要特别说明：

- `TowerDefenseEnv` 才是真正用于训练的环境。
- `Pygame` 只负责展示和交互演示，不是训练环境。
- 训练与评估应直接调用 `TowerDefenseEnv` 或训练适配器，而不是依赖 Pygame 窗口。

## 项目简介

- 地图为 `5 x 9` 网格
- 敌人从右向左移动
- 防御塔自动攻击同一行敌人
- 资源会随时间增长
- 基地血量决定胜负
- 对外暴露离散 `tuple` 状态，便于 Q-learning 使用 Q-table

## 运行方式

安装依赖：

```bash
pip install -r requirements.txt
```

启动 Pygame 演示：

```bash
python main.py
```

运行环境兼容性测试：

```bash
python test_env_compatibility.py
```

## 项目结构

- `main.py`：Pygame 入口、模式切换、日志集成
- `env.py`：强化学习环境、状态编码、动作处理、奖励计算
- `training_adapter.py`：正式训练适配器，供队友训练模块直接调用
- `agents.py`：规则 Agent 与 Q-learning 对接辅助逻辑
- `tower.py`：防御塔实体
- `enemy.py`：敌人实体
- `renderer.py`：Pygame 渲染逻辑
- `logger.py`：CSV / JSON 步级日志记录
- `database.py`：SQLite 会话与动作存储
- `config.py`：运行时 Python 配置
- `test_env_compatibility.py`：本地 smoke test 与外部 `pvzlib` 对接验证

## 与队友训练模块对接方式

```python
from env import TowerDefenseEnv
from training_adapter import FastCompatibilityEnv

env = FastCompatibilityEnv(TowerDefenseEnv(), step_dt=1.0)

state = env.reset(seed=42)
valid_actions = env.valid_actions()
next_state, reward, done, info = env.step(action_id)
```

## 开发进度

当前阶段：

- 第一阶段：最小可运行塔防原型已完成
- 第二阶段：Q-learning 兼容环境已完成
- 第三阶段：规则基线 Agent 与兼容性测试已完成
- 第四阶段：CSV / JSON / SQLite 日志系统已完成

当前已支持功能：

- 手动模式
- 规则 AI 模式
- 模型 AI 预留模式
- 可直接作为 Q-table key 的离散状态 `tuple`
- `wait` / `place_tower` 动作映射
- 每步日志记录
- SQLite 会话存档

