# 01 — Code Map

> 一份给 AI Agent 用的"哪改在哪"地图。读完这份, 给定一个修改诉求 (改打断逻辑 / 加一个 TTS / 调
> 端到端引擎默认值) 应当能直接 jump 到目标文件 + 函数。

行数全部用 `wc -l` 实测。最后实测时间见 git log。

---

## Python 主服务 (FastAPI + Pipecat)

### `bot.py` (1,778 行)

整套服务的单点真相, FastAPI 路由 + Pipecat pipeline 构造 + 4 个 TTS 实现 + 所有默认值 / KB 注入。

- **角色**: HTTP/WS 入口 (FastAPI app)、双引擎 (Nova Sonic v2 / Pipeline) 构造、监控广播。
- **7 个 endpoint** (`@app.*` 装饰器):
  - `GET /` — `app.mount("/", StaticFiles(directory="static/admin/dist", html=True))` 挂在文件末尾, 服务合并后的 admin 单页 SPA
  - `GET /api/config` (1516) — UI 拉取语言 / 模型 / 音色 / 场景
  - `POST /api/summary` (1561) — 用 Bedrock LLM 对历史做总结
  - `WS /ws` (1618) — Web 客户端 16 kHz PCM 双向
  - `GET /api/calls` (1675) — Monitor UI 拉活跃通话列表
  - `WS /phone/ws` (1689) — voice-server 入口 (16 kHz PCM, 不校验 SitePassword)
  - `WS /monitor/ws` (1736) — 多浏览器只读事件流
- **关键构造函数**:
  - `_build_nova_sonic_pipeline(...)` (1276) — 端到端 S2S, 走 Bedrock Nova Sonic v2
  - `_build_pipeline(...)` (1390) — 三段式 STT (Transcribe) → LLM (Bedrock) → TTS (MiniMax/Polly)
  - `_build_tts(...)` (1192) — 在 pipeline 模式下选 TTS provider
- **关键工具/类**:
  - `EventBroadcaster` (1087) — Pipecat observer, 把 frame → JSON event 广播给 ws/monitor
  - `RawPCMSerializer` (1165) — Pipecat 的 binary frame 编解码 (PCM 直通)
  - `SimpleMiniMaxTTSService` (256) — 自实现 MiniMax TTS (Pipecat 自带版有 group_id 空字符串 bug)
  - `SimplePollyTTSService` (394) — 自实现 Polly TTS (Pipecat 自带版在 pipeline 模式下不出 frame)
  - `_kb_seed_messages(...)` (930) — 把 KB 文档以 user/assistant 首轮形式注入 LLMContext
  - `_resolve_kb_scenario / _resolve_system_greeting` (1234, 1253) — 场景 / 提示词解析
- **顶层默认常量** (`DEFAULT_*`, 影响 Web `/ws` 默认行为):
  - `DEFAULT_LANG="en-US"` (177), `DEFAULT_MODEL="nova-2-lite"` (178), `DEFAULT_PROVIDER="minimax"` (507),
    `DEFAULT_NOVA_SONIC_VOICE="tiffany"` (532), `DEFAULT_ENGINE="nova-sonic"` (541),
    `DEFAULT_SCENARIO="acme-security-support"` (747)
- **PHONE_\* 默认**: 自 T3 起仅在 import 时一次性合并到 `_RUNTIME_FALLBACK`, 不再被 `phone_ws_endpoint` 直接读. 真正的运行时默认走 `RUNTIME_CONFIG`. 见 `05-config-and-env.md`
- **运行时配置层** (T3+):
  - `RUNTIME_CONFIG = RuntimeConfig(...)` 模块单例, fallback 来自顶层常量 + PHONE_* env 一次性快照
  - `/ws` / `/phone/ws` / `/api/config` 都读 `RUNTIME_CONFIG.get_*_defaults()` (per-call 粒度)
  - 7 个 admin endpoint (`/api/admin/*`) + `admin_path_guard` middleware (ADMIN_PASSWORD Basic Auth)
  - `DEMO_LOADER = DemoLoader(...)` 模块单例, scan `data/<demo>/manifest.yaml + kb.md`
  - `_kb_seed_messages` / `_resolve_kb_scenario` 都先查 demo_loader, 未命中再 fallback 到 KB_SCENARIOS
