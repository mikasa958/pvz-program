# auto_PVZ_v1 与 tower_defense_ai 对接说明

## 1. 最终整合思路

不要把两个“游戏规则”混在一起。

- `auto_PVZ_v1`：保留为训练算法库，重点使用 `pvz_ai_course/pvzlib/agents.py` 里的 `QLearningAgent` 和 `pvzlib/train.py` 里的训练/评估循环。
- `tower_defense_ai`：作为唯一真实运行环境，负责 5×9 网格、敌人移动、炮塔攻击、资源增长、Pygame 展示、日志和数据库。
- `scripts/train_tower_qlearning.py`：桥接脚本，把同伴的 Q-learning 算法接到你的塔防环境上训练，并保存模型到 `tower_defense_ai/models/tower_q_table.pkl`。

整合后的闭环是：

```text
tower_defense_ai.TowerDefenseEnv
        ↓ reset/get_state/valid_actions/step
training_adapter.FastCompatibilityEnv
        ↓ 标准 Gym-like 接口
auto_PVZ_v1.pvzlib.QLearningAgent
        ↓ 训练得到 Q-table
tower_defense_ai.models/tower_q_table.pkl
        ↓ Pygame MODEL AI 模式读取
tower_defense_ai/main.py 演示
```

## 2. 两边接口统一标准

### 状态 state

你的塔防环境输出的是可直接作为 Q-table key 的离散 tuple：

```python
state = env.reset(seed=42)
state = env.get_state()
```

当前 state 结构为：

```text
(resource_bucket, base_hp, time_bucket, spawn_bucket,
 tower_count_bucket, enemy_count_bucket,
 row0_tower_mask, row1_tower_mask, row2_tower_mask, row3_tower_mask, row4_tower_mask,
 row0_enemy_mask, row1_enemy_mask, row2_enemy_mask, row3_enemy_mask, row4_enemy_mask)
```

### 动作 action

统一使用整数动作，不传中文、不传坐标对象。

```text
0      = wait
1~45   = place_tower(row, col)
action_id = 1 + row * 9 + col
```

例如：

```python
row = 2
col = 3
action_id = 1 + row * 9 + col  # 22
```

### 环境 step

所有训练模块只认这个接口：

```python
next_state, reward, done, info = env.step(action_id)
```

`info` 里保留调试字段：

```python
info["action_success"]
info["action_reason"]
info["kills"]
info["breaches"]
info["resources"]
info["base_hp"]
info["reward_breakdown"]
```

## 3. 运行顺序

### 第一步：安装依赖

在整合项目根目录运行：

```bash
pip install -r requirements.txt
```

如果只做命令行训练，代码已经提供 `pygame_compat.py` 兜底；但正式 Pygame 展示仍建议安装 pygame 或 pygame-ce。

### 第二步：检查对接是否通

```bash
python scripts/check_integration.py
```

看到类似输出即可：

```text
OK: auto_PVZ_v1 Q-learning can train tower_defense_ai environment.
```

### 第三步：训练模型

```bash
python scripts/train_tower_qlearning.py --episodes 2000 --eval-episodes 200
```

训练完成后会生成：

```text
tower_defense_ai/models/tower_q_table.pkl
```

### 第四步：运行可视化演示

```bash
python tower_defense_ai/main.py
```

按键：

```text
1 = 手动模式
2 = 规则 AI 模式
3 = 模型 AI 模式
R = 重开
ESC = 退出
```

## 4. 原始版本中最容易出问题的点

### 问题 1：同伴的 env 和你的 env 不是同一个东西

同伴 `SimplifiedPVZEnv` 是抽象环境，动作只有 4 个：

```text
SAVE / PLANT_SUNFLOWER / PLANT_PEASHOOTER / PLANT_WALLNUT
```

你的 `TowerDefenseEnv` 是具体塔防环境，动作有 46 个：

```text
WAIT + 5×9 个放塔动作
```

所以不能让你的 Pygame 直接吃同伴环境的动作。正确做法是：保留同伴的 Q-learning 算法，改用你的环境训练。

### 问题 2：测试文件默认路径写错

原来 `test_env_compatibility.py` 默认找：

```text
auto_PVZ/pvz_ai_course
```

但你上传的是：

```text
auto_PVZ_v1/pvz_ai_course
```

本整合版已修正。

### 问题 3：`evaluate_q` 返回值不一致

同伴的 `evaluate_q` 返回：

```python
(mean, std)
```

原测试里当成一个 float 格式化，会报错。本整合版已兼容 tuple / float 两种情况。

### 问题 4：训练环境不应该强依赖 Pygame 窗口

原 `env.py / enemy.py / tower.py` 直接 import pygame。命令行训练时如果没装 pygame，会在 import 阶段失败。本整合版加了 `pygame_compat.py`，训练可无窗口运行；Pygame 展示仍使用真实 pygame。

### 问题 5：MODEL AI 模式原来没有读取训练模型

原来的 `ModelAgent()` 是空壳，按 3 以后基本只会 wait。本整合版已经让它自动读取：

```text
tower_defense_ai/models/tower_q_table.pkl
```

并且只在 `env.valid_actions()` 给出的合法动作里选 Q 值最大的动作，避免模型乱点非法格子。

## 5. 分工建议

### 你的部分

- 维护 `tower_defense_ai`：游戏环境、Pygame 展示、状态编码、动作映射、日志、数据库。
- 保证 `reset / step / valid_actions / get_state` 稳定。
- 在汇报中讲清楚“状态感知—动作执行—奖励反馈—可视化演示”。

### 同伴部分

- 维护 `auto_PVZ_v1/pvzlib`：Q-learning、规则基线、实验曲线、对照实验。
- 负责调参：episodes、alpha、gamma、epsilon_decay、q_init。
- 产出实验结果：训练曲线、平均奖励、通关率、规则策略 vs Q-learning 对比。

### 共同约定

永远不要私自改这三个接口：

```python
env.reset(seed) -> state_tuple
env.valid_actions() -> list[int]
env.step(action_id) -> next_state, reward, done, info
```

只要这三个接口稳定，你们两个人的代码就不会互相拖垮。
