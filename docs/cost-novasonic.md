# Nova Sonic v2 电话语音机器人 — 月度成本估算

> **场景**：客户使用 Nova Sonic v2 端到端语音模型 + ACME Security 技术支持 KB
> 场景，电话呼入路径（Chime SDK Voice Connector → SIP/RTP →
> voice-server → bot.py /phone/ws）。
>
> **基准用量**：1,000 通/月，每通 3 分钟，主叫/机器人各说一半。
>
> **区域**：us-east-1。所有价格基于 AWS Pricing API 实时拉取（拉取日
> 2026-05-15）。Chime SDK Voice Connector 与 Claude 4.x 的部分价格在
> Pricing API 中暂未公开，使用官方公布价。

---

## TL;DR

| 通量 | 通话总时长 | Bedrock Nova Sonic | Chime VC 通话费 | 固定基础设施 | **月度合计** |
|---:|---:|---:|---:|---:|---:|
|   500 通 | 1,500 min | $48.35 | $0.97 | $32.97 | **$82.30** |
| **1,000 通** | **3,000 min** | **$96.70** | **$1.95** | **$32.97** | **$131.62** |
| 3,000 通 | 9,000 min | $290.10 | $5.85 | $32.97 | **$328.92** |

**单通成本 ≈ $0.10**（含全部基础设施摊薄前的纯变动费 $0.0986）。

---

## 1. 架构与计费组件

```
PSTN 来电
   │
   ▼ SIP+RTP (UDP 5060 / 10000-10999)
┌────────────────────────────────┐
│  Chime SDK Voice Connector     │  ← 按 inbound 分钟数计费 + DID 月租
└────────────────────────────────┘
   │
   ▼
┌────────────────────────────────┐
│  EC2 t3.medium (us-east-1)     │  ← 固定月费 (7×24 在线)
│  ├─ voice-server (Node SIP)    │
│  └─ bot.py (Pipecat)           │
└────────────────────────────────┘
   │
   ▼  双向流式 (binary stream)
┌────────────────────────────────┐
│  Bedrock Nova Sonic v2         │  ← 按 token 计费 (speech in/out + text in/out)
└────────────────────────────────┘
```

涉及的 AWS 计费项目：

| 类别 | 服务 | 计量 |
| --- | --- | --- |
| 固定 | EC2 t3.medium | per hour |
| 固定 | EBS gp3 20 GB | per GB·month |
| 固定 | Secrets Manager | per secret/month + per API request |
| 固定 | Chime VC US DID | per number·month |
| 固定 | S3 (deploy 桶) | per GB·month |
| 变动 | Bedrock Nova Sonic v2 | per 1K tokens（speech in/out, text in/out 各一档） |
| 变动 | Chime VC inbound | per minute |
| 变动 | CloudFront 出网 | 1 TB 内免费，超出按 GB |

> 备注：**Polly/Transcribe 在 Nova Sonic 模式下不计费**——Nova Sonic v2
> 端到端处理 audio in/out，不经过单独的 STT/TTS 服务。

---

## 2. 单价（us-east-1, on-demand）

来源：AWS Pricing API（除特别注明外）。

### Bedrock Nova Sonic v2

| 维度 | 单价 |
|---|---|
| Speech understanding **input** token | **$0.0030 / 1K tok** |
| Speech understanding **output** token | **$0.0120 / 1K tok** |
| Text **input** token | $0.000330 / 1K tok |
| Text **output** token | $0.002750 / 1K tok |

**Token 换算**：电话音频以 **~70 tok/sec** 编码（AWS 文档口径）。
即 60 秒电话 ≈ 4,200 speech tokens。

### Chime SDK Voice Connector（电话）

| 维度 | 单价 |
|---|---|
| Inbound calling（VC 把 PSTN 入站接到 SIP trunk） | **$0.00065 / 分钟** |
| US 本地号码（DID）月租 | **$1.00 / 月** |

> Chime VC 这两项 Pricing API 没有公开 endpoint，价格摘自
> <https://aws.amazon.com/chime/chime-sdk/pricing/>。

### 基础设施（固定）

| 项 | 单价 | 月度 |
|---|---|---:|
| EC2 t3.medium on-demand | $0.0416/hr | **$29.95** |
| EBS gp3 20 GB | $0.08/GB·月 | **$1.60** |
| Secrets Manager（1 个 MiniMax key） | $0.40/secret | **$0.40** |
| S3 deploy 桶（< 1 GB tarballs） | $0.023/GB | **~$0.02** |
| Chime VC US DID（+1 号码） | $1.00/号月 | **$1.00** |
| CloudFront 出网 | 1 TB 免费 / 超出 $0.085/GB | **$0** （场景内） |
| **固定小计** |  | **$32.97/月** |

---

## 3. 单次通话成本（3 分钟 / 用户与机器人各说 1.5 分钟）

### 3.1 Token 用量

| 项 | 量 | 计算 |
|---|---:|---|
| Speech in tokens | 6,300 | 1.5 min × 60 sec × 70 tok/sec |
| Speech out tokens | 6,300 | 1.5 min × 60 sec × 70 tok/sec |
| Text in tokens | ~5,000 | system prompt + ACME Security KB（26K 字符 ≈ 6.5K tok）+ 对话历史摊到本通 |
| Text out tokens | ~200 | Nova Sonic v2 同时输出的少量 narration text |

### 3.2 单价 × 用量