- **何时改它**:
  - 加新引擎 / 切换默认引擎 → `DEFAULT_ENGINE` + `_build_*_pipeline` + Admin UI 改默认
  - 改打断逻辑 → 找 `LLMUserAggregatorParams` / `SileroVADAnalyzer` / `SpeechTimeoutUserTurnStop` 在两个 build 函数里
  - 加新 TTS provider → 仿 `SimpleMiniMaxTTSService` / `SimplePollyTTSService`, 在 `_build_tts` 里加分支
  - 加新 endpoint → 在 1500+ 区域加 `@app.*`
  - 加新业务场景 → 直接 `mkdir data/<demo>/` + manifest.yaml + kb.md, 不用改代码 (见 03-runbook §6.4)
  - 改 Web 监听协议 → `RawPCMSerializer` + `WS /ws` handler

### `runtime_config.py` (158 行, T3 新增)

运行时配置层, JSON 文件 (`config/runtime.json`) 持久化 + 内存缓存 + atomic write. 提供
`get_web_defaults / get_phone_defaults / update_web / update_phone / reload` 五个公开方法.
单测 `tests/test_runtime_config.py` (6 个).

### `demo_loader.py` (132 行, T2 新增)

扫描 `data/<demo>/` 子目录, 把 `manifest.yaml + kb.md` 加载成 demo 对象. 提供
`list / get(id) / rescan` 三方法. 校验失败的 manifest log warning + 跳过, 不让服务崩.
单测 `tests/test_demo_loader.py` (8 个, 含与 KB_SCENARIOS byte-equal 回归).

### `smoke_bedrock.py` (34 行) / `smoke_minimax.py` (96 行) / `smoke_polly.py` (64 行) / `smoke_transcribe.py` (89 行)

四个独立连通性测试。每个文件直接 `python smoke_*.py` 跑, 验证对应外部服务的最小调用链 (auth +
一次 invoke + 输出落地)。当线上服务出问题时第一步: 先确认 smoke 能过。本地开发新加 provider
时也建议先写个 smoke。

---

## Node 电话桥 (SIP/RTP → Pipecat)

### `voice-server/src/server.ts` (154 行)

Node 服务总入口, 把 SIP 来电的 RTP 流转发到 bot.py 的 `/phone/ws`, 并接事件做 barge-in mute。

- **角色**: 进程 main, SIP UAS 注册 + 来电 fan-out
- **关键回调**:
  - `sipServer.onIncomingCall(call => …)` — 每个来电创建 PipecatClient, 把 RTP 包通过 `client.sendPCM8(pcm8)` 转发
  - `client = new PipecatClient(...)` 的 `onEvent` — 收到 `user_speaking=true` / `asr_partial` / `asr_final` 调 `rtpSession.setMuted(true)`; 收到 `llm_start` / `tts_start` / `user_speaking=false` 解 mute
  - `endCall(reason)` — 清队列、断 ws、结束 SIP dialog
- **何时改它**:
  - 改打断 trigger (mute / unmute 时机) → 这里的 `onEvent` 分支
  - 改 max call duration → `MAX_CALL_DURATION_MS` env (在 `consts.ts`)
  - 加并发上限 / 准入策略 → `sipServer.onIncomingCall` 入口处加判断

### `voice-server/src/sip/sip-server.ts` (420 行)

SIP UAS 实现, 处理 INVITE / ACK / BYE / OPTIONS / CANCEL 等信令。最大、最绕的文件。

- **角色**: SIP 协议状态机
- **导出**: `class SipServer { onIncomingCall, endCall, start, stop }`
- **关键方法**: `handleInvite`, `handleAck`, `handleBye`, `sendResponse`, `cleanupDialog`
- **何时改它**: 不正常的 SIP 信令兼容性问题、Chime VC 与某 carrier 不通; 一般不需要动。

### `voice-server/src/sip/rtp-session.ts` (250 行)

每路通话一个 `RtpSession`, 负责 RTP 包收发 + μ-law 编解码 + outbound queue + **mute 模式 (barge-in 关键)**。

