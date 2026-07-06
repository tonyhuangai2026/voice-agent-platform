# 04 · Cost & Risks

> 这份文档帮 agent 在动改动前知道**「哪条路径有钱、哪条有坑」**。
> 详细的成本拆解 (单通 token-by-token, 单价表, 月度场景区间) 在
> [../cost-novasonic.md](../cost-novasonic.md) — 本文不抄数字, 只给量级。

---

## 1 · 成本摘要

**一句话**: Nova Sonic v2 端到端模式下, 单通约 **$0.10 量级**;
1,000 通/月 (3 min/通) 含全部基础设施约 **$130 量级**; 5,000 通/月约
**$500 量级**。固定基础设施 (EC2 t3.medium 7×24 + EBS + DID 等) 约
**$30 量级**, 在低流量时占大头。

| 通量 (3 min/通) | 月度合计量级 |
|---:|---:|
|   500 通 | ~$80 |
| **1,000 通** | **~$130** |
| 3,000 通 | ~$330 |
| 5,000 通 | ~$530 |

> 精确数字 (含 Bedrock / Chime VC / 固定费的拆解, 以及 100/500/1K/3K/5K
> 五档区间表) 见 [../cost-novasonic.md](../cost-novasonic.md) 的 TL;DR 与
> §4 月度估算。汇率换算 (RMB / HKD) 也在那里。
>
> **不要把上面这张表当作合同报价**——它是给 agent 用的"有没有跑偏"sanity
> check, 实际报价以 cost-novasonic.md 为权威, 并按结算日汇率换算。

---

## 2 · 风险清单 (≥ 9 条)

每条三段式: **描述 / 触发条件 / 缓解办法**。修复操作不在这写,
若需具体改法见 [03-runbook.md](./03-runbook.md) 对应 hotfix。

### R1 · Nova Sonic v2 不支持粤语 / 普通话 / 日语

- **描述**: 内置 10 个音色 (Tiffany / Matthew / Carlos / Sofia / Beatrice /
  Lorenzo / Marie / Lennart / Ana / Amy) 全部是英 / 西 / 法 / 德 / 意 / 葡
  范围, 完全没覆盖中日韩亚洲语种
- **触发**: 客户主要业务在粤语 / 普通话 / 日语市场, 又选了 Nova Sonic v2
  端到端
- **缓解**: 切到 Pipeline 模式 (Engine B) — Transcribe + Bedrock LLM
  (Nova / Claude) + MiniMax (中粤日音色丰富) 或 Polly (中文 generative
  少, 但英语 generative 自然)。具体引擎选型见
  [02-architecture.md Diagram 2](./02-architecture.md#diagram-2--dual-engine-comparison)

### R2 · Nova Sonic system prompt 字符上限 → KB 注入风险

- **描述**: Nova Sonic v2 的 system prompt + 历史合并字符 ~22-25 K 上限,
  超过会报 `Error processing responses` 直接挂掉
- **触发**: 把大文档 (FAQ / 操作手册 / 政策) 当 system instruction 直接喂
- **缓解**: 用 `_kb_seed_messages` 把 KB 包装成**合成 user message + assistant
  ack**, 进 LLMContext 而不是 system prompt。机制图见
  [02-architecture.md Diagram 5](./02-architecture.md#diagram-5--kb-injection-flow-synthetic-user-message)

### R3 · Speech tok/sec 编码率为估算值

- **描述**: cost-novasonic.md 默认按 ~70 tok/sec 估算 Nova Sonic 的 speech
  in/out token 量, 但这不是 AWS 官方公开口径
- **触发**: 客户拿这个数字直接定预算; 实际计费时发现 ±10~30% 偏差
- **缓解**: 上线前用 CloudWatch metric `InputSpeechTokenCount` /
  `OutputSpeechTokenCount` (namespace `AWS/Bedrock`,
  `ModelId=amazon.nova-2-sonic-v1:0`) 对一通已知时长的电话做实测,
  以实测值替换估算值。命令片段见 [03-runbook.md §4](./03-runbook.md#4--常用运维命令)

### R4 · Chime VC inbound 价格非 Pricing API 公开值

- **描述**: Chime SDK Voice Connector 的 inbound minute 单价 ($0.00065/min)
  + DID 月租 ($1) 在 AWS Pricing API 里没有公开 endpoint
- **触发**: 自动化 cost script 拉 Pricing API 拉不到, 报告里少了 Chime 这部分
- **缓解**: 单价**写死**在 cost-novasonic.md 引用 Chime 公开页
  <https://aws.amazon.com/chime/chime-sdk/pricing/>; 跑成本 script 时
  Chime 部分用常量, 其他全部从 Pricing API 拉

### R5 · Claude 4.x 价格 Pricing API 暂未收录

- **描述**: Bedrock Pricing API 里 Claude 系列只到 Claude 3 Haiku / Sonnet;
  Claude Haiku 4.5 / Sonnet 4.6 没有结构化定价
- **触发**: pipeline 模式选 Claude 4.x 模型时, 自动估算工具拿不到准价
- **缓解**: 先按 Anthropic 公布价手动写常量, 等 AWS 收录 Pricing API 后
  迁回; 或临时改用 Nova 系列做估算 baseline。Nova 系列在 Pricing API 里
  齐全

### R6 · EC2 t3.medium 7×24 月度固定费占小流量大头

- **描述**: 即使 0 通话/月, 也要 ~$30 EC2 + EBS + DID; < 100 通/月时
  固定费 > 变动费
- **触发**: 客户做 POC 阶段, 流量极低, 但实例一直挂着
- **缓解**: 1) 不需要 7×24 时按需 stop EC2 (但 Chime origination 也得停否则会
  连不上); 2) 流量极低时换 t3.small (~$15/月, 但 Silero VAD + 多并发会吃紧);
  3) RI / Savings Plan 砍 30-40%

