# IT 服务台知识库 · Amazon Connect

> 面向 ITSC 团队的语音优先解决方案。
> Amazon Connect + Nova Sonic(端到端语音模型) + AWS Lambda + Case (ITSM) 工单系统。
> 身份验证用 SMS OTP — 不需要声纹注册。

---

## 1 · 整体方案

设计原则:**语音优先 → 意图识别 → 能自助就自助 → 不行就优雅升级**,全程自动开工单。

### 1.1 三大支柱

- **语音入口与身份验证** — Amazon Connect 接 PSTN/SIP 入站电话。
  身份验证用 **SMS OTP**(员工编号 + 已登记手机 + 6 位短信验证码)。
  简单可靠,员工零额外操作。

- **Nova Sonic 端到端模型** — Amazon Nova Sonic 是单个端到端语音模型,
  内置 ASR + NLU + TTS。语调自然、低延迟、支持打断,
  替代了传统的 Lex + Polly 双服务架构。

- **自动化与工单** — AWS Lambda 调 Active Directory / Entra ID 解锁,
  并自动在 Case 创建、更新、关闭工单。

### 1.2 关键指标

| 指标 | 目标 |
|---|---|
| 自助成功率 | ≥ 65% |
| 平均通话时长 | < 90 秒 |
| 工单自动化率 | 100% |
| P1 接听时长 | < 30 秒 |

---

## 2 · 参考架构

### 2.1 端到端调用链路

```
员工 → PSTN/SIP → Amazon Connect (Contact Flow / IVR)
                       │
                       ├─► Nova Sonic (端到端语音 LLM, ASR+NLU+TTS)
                       │       │
                       │       └─► AWS Lambda (业务编排)
                       │              ├─► Active Directory / Entra ID
                       │              ├─► Case (ITSM)
                       │              └─► DynamoDB (OTP 存储 / session)
                       │
                       ├─► Pinpoint / SNS (SMS OTP 投递)
                       ├─► Kinesis Video Streams ─► S3 (录音归档)
                       └─► CloudWatch + Contact Lens (分析)

       │ 路由决策
       ├─► 自助 OK → 自动结案(挂电话)
       └─► 需要真人 → Agent Workspace (CCP + 屏幕弹窗)
```

### 2.2 服务清单

| 服务 | 角色 |
|---|---|
| Amazon Connect | IVR · 路由 · 坐席桌面 |
| Nova Sonic | 端到端语音模型 |
| AWS Lambda | AD 解锁 · 工单 · 编排 |
| Pinpoint / SNS | SMS OTP 发送 |
| Contact Lens | 通话分析 · 情绪识别 |
| Case | ITSM 工单系统 |
| DynamoDB | OTP 存储 · 上下文 |
| S3 + KMS | 录音归档 · 保留策略 |

---

## 3 · 五个演示场景

ITSC 团队五种典型话务模式,每个有自己的话务流、自动化和升级策略。

### 3.1 场景一 · 电话自助解锁(全自动)

**触发**:客户提出解锁账号,且符合电话自助条件(已登记手机、政策允许)。
**路由标签**:● 全自动 · S2S 模型。

#### 流程

```
1. 入站电话 → Connect contact flow → 启动 Nova Sonic 双向 S2S 会话。
2. Nova Sonic:「您好,这里是 IT 服务台。」
3. 客户:「我账号被锁了,能帮我解锁吗。」
4. Nova Sonic 识别意图 = UnlockAccount,准备收 empId 槽位。
5. 让客户报员工编号,逐位读回确认。
6. Lambda fn-send-otp:
     - 查 AD 拿到登记手机
     - 调 Pinpoint/SNS 发 6 位 OTP
     - 写入 DynamoDB,TTL 5 分钟,最多 3 次尝试
7. Nova Sonic 让客户读出短信里的 6 位码。
8. Lambda fn-ad-unlock 调 Graph API / PowerShell 解锁。
9. 同一 Lambda 调 Case REST API:创建并自动关闭 Incident,
    Category = Access/Unlock,Caller = 已验证员工。
10. Nova Sonic 复述工单号;SNS 发条确认短信;通话结束。
```