- **角色**: RTP 协议层 + mute 状态机
- **关键方法**:
  - `start() / stop()` — bind UDP socket
  - `setRemote(ip, port)` — 从 SDP 学到对端
  - `sendAudio(pcm)` — 入队 outbound (mute 时直接丢)
  - `setMuted(boolean)` — barge-in 进入 / 退出静音, mute=true 时清队列且后续 sendAudio 全丢
  - `clearQueue()` — 清空但不进 mute (历史接口, 现在主要用 setMuted)
- **何时改它**:
  - 改打断行为 (清队列 vs 拒收 vs 衰减) → `setMuted` / `sendAudio`
  - 改 codec (假如要支持 OPUS) → `decode/encode μ-law` 调用处
  - 调 outbound queue 长度上限 → `sendAudio` 的 enqueue 处

### `voice-server/src/sip/sdp-parser.ts` (85 行)

SDP body 解析, 抽出对端 IP / RTP port / payload type。被 `sip-server.ts` 调用。一般不动。

### `voice-server/src/sip/sip-parser.ts` (172 行)

SIP message 文本解析 (request line / headers / body 切分)。被 `sip-server.ts` 调用。一般不动。

### `voice-server/src/sip/port-pool.ts` (47 行)

RTP 端口池 (默认 10000-10999), 每路通话从池中分一个 even port (RTP) + odd port (RTCP)。一般不动。

### `voice-server/src/sip/index.ts` (5 行)

barrel export, 把上面 5 个文件的公共 API 集中导出。

### `voice-server/src/pipecat-client.ts` (105 行)

把 RTP 流转发到 bot.py 的 `/phone/ws` WebSocket 客户端。Nova Sonic v2 必须 16 kHz 输入, 这里
做 8 → 16 kHz 上采样后再发。

- **导出**: `class PipecatClient { connect, sendPCM8, sendEvent, close, on('event'|'audio'|...)  }`
- **关键方法**:
  - `connect()` — 建 ws, 注册 binary / text 帧 handler
  - `sendPCM8(pcm8: Buffer)` — **关键**: 调 `upsample8to16` 后 `ws.send(pcm16)`. 之前直接转 8 kHz 会让 Nova Sonic 报 "Timed out waiting for audio bytes"
  - 收 binary 帧 (24 kHz PCM) → 触发 `on('audio')` → server.ts 调 `rtpSession.sendAudio` (内部 24→8 kHz)
  - 收 text 帧 (JSON event) → `on('event')` → 用于 mute / unmute 判断
- **何时改它**: 上下行采样率改动 / 加 ws 重连 / 加 backpressure。

### `voice-server/src/audio-utils.ts` (35 行)

无状态采样率转换工具。

- **导出**: `upsample8to16(pcm8) → pcm16`, `downsample24to8(pcm24) → pcm8`, `μlawDecode/Encode`
- **何时改它**: 加新采样率 / 换更高质量 resampler。

### `voice-server/src/types.ts` (33 行)

通用 TS 类型 (`AudioEvent`, `RtpInfo`, ...)。一般不动。

### `voice-server/src/consts.ts` (14 行)

env-driven 常量: `PIPECAT_WS_URL`, `MAX_CALL_DURATION_MS`, `CHIME_SAMPLE_RATE` (8000),
`PIPELINE_INPUT_SAMPLE_RATE` (16000), `PIPELINE_OUTPUT_SAMPLE_RATE` (24000)。

- **何时改它**: 默认值微调, 添加新 env (建议同步 `05-config-and-env.md`)。

---

## 前端

### `static/admin/` (Vue 3 + Naive UI — 单页合并后的唯一 SPA)

合并后的单页 SPA, FastAPI 在根 `/` mount (catch-all, 必须在所有 `@app.*` endpoint
之后否则会 shadow `/api/*` + WS). 旧的独立 demo SPA 目录已删除, 其
通话/监听/我的历史视图迁入本 SPA. 由 JWT session cookie + 角色权限门控: 普通用户
只见通话区 (Talk / 我的历史), 管理员另见 Monitor + 管理区 (Dashboard / 全量
History / Demos / MCP / Web&Phone 默认 / 用户管理).

- **构建**: `npm run build` 输出 `static/admin/dist/`, 由 `app.mount("/", StaticFiles(...))` 在
  bot.py 末尾挂载.