| 项 | 计算 | 单通 |
|---|---|---:|
| Speech in | 6,300 × $0.0030/1K | **$0.0189** |
| Speech out | 6,300 × $0.0120/1K | **$0.0756** |
| Text in | 5,000 × $0.000330/1K | $0.0017 |
| Text out | 200 × $0.002750/1K | $0.0006 |
| **Bedrock 小计** |  | **$0.0967** |
| Chime VC inbound | 3 min × $0.00065 | $0.0019 |
| **每通合计** |  | **$0.0986** |

> Speech out token 是单通最大头（占 ~76%），符合"机器人多说一句话就贵
> 一份"的直觉。如果场景里机器人话比较少（比如以听为主的咨询录音），
> 单通可压到 $0.04–0.05。

---

## 4. 月度估算（3 分钟通话）

### 4.1 主场景：1,000 通/月

| 项 | 计算 | 月度 |
|---|---|---:|
| 固定基础设施 | （见 §2） | $32.97 |
| Bedrock Nova Sonic v2 | $0.0967 × 1,000 | **$96.70** |
| Chime VC inbound | $0.0019 × 1,000 | $1.95 |
| **合计** |  | **$131.62** |

### 4.2 区间参考

| 通量 | 总通话时长 | Bedrock | Chime VC | 固定 | 合计 |
|---:|---:|---:|---:|---:|---:|
| 100 通 | 300 min | $9.67 | $0.20 | $32.97 | **$42.84** |
| 500 通 | 1,500 min | $48.35 | $0.97 | $32.97 | **$82.30** |
| **1,000 通** | **3,000 min** | **$96.70** | **$1.95** | **$32.97** | **$131.62** |
| 3,000 通 | 9,000 min | $290.10 | $5.85 | $32.97 | **$328.92** |
| 5,000 通 | 15,000 min | $483.50 | $9.75 | $32.97 | **$526.22** |

### 4.3 不同通话时长的影响（按 1,000 通/月）

| 平均时长 | Speech tok/通 | 单通成本 | 月度合计 |
|---:|---:|---:|---:|
| 1 min | 4,200 | $0.034 | $66.80 |
| 2 min | 8,400 | $0.066 | $99.21 |
| **3 min** | **12,600** | **$0.099** | **$131.62** |
| 5 min | 21,000 | $0.163 | $196.45 |
| 10 min | 42,000 | $0.323 | $358.50 |

---

## 5. 关键假设

1. **每通 3 分钟、用户与机器人各 50%**：客服 / 技术支持类对话的常见
   分布。如果机器人独白比例更高（如 IVR 通知），speech out 占比上升、
   单通成本变贵。
2. **70 tok/sec speech 编码率**：AWS 文档对 Nova Sonic v2 的口径，实际
   会有 ±10% 浮动。
3. **ACME Security KB 已注入对话历史**：每通通话 ~5K text input token 的
   假设里包含了 KB body 的 first user message。如果不用 KB 场景，text
   input 可降到 ~500 tok/通，单通省 ~$0.0015（影响很小）。
4. **EC2 7×24 在线**：低流量时（< 100 通/月）固定费占大头，按需启停
   或换 t3.small（$15/月）能砍一半。

---

## 6. 其他可能的省钱手段

| 措施 | 节省 | 备注 |
|---|---|---|
| 用 t3.small 替代 t3.medium | -$15/月 | Silero VAD 在 t3.small 上吃紧，电话场景只有 1-2 路并发时可行 |
| EC2 RI/Savings Plan（1 年） | -30~40% on EC2 | 适合稳定生产 |
| 释放未用的 Chime DID | -$1/号·月 | 测试期可省 |
| 把 Nova Sonic 换成 pipeline 模式（Transcribe + Nova 2 Lite + Polly Neural） | -10%~20% 单通 | 但延迟会变差、跨语种泛化差 |
| 短对话（< 1 分钟） | 单通 < $0.04 | 非线性，因为 speech 是主要变量 |

---

## 7. 不在估算内的费用

- **数据流出（CloudFront）**：1 TB 内免费。Web Monitor 模式纯文本事件，
  几 KB/秒；估计单 monitor 24/7 一个月 < 100 MB，远低于免费额度。
- **CloudWatch Logs**：只有 user-data bootstrap 写一次，正常运行下可忽略。
- **NAT Gateway / VPC**：方案不用 NAT，无费用。
- **WAF / Shield Advanced**：未启用。
- **MiniMax TTS**：Nova Sonic 模式不调用 MiniMax，无此费用。
- **跨区流量**：服务全部在 us-east-1。

---

## 8. 数据来源

- **AWS Pricing API**（boto3 `pricing` client）实时拉取：
  - EC2 instance / EBS（`AmazonEC2`）
  - Secrets Manager（`AWSSecretsManager`）
  - S3（`AmazonS3`）
  - Bedrock Nova Sonic v2 / Nova Lite / Nova Micro / Nova 2 Lite（`AmazonBedrock`）
  - Transcribe streaming / Polly（`transcribe` / `AmazonPolly`，参考用）
- **官方公布页**：
  - Chime SDK Voice Connector — <https://aws.amazon.com/chime/chime-sdk/pricing/>
  - Bedrock Claude 4.x — <https://aws.amazon.com/bedrock/pricing/>（Pricing API 暂未收录 Claude 4 系列）

---

## 9. 报价换算（人民币 / 港币粗略）

| 通量 | USD/月 | RMB/月 (×7.2) | HKD/月 (×7.8) |
|---:|---:|---:|---:|
| 500 通 | $82.30 | ¥593 | HK$642 |
| **1,000 通** | **$131.62** | **¥948** | **HK$1,027** |
| 3,000 通 | $328.92 | ¥2,368 | HK$2,566 |

> 实际报价请按当日汇率重算。
