# 05 · 配置与环境变量

> Onboarding 第 5 篇 — 给定一个配置/排查问题, agent 应当能从这份文档定位到:
> 谁读这个 env、默认值从哪来、改它会影响 Web 还是 Phone、是否敏感。
>
> 数据来自仓库实测 (grep `os.environ` / `process.env`), **不是** 从 Tech Design 抄。

## 1. `.env` 总览

- 服务侧 **bot.py** (Python) 与 **voice-server** (Node) 共享同一份 `/opt/voicebot/.env`,
  通过两个 systemd unit 各自的 `EnvironmentFile=/opt/voicebot/.env` 注入进程。
  见 [`deploy/cloudformation.yaml`](../../deploy/cloudformation.yaml) `voicebot.service` /
  `voiceserver.service` 段。
- 这份 `.env` **由 CloudFormation user-data 在 EC2 boot 时写一次**,
  内容是 user-data 里的 `cat > /opt/voicebot/.env <<EOF ... EOF` 段。
  之后修改有两条路径 (详见 [03-runbook §3 SSM 热更新](03-runbook.md)):
  - **SSM 直接编辑** `/opt/voicebot/.env` + `systemctl restart voicebot voiceserver` — 不会重跑 user-data
  - **重跑 deploy.sh + Instance replace** — 会重新生成
- 仓库根目录 [`.env.example`](../../.env.example) 是给本地开发者参考用的种子,
  **生产 `.env` 不来自这个文件**, 所以两份内容会漂移 (见本文末尾"已知漂移")。
- `deploy/deploy.sh` 在打 tarball 时显式 `--exclude='.env'`, **不会** 把本地 `.env` 推到 EC2。

## 2. 环境变量分组清单

> 影响路径: **Web** = `/ws` 浏览器入口; **Phone** = `/phone/ws` PSTN 入口; **All** = 两者都看;
> **VS** = 仅 voice-server 进程读。
>
> 安全级别: **🔴 secret** (必须 Secrets Manager 或 NoEcho); **🟡 sensitive** (避免明文外传);
> **⚪ public** (没敏感性)。
>
> "实测来源" 对应 grep 命中的代码位置, 用以反幻觉。

### 2.1 核心 / AWS

| name | 默认值 | 必需? | 作用 | 影响 | 安全 |
|---|---|---|---|---|---|
| `AWS_REGION` | `us-east-1` | 否 (有 fallback) | Bedrock / Transcribe / Polly / boto3 区域 | All | ⚪ |
| `SITE_PASSWORD` | `""` (空 = 不鉴权) | 否 | 整站 Basic Auth 密码 + WS 密码; 留空则关闭鉴权 | Web | 🔴 secret |
| `ADMIN_PASSWORD` | `""` (空 = admin 关闭) | 否 | 独立的 Admin UI Basic Auth 密码; 控制 `/admin/` 与 `/api/admin/*`. 空值时返回 503 (避免空密码暴露) | Admin | 🔴 secret |

实测来源:
- `bot.py:86` `SITE_PASSWORD = os.environ.get("SITE_PASSWORD", "").strip()`
- `bot.py` runtime config 段 `ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "").strip()`
- `bot.py:1300/1416/1591` `os.environ.get("AWS_REGION", "us-east-1")`

### 2.2 MiniMax (TTS, 仅 pipeline 模式 / 海外版账号)

| name | 默认值 | 必需? | 作用 | 影响 | 安全 |
|---|---|---|---|---|---|
| `MINIMAX_API_KEY` | (无 fallback, 必须存在) | 是 (用 MiniMax 时) | MiniMax HTTP API key | Phone (pipeline) + Web (provider=minimax) | 🔴 secret |
| `MINIMAX_BASE_URL` | `https://api.minimax.chat/v1/t2a_v2` | 否 | MiniMax 端点 (海外版); 不要换成 `api.minimaxi.chat` (那是国内版, 国际账号鉴权失败) | All | ⚪ |
| `MINIMAX_MODEL_DEFAULT` | `speech-2.8-turbo` | 否 | UI 不传 minimax_model 时的默认 | All | ⚪ |
| `MINIMAX_GROUP_ID` | `""` (空) | 否 | MiniMax group_id; **⚠️ 如果设了空字符串 `""` 而不是不设 / unset, MiniMax 会按"未知账户"处理, 报 401 / "insufficient balance"** | All | 🟡 |

