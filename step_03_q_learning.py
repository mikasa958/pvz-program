"""
Step 03：Q-Learning（作业核心 AI 优化）

目标：
- 写出最小 Q-Learning 训练循环
- 观察训练曲线的「后段平均值」是否提高
- 用贪心策略（epsilon=0）评估训练后的平均表现

说明：本步只有 AI（Q-learning），不含 Rule 常规对照；要做完整对照请用 step_04。

运行（在 pvz_ai_course 目录下）：
python step_03_q_learning.py

输出：experiments/{RUN_ID}_train.csv，并在 summary.csv 追加一行。
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from save_experiment_csv import append_summary_row, save_training_curve

from pvzlib.agents import QLearningAgent, QLearningConfig
from pvzlib.env import SimplifiedPVZEnv
from pvzlib.train import evaluate_q, tail_mean, train_q_learning

RUN_ID = "step03_default"
TRAIN_EPISODES = 5000
EVAL_EPISODES = 300
ENV_SEED = 7


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    env = SimplifiedPVZEnv(seed=ENV_SEED)

    q_cfg = QLearningConfig(
        alpha=0.12,
        gamma=0.96,
        epsilon=1.0,
        epsilon_min=0.05,
        epsilon_decay=0.999,
        seed=2026,
    )
    agent = QLearningAgent(q_cfg)

    print("开始训练 Q-Learning...（训练时会探索，所以每次运行结果可能略有波动）")
    curve = train_q_learning(env, agent, episodes=TRAIN_EPISODES)
    print("训练结束。")

    tail200 = round(tail_mean(curve, n=200), 2)
    print("最后 200 局平均总奖励 =", tail200, "（训练后段是否变好）")

    score, score_std = evaluate_q(env, agent, episodes=EVAL_EPISODES)
    print("Q-Learning（贪心）平均总奖励 =", round(score, 2), "（评估时 epsilon=0）")

    csv_path = save_training_curve(RUN_ID, curve)
    append_summary_row(
        {
            "run_id": RUN_ID,
            "date": date.today().isoformat(),
            "script": "step_03_q_learning.py",
            "env_seed": ENV_SEED,
            "agent_seed": agent.cfg.seed,
            "train_episodes": TRAIN_EPISODES,
            "eval_episodes": EVAL_EPISODES,
            "alpha": agent.cfg.alpha,
            "gamma": agent.cfg.gamma,
            "epsilon_decay": agent.cfg.epsilon_decay,
            "exploration": agent.cfg.exploration,
            "boltzmann_tau_start": agent.cfg.boltzmann_tau
            if agent.cfg.exploration == "boltzmann"
            else "",
            "boltzmann_tau_min": agent.cfg.boltzmann_tau_min
            if agent.cfg.exploration == "boltzmann"
            else "",
            "boltzmann_tau_decay": agent.cfg.boltzmann_tau_decay
            if agent.cfg.exploration == "boltzmann"
            else "",
            "q_update": agent.cfg.q_update,
            "tail_mean_last200": tail200,
            "eval_mean": round(score, 2),
            "eval_std": round(score_std, 2),
            "rule_mean": "",
            "note": "step03_only_no_rule_baseline",
        }
    )
    print("已保存训练曲线:", csv_path)
    print("已在 experiments/summary.csv 追加一行（run_id=", RUN_ID, "）", sep="")

    print("\n建议你写报告时做两件事：")
    print("- 画出 curve（每局总奖励）随训练变化的曲线图")
    print("- 完整「常规 vs AI」对照请运行 step_04_experiment.py")


if __name__ == "__main__":
    main()
