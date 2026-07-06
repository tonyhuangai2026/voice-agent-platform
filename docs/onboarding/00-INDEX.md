# 00 · Onboarding 索引

> Voice Bot 项目 onboarding 套件的统一入口。读完这一份, 就知道按什么顺序读其他几份, 各自边界在哪里。

## 本套文档的目的

来自 idea `9b9ab91a` 的原始诉求 — **"详细了解 Voice Bot 项目情况, 后面会让你帮忙进行开发操作"**。
这套 5 份内容 (01–05) 把项目当前状态(代码地图 / 架构 / 部署 / 成本风险 / 配置)逐项捞出,
让接下来要动手改代码、做部署、排查 bug 的 agent 不用再重新摸索一遍。

## 目标读者

- **主**: AI agent (例如 Claude / 其他 dev agent)。文档行文偏密、术语保留, 适合一次性灌入上下文。
- **次**: 工程师 (上手交接 / 问题诊断 / on-call)。行数刻意控制, 5 份合计 ~1100 行, 一杯咖啡时间能看完。

## 阅读顺序建议

按你要做的事挑路径, 不必从头到尾:

| 我要做的事 | 推荐顺序 |
|---|---|
| 改代码 | [01-code-map](01-code-map.md) → [02-architecture](02-architecture.md) |
| 部署 / 运维 / 排查事故 | [03-runbook](03-runbook.md) |
| 配置 / 排查 env 问题 | [05-config-and-env](05-config-and-env.md) |
| 评估改动影响 / 算钱 / 看风险 | [04-cost-and-risks](04-cost-and-risks.md) |
| 完整 onboarding (新人) | 01 → 02 → 05 → 03 → 04 |

## 5 份文档简介

- [01-code-map](01-code-map.md) — 代码地图: 每个关键文件 (bot.py / voice-server / static / deploy) 的行数、关键导出、改它的时机。
- [02-architecture](02-architecture.md) — 架构图册: 7 张 ASCII 图覆盖双引擎、双入口数据流、Pipecat frame pipeline、KB 注入、打断时序、Web Monitor fan-out。
- [03-runbook](03-runbook.md) — 运维手册: 一键部署, Chime VC 4 步配置, SSM 热更新, 常用命令, 8 个已知 hotfix 三段式。
- [04-cost-and-risks](04-cost-and-risks.md) — 成本风险: 月费量级摘要 + 11 条风险清单 (描述 / 触发 / 缓解), 详细数字链回 cost-novasonic。
- [05-config-and-env](05-config-and-env.md) — 配置清单: 4 组 env (核心 / MiniMax / PHONE_* / voice-server) + 默认值优先级 + 跨服务依赖 + GroupId 陷阱。

## 外部相关文档

- [README.md](../../README.md) — 项目根 README, 功能一览 + 本地运行 + API 参考。
- [deploy/README.md](../../deploy/README.md) — 一键 CloudFormation 部署细节、Chime VC 手工步骤、销毁与故障排查。
- [docs/cost-novasonic.md](../cost-novasonic.md) — Nova Sonic v2 月度成本权威表 (token 拆解、TCO 矩阵)。

## 更新约定

这套文档**不会**自动同步代码改动 — 它是写给 onboarding 的快照, 不是测试断言。

后续如有以下结构性改动, 请手动更新对应章节:

- 新增 / 删除 endpoint → 改 [01-code-map](01-code-map.md) bot.py 段
- 新增引擎 / 引擎默认值变化 → 改 [02-architecture](02-architecture.md) 双引擎对比 + [05-config-and-env](05-config-and-env.md) PHONE_* 表
- 新增 env var → 改 [05-config-and-env](05-config-and-env.md) 对应分组表
- 新增/修复 hotfix → 改 [03-runbook](03-runbook.md) §5 hotfix 列表
- 计费维度变化 → 改 [04-cost-and-risks](04-cost-and-risks.md) + [docs/cost-novasonic.md](../cost-novasonic.md)

> 简单 PR 模板: 改完代码顺便 grep 这 5 份文档, 看是否引用了被改的文件 / 函数 / env, 是的话同步改。
