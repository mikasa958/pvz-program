# 仓库整理记录

整理日期：2026-10-22。

## 保留与去重

以原 `pvz_v5/` 为维护版本，将其源码提升到仓库根目录。原 `pvz_v5_demo2_extracted/pvz_v5/` 的 27 个源码、配置与说明文件与维护版完全一致，按 SHA-256 校验后清理；其中的可执行程序也与展示目录中的 v5 程序相同，保留展示目录的版本。

原 `成果展示.zip` 的 237 个文件逐项核对大小与 SHA-256，均与解压后的文件一致，删除冗余 ZIP。旧版目录中的虚拟环境、pip 缓存、PyInstaller 工具副本和构建中间文件一并清理。原 `tower_defense_ai_unzipped/` 只包含打包工具缓存，清理后移除空目录。

共清理 471,846,645 字节，约 450 MiB。此数字包含重复文件、重复压缩包及可重建的构建缓存。

## 目录映射

| 原位置 | 整理后位置 |
| --- | --- |
| `pvz_v5/*.py` | 根目录源码；测试移到 `tests/` |
| `pvz_v5/游戏说明书.md` | `docs/user-guide.md` |
| `汇报与方案/*.md` | `docs/plans/` |
| 汇报 Word 文件、`pvz波次设置.doc` | `docs/reports/` |
| `成果展示/pvz_v1.png` | `docs/images/pvz-v1-preview.png`，早期版本截图 |
| `integrated_td_ai_project（最终版）/integrated_td_ai/` | `.local-archive/legacy/integrated_td_ai/` |
| `成果展示/` 其余内容 | `.local-archive/showcase/` |
| 其余原始 ZIP | `.local-archive/packages/` |

独有的旧版源码、训练模型、实验结果、视频、日志和报告均保留。旧版源码代表不同实现，没有按文件名相似度合并。

`.local-archive/cleanup-manifest.json` 在本机记录移动路径、删除类型及重复文件校验值。修改过的原始环境文件、测试和 README 也保存在该归档内，便于比较和恢复。归档目录已加入 `.gitignore`。

## GitHub 文件

增加根目录 README、开发依赖、pytest 配置、保守的 Ruff 检查、换行规则和 GitHub Actions。自动验证覆盖 Linux Python 3.11 / 3.13 和 Windows Python 3.13；远程 CI 结果须上传后查看，本机验证环境为 Windows Python 3.13.9。

维护分支为 [mikasa958/pvz-program 的 main 分支](https://github.com/mikasa958/pvz-program)。本次 v5 更新接续既有提交历史，不重写历史。早期整合版、课程脚本、训练 CSV 与旧 Q 表已移出主目录，仍可在 [更新前的仓库快照](https://github.com/mikasa958/pvz-program/tree/03883034463def17d1aa0a2debf1fe45bdee2ddd) 中查看。

源码 ZIP 使用 Git 的忽略规则生成，排除本机归档、虚拟环境、日志和构建产物。

没有擅自添加许可证或作者授权信息。当前 README 已说明 F3 是模型策略接入接口，不能将其误认为预训练模型演示。

## 验证与小范围修复

整理前，现有 59 项 pytest 测试有 1 项失败，独立兼容性检查也失败。修复涉及两处波次状态判断：

- 最后一波尚有敌人时继续战斗，待清空敌人后结算，避免提前进入无后续波次可接续的强化状态。
- 已存在活动波次时，选择强化后恢复活动状态。

新增手动 / 自动强化两种情况下的最终波次回归用例，先确认两种情况均失败，再修改环境逻辑。兼容性检查同步使用当前敌人配置字段，捕获放置动作本身触发的自动强化信息，并为“清场后升级”的用例明确设置清场条件。

验证结果：

- pytest：61 项通过。
- 独立兼容性检查：通过；未安装的可选外部 `pvzlib` 集成检查明确跳过。
- Ruff 语法与未定义名称检查：通过。
- 独立导出包：解压后重复通过上述检查，确认不依赖本机历史归档。
- 训练脚本：运行 3 个 stage 0 episode，成功生成 JSON Q 表，非法动作计数为 0。此短运行仅验证训练链路，不作为模型性能评估。
- 游戏入口：在 SDL dummy 驱动下完成初始化、3 帧循环和退出；未进行人工图形交互测试。
- 上传候选文件：49 个，约 6.4 MiB；内容哈希检查未发现重复文件，常见密钥模式扫描无命中。

Windows 可执行程序未重新打包；原有可执行程序属于历史演示文件，不包含本次源码修复。
