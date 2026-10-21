# 强化学习接口

以下说明对应当前维护的 v5 源码。战役演示与训练使用不同配置；旧版模型的状态、动作编码不能直接复用。

## 环境选择

| 构建函数 | 用途 |
| --- | --- |
| `build_campaign_v5_config(seed=42)` | 图形演示使用的 15 波战役 |
| `build_training_stage_0_config(seed=42)` | 2 波训练场景 |
| `build_training_stage_1_config(seed=42)` | 5 波训练场景 |
| `build_training_stage_2_config(seed=42)` | 8 波训练场景 |

`TowerDefenseEnv` 提供底层游戏环境，`FastCompatibilityEnv` 提供固定时间步长、观察编码选择和宏动作转换。两者均使用项目自己的四返回值接口，并非 Gymnasium 的五返回值接口。

```python
state = env.reset(seed=42)
actions = env.valid_actions()
state, reward, done, info = env.step(actions[0])
```

`state` 为离散整数元组，`reward` 为浮点数，`done` 为终止或截断标记。`info` 包含 `reward_breakdown`、`termination_reason`、`episode_truncated` 和当前合法动作等信息。

## 状态与动作

适配器的 `state_mode` 支持：

- `default`：兼容的游戏状态，长度由 `env.STATE_VECTOR_SIZE` 定义。
- `training`：包含植物、冷却和待选强化等训练信息，长度由 `env.TRAINING_STATE_VECTOR_SIZE` 定义。
- `compact`：训练用紧凑状态，长度由 `rl_training.TRAINING_COMPACT_STATE_SIZE` 定义。

`use_state_hash=True` 会将 compact 状态转换为哈希键。模型及持久化代码应保存所用编码与配置，避免混用不同状态空间。

完整动作空间包含等待、3 种植物在 45 个格子上的放置动作，以及 3 个强化选择动作。`training_action_mode="macro"` 时，适配器将宏动作转换为底层动作。

动作编码与 `state_mode` 是两个独立设置：切换状态编码不会自动切换动作空间。建议用内置训练配置，并始终从 `valid_actions()` 选取动作。

更丰富的调试信息通过 `get_render_state()` 获取，例如波次、阳光、强化、地图效果和卡牌冷却。

## 训练与保存

```bash
python scripts/train_q_table_smoke.py
python scripts/train_q_table.py --episodes 100 --stage 0 --save outputs/q_table.json
```

训练脚本自动设置 SDL dummy 驱动。虽然不需要显示器，环境仍依赖 `pygame` 模块，需要安装 `requirements.txt`。

当前 `agents.ModelAgent` 接受状态到动作的字典或可调用策略。`main.py` 默认创建空策略；F3 模式不会自动读取训练脚本输出。接入模型时，需要同时对齐配置、状态编码与动作编码，并自行实现加载和转换。

## 可选旧算法兼容检查

`python -m tests.test_env_compatibility` 默认运行本项目的回归检查。只有设置 `PVZLIB_COURSE_DIR` 指向包含 `pvzlib/` 的课程目录时，才额外运行旧算法库的训练 / 评估检查。旧项目原件保存在本机 `.local-archive/legacy/`，不属于克隆仓库的必需依赖。