#### 关键参数

- 身份验证:SMS OTP
- OTP 有效期:5 分钟
- 最多尝试:3 次
- 语音引擎:Nova Sonic
- 目标:零人工、< 90 秒、不需要声纹注册

#### 对话示例

> Sam:「您好,这里是 IT 服务台的 Sam,有什么可以帮您?」
> 客户:「我账号被锁了。」
> Sam:「了解,我帮您解锁。请告诉我员工编号。」
> 客户:「W123456。」
> Sam:「再确认一下,W-1-2-3-4-5-6,对吗?」
> 客户:「对。」
> Sam:「我已经发了一个 6 位短信验证码到您手机,能读给我听吗?」
> 客户:「8 2 4 1 5 7。」
> Sam:「谢谢…您账号已经解锁了,工单号 INC-0-0-1-2-3-4-5,
>      还有其他需要吗?」

---

### 3.2 场景二 · 转虚拟坐席解锁

**触发**:客户要解锁,但**不符合电话自助**(没登记手机、政策要求更强 MFA、
高风险用户组)。
**路由标签**:● 数字渠道交接。

#### 流程

```
1. 入站 → Nova Sonic 识别意图 = UnlockAccount。
2. Contact Flow 检查 contact attributes → 该客户不符合电话自助。
3. Nova Sonic:「我马上发一个安全链接到您的 Teams 或短信,
   到那里完成解锁。」
4. Lambda 通过 SNS 短信 + Teams 机器人发一次性深链(TTL 5 分钟)。
5. Virtual Agent (Copilot Studio / Amazon Q Business) 的「解锁」
   topic 接管,跑 MFA 挑战然后继续解锁流程。
6. VA 调**同一个** fn-ad-unlock Lambda — 电话和数字渠道行为一致,
   工单分类也一致。
7. 工单号和审计写回原 Connect contact 作为 attributes,统一分析。
```

#### 为什么不强行电话自助

语音 + AD 解锁需要强身份。简单解锁场景 SMS OTP 够用,
但高风险用户组要走数字渠道做更强 MFA 挑战。

---

### 3.3 场景三 · MFA 重新绑定咨询 — 教育 + 数字渠道

**触发**:客户问怎么重新绑定 MFA / 怎么换新设备。
**路由标签**:● 教育 + 数字推送。

#### 为什么不在电话上完成

绑新 MFA 是**敏感操作**,纯语音渠道做风险太大。改成:
口头讲要点 + 推详细步骤到 Teams + 短信。

#### 流程

```
1. 客户:「我换手机了,MFA 怎么重新绑定?」
2. Nova Sonic 识别意图 = MfaReRegister。
3. Sam 口头讲 3 步要点:
     - 在账号 portal 里删除旧设备
     - 打开 aka.ms/mfasetup
     - 用新认证 app 扫二维码
4. Sam:「需要我把详细步骤发给您吗?」
5. 客户确认后,Lambda 推一张 Teams 自适应卡片 + KB 深链。
6. Case 开一张 Service Request(不是 Incident),状态 Awaiting user。
7. Sam:「已经发到您 Teams,工单号 SR-0-0-0-9-8-7,有问题再来电。」
8. 48 小时还没完成,系统自动触发坐席回拨流程。
```

---

### 3.4 场景四 · 客户坚持要真人 — 优雅升级

**触发**:
- 客户说「人工」、「真人」、「找个人来」,或者
- Nova Sonic 连续两次 no-match,或者
- 情绪连续 2 轮以上偏负面。
**路由标签**:● 人工升级。

**原则**:绝不强迫自助。「随时可以说 找人工」的兜底全程都在。

#### 流程