> ⚠️ **MiniMax GroupId 空字符串陷阱**: 注意 "未设" (env 不存在) 和 "设为空字符串" 行为不同。
> 海外版账号通常不需要 GroupId, **请直接不写这个 env 行**, 不要写 `MINIMAX_GROUP_ID=` 这样的空值。
> 见 [03-runbook §5 Hotfix 6](03-runbook.md) 故障案例。

实测来源:
- `bot.py:1224` `os.environ["MINIMAX_API_KEY"]` (无 fallback, 缺失会抛 KeyError)
- `bot.py:1225` `os.environ.get("MINIMAX_GROUP_ID", "")`
- `bot.py:1226` `os.environ.get("MINIMAX_BASE_URL", "https://api.minimax.chat/v1/t2a_v2")`
- `bot.py:516` `os.environ.get("MINIMAX_MODEL_DEFAULT", "speech-2.8-turbo")`

> 注意: 当前 CFN user-data 写的是 `MINIMAX_MODEL=speech-2.8-turbo`, 但 bot.py 实际读的是
> `MINIMAX_MODEL_DEFAULT`。这是一处**已知漂移**(见末尾)。`MINIMAX_MODEL=` 在生产环境里被忽略,
> bot.py fallback 到硬编码默认值 `speech-2.8-turbo` (恰好相同, 所以没暴露)。

### 2.3 电话呼入默认 (PHONE_*)

> 这一组只影响 PSTN 呼入路径 `/phone/ws` (Chime VC 不能传 query 参数), 不影响 Web。
> Web 端用 `bot.py` 顶层常量 `DEFAULT_*` 作为页面初始默认 (见 §3 默认值优先级)。

| name | 默认值 (CFN 写入) | 必需? | 作用 | 影响 | 安全 |
|---|---|---|---|---|---|
| `PHONE_ENGINE` | `nova-sonic` | 否 (fallback `DEFAULT_ENGINE`) | `nova-sonic` 走端到端 S2S, `pipeline` 走 STT+LLM+TTS | Phone | ⚪ |
| `PHONE_LANG` | `en-US` | 否 (fallback `DEFAULT_LANG`) | 同 LANGUAGES key (`en-US`/`zh-HK`/`zh-CN`/`ja-JP`) | Phone | ⚪ |
| `PHONE_SCENARIO` | `acme-security-support` | 否 (fallback `DEFAULT_SCENARIO`) | 普通 SCENARIOS key 或 KB_SCENARIOS key | Phone | ⚪ |
| `PHONE_VOICE` | `tiffany` | 否 (fallback `DEFAULT_MINIMAX_VOICE`) | 引擎对应音色 ID; nova-sonic 走 NOVA_SONIC_VOICES, pipeline+minimax 走 MINIMAX_VOICES, pipeline+polly 走 POLLY_VOICES | Phone | ⚪ |
| `PHONE_PROVIDER` | `minimax` | 否 (fallback `DEFAULT_PROVIDER`) | 仅 `pipeline` 模式生效; `minimax` / `polly` | Phone | ⚪ |
| `PHONE_MODEL` | `nova-2-lite` | 否 (fallback `DEFAULT_MODEL`) | 仅 `pipeline` 模式生效; Bedrock LLM key | Phone | ⚪ |
| `PHONE_MINIMAX_MODEL` | `speech-2.8-turbo` | 否 (fallback `DEFAULT_MINIMAX_MODEL`) | 仅 pipeline + provider=minimax 生效 | Phone | ⚪ |

实测来源 `bot.py:1666-1672` (七连读):
```
PHONE_ENGINE   = os.environ.get("PHONE_ENGINE",   DEFAULT_ENGINE)
PHONE_LANG     = os.environ.get("PHONE_LANG",     DEFAULT_LANG)
PHONE_SCENARIO = os.environ.get("PHONE_SCENARIO", DEFAULT_SCENARIO)
PHONE_PROVIDER = os.environ.get("PHONE_PROVIDER", DEFAULT_PROVIDER)
PHONE_MODEL    = os.environ.get("PHONE_MODEL",    DEFAULT_MODEL)
PHONE_VOICE    = os.environ.get("PHONE_VOICE",    DEFAULT_MINIMAX_VOICE)
PHONE_MINIMAX_MODEL = os.environ.get("PHONE_MINIMAX_MODEL", DEFAULT_MINIMAX_MODEL)
```

