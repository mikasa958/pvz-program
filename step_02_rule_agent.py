"""
Step 02：加入规则策略（Baseline）

目标：
- 学会把“决策逻辑”封装成 agent.act(env)
- 得到一个可对照的 baseline 分数（写报告要用）

运行：
python step_02_rule_agent.py

你应该观察什么（课堂检查点）：
- baseline 分数是“对照组”，后面所有 AI 的提升都要和它比。
- 规则策略参数（sunflower_target / defend_pressure_*）会明显影响分数；
  这也说明“手调规则”很费劲，而 AI 的价值在于能自动学到更好的平衡。
"""

import sys

from pvzlib.agents import RuleAgent, RuleAgentConfig
from pvzlib.env import SimplifiedPVZEnv
from pvzlib.train import evaluate_rule


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):   #如果sys.stdout有reconfigure方法，则重新配置编码
        sys.stdout.reconfigure(encoding="utf-8")  #重新配置编码为utf-8

    env = SimplifiedPVZEnv(seed=7)

    # 你可以改这些参数，看 baseline 怎么变化（这也能写进报告）
    #
    # 这组参数刻意让策略“更像新手”：
    # - sunflower_target 很高：前期过度贪经济
    # - defend_pressure_* 很高：防守反应偏慢
    #
    # 好处：
    # - 作为对照组更合适（baseline 不应该被你手工调成接近最优）
    # - 这样你更容易在报告中展示：Q-Learning 通过训练学到了更好的权衡
    rule_cfg = RuleAgentConfig(
        sunflower_target=8,
        defend_pressure_pea=7.5,
        defend_pressure_wall=9.5,
    )
    agent = RuleAgent(rule_cfg)  #创建规则策略智能体

    score = evaluate_rule(env, agent, episodes=300)  #评估规则策略智能体，返回平均总奖励
    print("Rule-Based baseline 平均总奖励 =", round(score, 2))
    print("提示：这个分数稍后会用来和 Q-Learning 做对比。")


if __name__ == "__main__":
    main()