```
1. Nova Sonic 识别 SpeakToHuman 意图(或触发兜底)。
2. Sam:「没问题,我马上帮您转给专门的同事。」
3. Contact flow 写 contact attributes:
     empId, lastIntent, otpStatus, ticketId, transcriptUri
4. 按技能 + 优先级路由队列:
     - Account / Network / Endpoint
     - VIP / 普通
5. 坐席 CCP 接听;CTI adapter 屏幕弹窗预填 Case 工单 — 第一句话
   就能上下文对齐。
6. 通话后处理(ACW)自动补完工单,坐席只做必要调整。
```

#### 语气

平静、致歉,不强推。「不好意思机器没能帮您搞定,我马上让专人来处理。」

---

### 3.5 场景五 · 严重事故(P1) — 紧急通道

**触发**:客户用关键词:
- 「生产挂了」、「production down」、「production outage」
- 「全公司都登不上」、「整个办公室都受影响」
- 「critical」、「emergency」、「紧急」
- Contact Lens 二级信号:情绪 = 强烈负面。

**路由标签**:● P1 紧急通道。

#### 流程(完全跳过自助)

```
1. 客户:「生产环境完全挂了!」
2. Nova Sonic 识别意图 = ReportIncident, severity = CRITICAL。
3. Contact Lens 确认:情绪强烈负面。
4. **跳过所有自助** — 不要问员工编号或任何非必要信息,
   速度优先于验证。
5. Lambda 并行 fan-out:
     - Case:开 P1 Incident,自动建战时室
     - PagerDuty:呼 on-call(P1)
     - Teams:战时室频道
     - 高管通知
6. Sam:「已经升级到 P1,工单号 INC-0-0-9-9-0-0-1,
   马上帮您接到值班经理。」
7. 直接接 Major Incident Manager 技能组,跳过普通队列,SLA < 30 秒。
8. Contact Lens 实时把转录推给 MIM,客户不用重复说一遍。
9. 事后:录音 + 转录归档到 S3,挂到 PIR(事后复盘)记录上。
```

---

## 4 · 路由与升级矩阵

```
入站电话
   │
   ▼
收员工编号
   │
   ▼
Nova Sonic 意图分类
   │
   ├── UnlockAccount + OTP 合资格        →  场景 1(自动解锁)
   ├── UnlockAccount + OTP 不合资格      →  场景 2(转 VA)
   ├── MfaReRegister                      →  场景 3(教育 + 推指引)
   ├── SpeakToHuman / 连续两次 no-match   →  场景 4(优雅人工)
   ├── ReportIncident severity=P1         →  场景 5(P1 紧急通道)
   └── 其他                               →  兜底:FAQ 播报 + 转人工
```

---

## 5 · 安全、合规、可观测

### 5.1 SMS OTP 身份验证

- 员工编号 + 登记手机 + 6 位 OTP
- TTL 5 分钟,最多 3 次尝试
- 限流:每个员工 10 分钟最多 1 个 OTP
- 不需要声纹注册,员工零成本

### 5.2 录音与转录

- S3 服务端加密 + KMS CMK
- Object Lock 保留策略(合规)
- Contact Lens 自动脱敏 PII(卡号、PIN、身份证号等)

### 5.3 可观测

- CloudWatch dashboard:自助率、放弃率、队列等待、P1 接听时长
- QuickSight:每周报告给 ITSC manager
- 单通话钻取:Connect contact ID → Lambda 日志 → Case 工单 → Contact Lens 转录

---

## 6 · 常见客户原话(意图训练参考)

| 客户原话 | 意图 |
|---|---|
| 「我账号被锁了」、「登不进去」、「提示尝试次数过多」 | UnlockAccount |
| 「我换新手机了 MFA 怎么办」、「认证 app 在旧手机上」 | MfaReRegister |
| 「转人工」、「找个真人」、「我要跟人说话」 | SpeakToHuman |
| 「生产挂了」、「全公司都登不上」、「这是生产事故」 | ReportIncident severity=P1 |

---

## 7 · 知识库没覆盖时怎么办

如果客户的问题不在上面 5 个场景里,也不在 FAQ 列表里,**不要瞎编**。
照实说:

> 「这个问题超出我能在电话上处理的范围,我帮您转给专门的同事。」

然后走场景四(人工升级)。
