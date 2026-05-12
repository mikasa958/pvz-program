"""
Step 04：对照实验（Rule-Based vs Q-Learning）

目标：
- 同一环境、同一评估方式下对比「常规规则策略」与「Q-learning」
- 输出平均总奖励与相对提升（写报告直接用）

运行（在 pvz_ai_course 目录下）：
python step_04_experiment.py

输出：
- experiments/{RUN_ID}_train.csv（Q-learning 训练曲线）
- experiments/{RUN_ID}_train.png（同曲线图，标题下含探索方式说明；需 pip install matplotlib）
- experiments/summary.csv 追加一行（含 exploration、q_update=q_learning|double_q、玻尔兹曼参数等；表头变化时会迁移到同一文件）

说明：若你只要交一份对照实验，通常只跑本脚本即可；step_03 用于分步理解 AI 训练。
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from save_experiment_csv import append_summary_row, save_training_curve

from pvzlib.agents import QLearningAgent, QLearningConfig, RuleAgent, RuleAgentConfig
from pvzlib.env import SimplifiedPVZEnv
from pvzlib.train import evaluate_q, evaluate_rule, tail_mean, train_q_learning

RUN_ID = "E07_E05+seed20"
TRAIN_EPISODES = 10000
EVAL_EPISODES = 300
ENV_SEED = 7
# 自动保存 PNG 时滑动平均窗口（与 plot_training_curve.py --window 一致）
PLOT_MA_WINDOW = 50

# ---------------------------------------------------------------------------
# 探索方式（与 pvzlib.agents.QLearningConfig 一致）
#   "epsilon_greedy" — 原版 ε-贪心（均匀随机试探）
#   "boltzmann"      — Softmax(Q/τ) 按优劣分配概率抽样（详见 agents 内注释）
# ---------------------------------------------------------------------------
EXPLORATION_MODE = "boltzmann"
BOLTZMANN_TAU = 1.5
BOLTZMANN_TAU_MIN = 0.1
BOLTZMANN_TAU_DECAY = 0.9995

# ---------------------------------------------------------------------------
# Q 更新方式：与 QLearningConfig.q_update 一致
#   "q_learning" — 单表标准 Q-learning（原版）
#   "double_q"   — 双表 Double Q-learning（减轻 max 过估计，见 agents.py）
# ---------------------------------------------------------------------------
Q_UPDATE_MODE = "q_learning"

# ---------------------------------------------------------------------------
# 小课 1：乐观初值（Optimistic Initialization）—— 只改下面这一行即可做实验
#
#   0.0   与原版完全一致：字典里没有的 (s,a) 当作 Q=0。
#   40.0  示例：没见过的 (s,a) 先当作「还不错」，早期更愿意试不同动作。
#
# 读代码顺序建议：step_04 这里 → pvzlib/agents.py 里 QLearningConfig 的说明
# → QLearningAgent._q() 那一行 .get(..., self.cfg.q_init)
# ---------------------------------------------------------------------------
Q_OPTIMISTIC_INIT = 40.0


def _exploration_png_subtitle() -> str:
    parts = [f"q_update={Q_UPDATE_MODE}"]
    if EXPLORATION_MODE == "boltzmann":
        parts.append(
            f"exploration=boltzmann | tau0={BOLTZMANN_TAU} "
            f"tau_min={BOLTZMANN_TAU_MIN} decay={BOLTZMANN_TAU_DECAY}"
        )
    else:
        parts.append("exploration=epsilon_greedy")
    return " | ".join(parts)


def _summary_exploration_columns() -> dict[str, object]:
    if EXPLORATION_MODE == "epsilon_greedy":
        return {
            "exploration": "epsilon_greedy",
            "boltzmann_tau_start": "",
            "boltzmann_tau_min": "",
            "boltzmann_tau_decay": "",
        }
    return {
        "exploration": "boltzmann",
        "boltzmann_tau_start": BOLTZMANN_TAU,
        "boltzmann_tau_min": BOLTZMANN_TAU_MIN,
        "boltzmann_tau_decay": BOLTZMANN_TAU_DECAY,
    }


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    env_rule = SimplifiedPVZEnv(seed=ENV_SEED)
    env_q = SimplifiedPVZEnv(seed=ENV_SEED)

    rule_agent = RuleAgent(
        RuleAgentConfig(
            sunflower_target=8,
            defend_pressure_pea=7.5,
            defend_pressure_wall=9.5,
        )
    )
    rule_score = evaluate_rule(env_rule, rule_agent, episodes=EVAL_EPISODES)

    q_agent = QLearningAgent(
        QLearningConfig(
            alpha=0.12,
            gamma=0.96,
            epsilon=1.0,
            epsilon_min=0.05,
            epsilon_decay=0.999,
            seed=20,
            q_init=Q_OPTIMISTIC_INIT,
            exploration=EXPLORATION_MODE,
            boltzmann_tau=BOLTZMANN_TAU,
            boltzmann_tau_min=BOLTZMANN_TAU_MIN,
            boltzmann_tau_decay=BOLTZMANN_TAU_DECAY,
            q_update=Q_UPDATE_MODE,
        )
    )
    curve = train_q_learning(env_q, q_agent, episodes=TRAIN_EPISODES)
    q_score, q_std = evaluate_q(env_q, q_agent, episodes=EVAL_EPISODES)

    csv_path = save_training_curve(RUN_ID, curve)
    try:
        from plot_training_curve import save_training_curve_png

        png_path = save_training_curve_png(
            csv_path,
            window=PLOT_MA_WINDOW,
            show=False,
            subtitle=_exploration_png_subtitle(),
        )
        print("已保存训练曲线图:", png_path)
    except ImportError as e:
        print("未安装 matplotlib，已跳过自动出图（pip install matplotlib）:", e)
    except Exception as e:
        print("自动出图失败（训练 CSV 已保存）:", e)

    tail200 = round(tail_mean(curve, 200), 2)
    append_summary_row(
        {
            "run_id": RUN_ID,
            "date": date.today().isoformat(),
            "script": "step_04_experiment.py",
            "env_seed": ENV_SEED,
            "agent_seed": q_agent.cfg.seed,
            "train_episodes": TRAIN_EPISODES,
            "eval_episodes": EVAL_EPISODES,
            "alpha": q_agent.cfg.alpha,
            "gamma": q_agent.cfg.gamma,
            "epsilon_decay": q_agent.cfg.epsilon_decay,
            **_summary_exploration_columns(),
            "q_update": Q_UPDATE_MODE,
            "tail_mean_last200": tail200,
            "eval_mean": round(q_score, 2),
            "eval_std": round(q_std, 2),
            "rule_mean": round(rule_score, 2),
            "note": (
                f"step04_rule_vs_q,q_init={Q_OPTIMISTIC_INIT},"
                f"exploration={EXPLORATION_MODE},q_update={Q_UPDATE_MODE}"
            ),
        }
    )

    print("====== 对照实验结果 ======")
    print("Q 更新方式 Q_UPDATE_MODE =", Q_UPDATE_MODE)
    print("探索方式 EXPLORATION_MODE =", EXPLORATION_MODE)
    print("Q 乐观初值 q_init =", Q_OPTIMISTIC_INIT, "（见文件顶部 Q_OPTIMISTIC_INIT）")
    print("Rule-Based 平均总奖励 =", round(rule_score, 2))
    print("Q-Learning 平均总奖励 =", round(q_score, 2))
    print("Q-Learning 最后 200 局训练均值 =", tail200)
    print("已保存训练曲线:", csv_path)
    print("已在 experiments/summary.csv 追加一行（run_id=", RUN_ID, "）", sep="")

    improve = ((q_score - rule_score) / (abs(rule_score) + 1e-6)) * 100.0
    print("相对提升 =", f"{improve:.2f}%")

    print("\n报告怎么写（可直接套用）：")
    print("- 设定 Rule-Based 为对照组（baseline）。")
    print("- 在相同环境参数和随机种子下训练并评估 Q-Learning。")
    print("- 用平均总奖励作为评价指标，给出相对提升百分比。")


if __name__ == "__main__":
    main()