### 2.4 voice-server (Node)

| name | 默认值 | 必需? | 作用 | 影响 | 安全 |
|---|---|---|---|---|---|
| `PUBLIC_IP` | `0.0.0.0` | 是 (生产) | SDP `c=` 行通告的媒体地址, **必须**是 Chime 能从公网访问到的 EC2 IP; 写错通话能 ring 但听不到声音 | VS | 🟡 |
| `RTP_PORT_BASE` | `10000` | 否 | RTP 端口池起点, 与 Security Group inbound `10000-10999` 对应 | VS | ⚪ |
| `RTP_PORT_COUNT` | `1000` | 否 | RTP 端口池大小 = 最大并发 SIP 通话数 | VS | ⚪ |
| `PORT` | `3000` | 否 | voice-server 自带的 HTTP 健康 / 诊断端点 (`/health`, `/api/active-calls`) | VS | ⚪ |
| `PIPECAT_WS_URL` | `ws://127.0.0.1:7860/phone/ws` | 否 | Pipecat 的 phone WS endpoint; 默认走本机 7860 | VS | ⚪ |
| `MAX_CALL_DURATION_MS` | `1200000` (20 min) | 否 | 单通最大时长, 到点 voice-server 主动 hangup | VS | ⚪ |

实测来源:
- `voice-server/src/server.ts:17-20` `PORT` / `PUBLIC_IP` / `RTP_PORT_BASE` / `RTP_PORT_COUNT`
- `voice-server/src/consts.ts:5` `PIPECAT_WS_URL`
- `voice-server/src/consts.ts:14` `MAX_CALL_DURATION_MS`

> 注意: `PORT` 和 `MAX_CALL_DURATION_MS` 当前 **不在 CFN user-data 的 `.env` 里**, 仅有代码默认。
> 要调整必须 SSM 编辑 `.env` 后 `systemctl restart voiceserver`。

## 3. 默认值优先级

Web 端 (`/ws`) 三层优先级, 从弱到强:

```
bot.py 顶层常量 (DEFAULT_LANG / DEFAULT_ENGINE / DEFAULT_SCENARIO / ...)
        ↓ 被覆盖
WS query params (lang / engine / model / voice / scenario / provider / minimax_model / system / greeting)
```

> Web 端**不读** `PHONE_*` env vars。改 Web 默认的唯一办法是改 `bot.py` 顶层常量 (`DEFAULT_LANG` 等) 后重新部署 — 见 [01-code-map](01-code-map.md) 的 bot.py 段。

PSTN 端 (`/phone/ws`) 两层优先级, 从弱到强:

```
bot.py 顶层常量 (DEFAULT_LANG / ENGINE / SCENARIO / MINIMAX_VOICE / ...)
        ↓ 被覆盖
PHONE_* env vars (PHONE_ENGINE / PHONE_LANG / ...)
```

> Chime VC SIP INVITE 不携带 query params, 所以 PSTN 端没有"per-call" 第三层。要按主叫号
> 路由不同行为, 需要 `bot.py` `phone_ws_endpoint` 自行解析 `caller` 字段后分支。

## 4. 跨服务依赖 (env 来源责任表)