### R7 · MiniMax 海外版 `MINIMAX_GROUP_ID` 空字符串陷阱

- **描述**: MiniMax 海外版 `?GroupId=` 拼到 URL, 即使 group_id 是**空字符串**
  也会被 MiniMax 当成不同 (未充值) 账户, 返回 `insufficient balance`
- **触发**: `.env` 里写了 `MINIMAX_GROUP_ID=` (空值), 而不是不写该 env
- **缓解**: 1) `.env` 里**不写**该 env; 2) 代码侧已在
  `SimpleMiniMaxTTSService.run_tts` 检测空 group_id 时把 query string
  截掉。具体修复见 [03-runbook.md Hotfix 6](./03-runbook.md#hotfix-6--minimax-minimax_group_id-空字符串陷阱)

### R8 · CFN `aws cloudformation deploy` 不重跑 user-data

- **描述**: 改了 bot.py 后重新 `./deploy.sh`, EC2 上代码可能没变 — CFN
  只在 instance 属性改变时 replace EC2, user-data 不会自动重跑
- **触发**: 修代码后只跑 deploy.sh, 不跑 SSM 推送, 业务行为没生效
- **缓解**: 改完代码用 SSM 热更新流程把 tarball 推 EC2 + tsc + restart。
  具体步骤见 [03-runbook.md §3 SSM 热更新](./03-runbook.md#3--ssm-热更新-绕开-cfn-user-data-不重跑) +
  [Hotfix 7](./03-runbook.md#hotfix-7--cfn-deploy-不重跑-user-data)

### R9 · EC2 stop/start 后公网 IP 漂移

- **描述**: CFN 默认 EC2 没挂 EIP, 重启 / replace 后公网 IP 变化, Chime VC
  origination 仍然指向旧 IP, 拨电话进 SIP 直接超时
- **触发**: 任意 EC2 reboot / replacement 事件之后没同步更新 origination
- **缓解**: 1) 部署后立即 `aws chime-sdk-voice put-voice-connector-origination`
  同步新 IP; 2) 长期方案给 EC2 挂 EIP (CFN template 加 `AWS::EC2::EIP`)
  彻底固定 IP。具体见 [03-runbook.md Hotfix 8](./03-runbook.md#hotfix-8--ec2-公网-ip-漂移--chime-vc-origination-失效)

### R10 · CloudFront 出网超 1 TB 后开始计费

- **描述**: AWS 免费层每月 CloudFront 出网 1 TB / 1000 万次请求, 超出后
  按 ~$0.085/GB 算
- **触发**: 大量音频 streaming 到浏览器 (Web Talk + 大量 Monitor 监听)
  累计超 1 TB
- **缓解**: 1) 监控用 CloudWatch metric `BytesDownloaded`; 2) 把音频从
  Web 改成单独 path (例如 ALB) 走非计费链路; 3) 提前用 Cost Anomaly
  Detection 设警

### R11 · 通话不落盘 → 出问题难排查 / 无审计

- **描述**: bot.py 默认全部通话内存里跑, 通话结束后 ASR / LLM / TTS 内容
  都丢, 只有 Web Monitor 实时看才能复盘
- **触发**: 客户投诉 / 法务要审计 / 性能调优需要回放
- **缓解**: 加 Kinesis Data Stream 把 EventBroadcaster 的 JSON 事件流出去,
  落 S3 + KMS 加密; 或简单点, bot.py 写一份 jsonl 文件到 EBS 然后定期
  rsync 到 S3

---

## 3 · 还会去哪里看

- 详细成本拆解 / 单通 token / 月度区间表: [../cost-novasonic.md](../cost-novasonic.md)
- 风险对应的修复操作: [03-runbook.md](./03-runbook.md) §5 hotfix 清单
- 配置陷阱 (env 层面): [05-config-and-env.md](./05-config-and-env.md)
- 引擎选型 (语种 → 引擎): [02-architecture.md Diagram 2](./02-architecture.md#diagram-2--dual-engine-comparison)
