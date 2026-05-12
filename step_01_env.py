"""
Step 01：只跑环境（先理解“交互接口”）

目标：
- 让你看到 env.reset() / env.step() 的返回值长什么样
- 理解：state / action / reward / done / info 是什么

运行：
python step_01_env.py

你应该观察什么（课堂检查点）：
- state 是一个 tuple（离散桶值），它就是 Q-Learning 的“输入”。
- reward 是一个 float，来自 env.py 的奖励函数（不是你手写的策略）。
- info 里有 sun / pressure 等原始信息，方便你验证环境是否按预期运行。
"""

import sys

from pvzlib.env import (
    ACTION_NAME,
    ACTION_PLANT_SUNFLOWER,
    ACTION_SAVE,
    SimplifiedPVZEnv,
)


def main() -> None:
    # Windows 控制台常见中文乱码：这里强制 stdout 使用 UTF-8
    # 这样你在终端运行时能看到正常中文输出
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    env = SimplifiedPVZEnv(seed=7)

    state = env.reset()
    print("初始离散 state =", state, "（这是 Q-Learning 看到的状态）")
    print("当前合法动作 =", [ACTION_NAME[a] for a in env.valid_actions()])

    # 我们先手工走几步：先种一个向日葵，然后 SAVE 几步看经济增长与压力变化
    actions = [ACTION_PLANT_SUNFLOWER, ACTION_SAVE, ACTION_SAVE, ACTION_SAVE]  #actions表示动作列表，这里循环只跑四步

    for i, a in enumerate(actions, start=1):  #enumerate表示枚举，将actions中的每个元素和索引一起返回
        next_state, reward, done, info = env.step(a)
        print(f"\n第 {i} 步动作 = {ACTION_NAME[a]}")
        print("reward =", round(reward, 3), "（环境对你这一步的打分）")   #round表示四舍五入到小数点后三位
        print("done =", done, "（True 表示这一局结束）")
        print("next_state =", next_state, "（下一步决策时看到的状态）")
        print("info =", info, "（调试信息：原始变量，便于理解）")
        if done:
            break


if __name__ == "__main__":
    main()