| env | 由谁/在哪写 | 改它怎么生效 |
|---|---|---|
| `AWS_REGION` | CFN user-data (`${AWS::Region}`) | 改 stack region 重新部署 |
| `SITE_PASSWORD` | CFN parameter `SitePassword` (NoEcho), 在 user-data 里展开到 `.env` | 重跑 `deploy.sh` 传新值; 或 SSM 编辑 `.env` 后 `systemctl restart voicebot` |
| `MINIMAX_API_KEY` | CFN parameter `MinimaxApiKey` → Secrets Manager → user-data 拉出来写到 `.env` | 同上, 或直接在 Secrets Manager 改 secret 后 SSM 重启 |
| `MINIMAX_BASE_URL` / `MINIMAX_MODEL` | CFN user-data 硬编码 | 编辑 `cloudformation.yaml` 重部署; 或 SSM 改 `.env` |
| `PHONE_*` (7 个) | CFN user-data 硬编码 | 同上 |
| `PUBLIC_IP` | CFN user-data 用 IMDS `curl http://169.254.169.254/.../public-ipv4` 在 boot 时取一次 | EC2 stop/start 后 IP 漂移; 必须 SSM 编辑 `.env` 重新填 (见 [03-runbook §5 Hotfix 8](03-runbook.md)) |
| `RTP_PORT_BASE` / `RTP_PORT_COUNT` | CFN user-data 硬编码 | 同 user-data 字段; 改时同步 SG inbound 范围 |
| `PIPECAT_WS_URL` | CFN user-data 硬编码 (本机 ws://127.0.0.1:7860) | 一般无需改 |
| `PORT` / `MAX_CALL_DURATION_MS` | **不在 user-data**, 仅有代码 fallback | SSM 编辑 `.env` 增加这两行 + `systemctl restart voiceserver` |

应当放 Secrets Manager / NoEcho 的 (避免明文留在 CFN console / 日志):
- `MINIMAX_API_KEY` ✅ 当前已经这样: CFN `MinimaxApiKey` 参数 NoEcho + 落地 Secret + user-data 拉出来
- `SITE_PASSWORD` ⚠️ 当前是 NoEcho 参数直接展开到 `.env`, 没进 Secrets Manager — 风险较低 (整站非业务密码), 但严格意义上仍可改进

## 5. 安全注意

- **不要** 把 `.env` 提交到 git。`deploy.sh` 已经 `--exclude='.env'`, 但本地编辑时仍要小心。
- **不要** 在 CFN Outputs / CloudWatch Logs / Slack 截图里直接 echo `MINIMAX_API_KEY` 或 `SITE_PASSWORD`。
- **不要** 在 CI 日志里 `env | grep MINIMAX` 这种排查方式 — 改用 `grep -E '^MINIMAX_API_KEY=' /opt/voicebot/.env | sed 's/=.*/=<redacted>/'`。
- 如果 `MINIMAX_API_KEY` 泄漏 (例如被聊天消息粘出来),
  立即在 MiniMax 控制台轮转 + 更新 Secrets Manager 里的 secret + SSM 重启 voicebot。
- 整站 Basic Auth (`SITE_PASSWORD`) 不是业务级访问控制 — 不要靠它保护客户敏感数据;
  生产线如有 PII / 财务数据流过, 应该上 ALB + Cognito 或 API Gateway + 真正的 OIDC。

## 已知漂移 (待清理)

记录, 不当作 BLOCKER:

| 位置 | 状态 |
|---|---|
| `.env.example` 里的 `BEDROCK_MODEL_ID=...` | bot.py 里 grep 不到, 已经死代码 (LLM 选型现在走 `MODELS` dict + WS query param) |
| `.env.example` 里的 `MINIMAX_VOICE=Calm_Woman` | bot.py 里 grep 不到, 实际由 `DEFAULT_MINIMAX_VOICE` 常量 + UI 选择决定 |
| `.env.example` 里的 `MINIMAX_BASE_URL=https://api.minimaxi.chat/v1/t2a_v2` | 用了**国内版**域名, 与生产 `.env` 用的 `api.minimax.chat` (海外版) 不一致 |
| CFN user-data 写 `MINIMAX_MODEL=...` 但 bot.py 读 `MINIMAX_MODEL_DEFAULT` | 名字不匹配; 当前因默认值相同 (`speech-2.8-turbo`) 没暴露 |
| `PHONE_*` env vars (PHONE_ENGINE/LANG/SCENARIO/...) | T3 之后 **不再** 被 `phone_ws_endpoint` 直接读. 仅在 bot.py import 时一次性合并到 `_RUNTIME_FALLBACK`, 用于 `config/runtime.json` 首次 seed 与 fallback. 真实运行时默认现在通过 Admin UI / `PUT /api/admin/config/phone` 编辑, 持久化在 `config/runtime.json`. 即: 改 `.env` 里的 `PHONE_ENGINE` 后只有删掉 `config/runtime.json` 重启服务才会生效. |

修复建议: 后续做一轮 cleanup, 用本文档作为 source-of-truth 重写 `.env.example` + CFN user-data。

## 相关文档

- [01-code-map](01-code-map.md) — 哪个 env 读自 bot.py 哪一段
- [02-architecture](02-architecture.md) — Web vs Phone 默认路径的整体拓扑
- [03-runbook](03-runbook.md) — SSM 编辑 `.env` 的具体步骤, GroupId 陷阱, IP 漂移修复
- [04-cost-and-risks](04-cost-and-risks.md) — 哪些 env 改错会产生计费风险