- **路由** (hash mode, base `/`, 避免后端 catch-all):
  - 通话区: `/talk` (大圆按钮 + 转写气泡 + 总结 + 调试 Drawer)、`/my-history` (本人通话历史)
  - 管理区: `/dashboard`、`/history`、`/demos`、`/mcp-servers`、`/web`、`/phone`、`/users`、`/monitor`
- **关键文件**:
  - `src/audio.js` — Recorder + Player 类, AudioWorklet downsample 16 kHz / Player 不 pin sampleRate
  - `src/ws.js` — `openTalkWs() / openMonitorWs(callId)`, ws-token 走 cookie 鉴权
  - `src/views/{TalkView, MonitorView, MyHistoryView, DebugDrawer}.vue` + admin 各管理视图
  - `src/App.vue` — 按 `/api/auth/me` 的 role 渲染分组菜单 (通话区 / 管理区)
- **设计原则**: 通话视图**没有任何配置控件** (engine/lang/scenario/voice 等). 配置走管理区
  Web/Phone 默认页, 改完默认通过 RUNTIME_CONFIG per-call hot-reload
- **何时改它**:
  - UI 视觉调整 → `App.vue` + 各 View
  - 新增可视化 (例如波形 / VAD level meter) → 加新 View 或 TalkView 内嵌组件
  - 见 `docs/onboarding/03-runbook.md` §6 Admin UI 操作.

### `static/index.html.legacy` (695 行, 已归档)

旧版单文件 SPA, T4-Demo 重写后归档. **不被路由**, 仅作为代码复现 / 行为参考保留.
原内容: 顶部一堆配置下拉 (engine / lang / model / voice / scenario / minimax_model) +
提示词编辑器 + Talk + Monitor 双模式 + 总结按钮. 这些功能已经分别迁移到:
- Talk 双模式 → `static/admin/src/views/{TalkView, MonitorView}.vue`
- 配置控件 → `static/admin/` (Web 默认编辑页)
- 提示词编辑器 → demo manifest.yaml + Admin Demos 页详情

---

## 部署

### `deploy/deploy.sh` (102 行)

一键部署 bash 脚本: 打包 → S3 上传 → CFN deploy → 输出 URL。

- **流程**: `tar (excl .venv/.env/...)` → `aws s3 cp` → `aws cloudformation deploy --parameter-overrides ...`
- **必填 env**: `MINIMAX_API_KEY`, `SITE_PASSWORD`, 可选 `STACK_NAME`, `REGION` (默认 us-east-1)
- **何时改它**: stack 重命名、加新 CFN 参数、改打包 exclude 列表 (例如新增 docs/ 默认进 tarball)。

### `deploy/cloudformation.yaml` (323 行)

EC2 + CloudFront + IAM Role + Secrets Manager + Security Group + user-data 全套模板。

- **CFN 资源**: `Instance` (EC2 t3.medium, Ubuntu 24.04), `CloudFrontDistribution` (\*.cloudfront.net),
  `InstanceRole` + `InstanceProfile` (Bedrock / Transcribe / Polly / Secrets read), `MinimaxSecret`,
  `OriginSecurityGroup`
- **user-data**: 装 Python 3.12 + Node 20, 拉 tarball, `pip install`, `npm install + tsc`,
  写 `/opt/voicebot/.env`, 起 `voicebot.service` + `voiceserver.service`
- **何时改它**:
  - 加新 IAM 权限 (新 AWS 服务) → `InstanceRole.Policies`
  - 调 instance type → `Instance.Properties.InstanceType`
  - 加新 SG 规则 (放新端口) → `OriginSecurityGroup.SecurityGroupIngress`
  - 改 systemd 单元 → `Instance.UserData` 中 `Fn::Base64`
  - **注意**: CFN deploy 不会重跑 user-data, 见 `03-runbook.md` 的 SSM 热更新段。

---

## 知识库素材

`data/acme-security-support/kb.md` 是当前默认 KB 场景 (ACME Security Tech Support Tina) 的素材文档。后续
新增场景的标准做法是: 在 `data/<行业>/` 下放文档, 在 `bot.py` 的 `KB_SCENARIOS` 注册一条。
