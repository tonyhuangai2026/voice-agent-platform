# 02 · Architecture & Data Flow

> Voice Bot 是一个 **双引擎 / 双入口** 实时语音机器人。本文用 7 张
> ASCII 图把拓扑、声学链路、Pipecat 帧流、KB 注入、打断时序、Web Monitor
> 全部讲清楚。**纯 ASCII，不依赖任何渲染工具**。
>
> 与本文配套的：[01-code-map.md](./01-code-map.md) · [03-runbook.md](./03-runbook.md) · [05-config-and-env.md](./05-config-and-env.md)

---

## Diagram 1 · Top-level Architecture

```
   ┌──────────────────┐                ┌──────────────────────┐
   │  PSTN Caller     │                │  浏览器 Web Caller    │
   │  (+1 / +86…)     │                │  https://*.cloudfront│
   └────────┬─────────┘                └──────────┬───────────┘
            │ SIP+RTP                              │ WSS  (16 kHz PCM)
            │ UDP 5060 / 10000-10999               │
            ▼                                      ▼
   ┌──────────────────┐                ┌──────────────────────┐
   │ Chime SDK Voice  │                │   CloudFront         │
   │   Connector      │                │   (HTTPS · TLS 1.2+) │
   └────────┬─────────┘                └──────────┬───────────┘
            │ G.711 μ-law 8 kHz                   │ HTTPS → :7860
            ▼                                      ▼
   ┌──────────────────┐                ┌──────────────────────┐
   │  voice-server    │                │   bot.py (Pipecat)   │
   │  (Node SIP UAS)  │═══════════════►│   FastAPI :7860      │
   │  rtp-session.ts  │  WS 16k PCM    │   /ws  /phone/ws     │
   │  pipecat-client  │  ◄──── 24k PCM │   /monitor/ws        │
   └──────────────────┘                └────┬───────┬─────────┘
                                            │       │
                            ┌───────────────┘       └────────────┐
                            ▼                                    ▼
                  ┌────────────────────┐            ┌──────────────────────┐
                  │  Engine A          │            │   Engine B           │
                  │  Nova Sonic v2     │            │   Pipeline           │
                  │  (Bedrock S2S)     │            │   STT + LLM + TTS    │
                  │  audio in/out      │            │   Transcribe →       │
                  │                    │            │     Bedrock LLM →    │
                  │                    │            │     MiniMax / Polly  │
                  └────────────────────┘            └──────────────────────┘
```

**说明.** `voice-server` 终结电话腿（SIP 信令 + RTP 媒体），把 8 kHz μ-law
解码后**上采样到 16 kHz** 再走 WebSocket 转发到 `bot.py /phone/ws`。Web
浏览器直接通过 CloudFront → `bot.py /ws` 连接，wire 格式同样是 16 kHz PCM。
两条入口最后都进入 Pipecat pipeline。

bot.py 内根据 `engine` 参数（Web）或 `PHONE_ENGINE` env（电话）路由到两个
引擎之一：**Engine A = Nova Sonic v2 端到端**，**Engine B = Pipeline (STT+LLM+TTS)**。

> **浏览器入口 (单页合并之后)**: `GET /` 由 `app.mount("/", StaticFiles(...))` 服务
> `static/admin/dist/` (Vue 3 + Naive UI SPA, hash routing). 旧的独立 demo SPA
> 目录已删除, 其通话/监听/我的历史视图并入 admin 单页 (`#/talk`、
> `#/monitor`、`#/my-history`), 由 JWT session cookie + 角色权限门控.
> 旧 `static/index.html` 已归档为 `index.html.legacy`, 不被路由.

---

## Diagram 2 · Dual-Engine Comparison

```
                Engine A · Nova Sonic v2 (S2S)
   ┌─────────────────────────────────────────────────────────┐
   │                                                         │
   │   audio (16 kHz) ─────► Bedrock Bidi Streaming ─────►   │
   │                          amazon.nova-2-sonic-v1:0       │
   │                       ◄─────────── audio (24 kHz) ────  │
   │                       ◄─────────── text events ──────   │
   │                                                         │
   │   计费维度: speech_in / speech_out / text_in / text_out │
   │   适用语种: en-US / en-UK / es / fr / de / it / pt      │
   │   未支持:   zh-HK / zh-CN / ja-JP                       │
   │   时延优势: 无 STT/TTS 跳, 端到端 < 1 s                 │
   └─────────────────────────────────────────────────────────┘

                Engine B · Pipeline (STT + LLM + TTS)
   ┌─────────────────────────────────────────────────────────┐
   │                                                         │
   │   audio (16 kHz) ──► Transcribe Streaming ──► text     │
   │                                                  │     │
   │                                                  ▼     │
   │                                          Bedrock LLM   │
   │                              (Nova 2 Lite / Claude 4.x) │
   │                                                  │     │
   │                                                  ▼     │
   │                                          MiniMax / Polly│
   │                                          ───► audio (24k)│
   │                                                         │
   │   计费维度: Transcribe sec + LLM tokens + TTS chars     │
   │   适用语种: zh-HK / zh-CN / en-US / ja-JP (4 种内置)    │
   │   时延:    1.5 ~ 3 s (STT + LLM + TTS 三跳)             │
   └─────────────────────────────────────────────────────────┘
```

**说明.** Engine A 的 audio 直接进 Bedrock 双向流，模型自己出 audio 和
narration text。Engine B 是经典三段式，三个服务分别计费，可灵活替换 (例如
TTS 在 MiniMax 与 Polly 之间切换)。

bot.py 中两个 builder：`_build_nova_sonic_pipeline()` (line 1276) 与
`_build_pipeline()` (line 1390)。`/ws` 由 query `engine=` 决定，`/phone/ws`
由 `PHONE_ENGINE` env 决定。

---

## Diagram 3 · Dual Ingress Data Flow (声学链路)

```
                ┌── Web /ws  (engine=nova-sonic 或 pipeline) ──┐
                │                                               │
   浏览器 mic ──► AudioWorklet ──► 16 kHz PCM ─► WSS ──► bot.py
   24 kHz PCM ◄── AudioBuffer ◄── 24 kHz PCM ◄─ WSS ◄── bot.py
                │                                               │
                └───────────────── (无重采样) ──────────────────┘


                ┌── Phone /phone/ws  (PHONE_ENGINE) ────────────────────────┐
                │                                                            │
   Chime VC ──► SIP/RTP ─► voice-server                                     │
                            │                                                │
                            │  μ-law 8 kHz (160 samples / 20 ms)             │
                            ▼                                                │
                            mulaw.decode → 8 kHz PCM 16-bit                  │
                            │                                                │
                            ▼  upsample8to16 (linear interpolation)          │
                            16 kHz PCM ──► WS ──► bot.py /phone/ws           │
                                                                             │
                            ◄── 24 kHz PCM ◄── bot.py (LLM/Sonic out)        │
                            │                                                │
                            ▼  downsample24to8                               │
                            8 kHz PCM 16-bit                                 │
                            │                                                │
                            ▼  mulaw.encode                                  │
                            μ-law 8 kHz ──► RTP ──► Chime VC ──► PSTN        │
                │                                                            │
                └────────────────────────────────────────────────────────────┘
```

**说明.** Web 端浏览器原生输出 16 kHz PCM，直通；Phone 端必须做两次重采样：
入站 8→16 kHz (Nova Sonic v2 强制要求 16 kHz 输入), 出站 24→8 kHz 再 μ-law
编码塞回 RTP 流。

入站重采样在 `voice-server/src/pipecat-client.ts:sendPCM8`，出站在
`voice-server/src/sip/rtp-session.ts:sendAudio`。重采样工具函数在
`voice-server/src/audio-utils.ts` (linear interpolation, ~3.4 kHz 带宽够用)。

> **为什么不直接在 bot.py 里收 8 kHz？** 早期试过，Pipecat 内部 Silero VAD
> 和 Nova Sonic 都期待 16 kHz；让 voice-server 上采样比让 Python 处理 8 kHz
> 路径稳定得多。

---

## Diagram 4 · Pipecat Frame Pipeline 序列图

```
   ┌───────────────────┐
   │   transport.input │  ◄── 16 kHz PCM frames (InputAudioRawFrame)
   └────────┬──────────┘
            │
            │  InputAudioRawFrame
            ▼
   ┌───────────────────────────────────────────────┐
   │   user_agg = LLMUserContextAggregator         │
   │   ┌─────────────────────────────────────────┐ │
   │   │ vad_analyzer = SileroVADAnalyzer        │ │
   │   │   → UserStartedSpeakingFrame /          │ │
   │   │     UserStoppedSpeakingFrame            │ │
   │   ├─────────────────────────────────────────┤ │
   │   │ user_turn_strategies =                  │ │
   │   │   [SpeechTimeoutUserTurnStopStrategy(   │ │
   │   │      user_speech_timeout=0.4)]          │ │
   │   │   → 0.4 s VAD silence => turn 结束      │ │
   │   └─────────────────────────────────────────┘ │
   └────────┬──────────────────────────────────────┘
            │
            │  LLMRunFrame / TranscriptionFrame
            ▼
   ┌───────────────────────────────────────────────┐
   │   llm = AWSNovaSonicLLMService               │   ← Engine A
   │   或                                          │
   │   stt + llm + tts (3 个 service 串联)         │   ← Engine B
   └────────┬──────────────────────────────────────┘
            │
            │  OutputAudioRawFrame / LLMTextFrame
            ▼
   ┌───────────────────┐
   │  transport.output │  ──► 24 kHz PCM frames
   └────────┬──────────┘
            │
            ▼
   ┌──────────────────────────────────────────┐
   │  assistant_agg                            │
   │  EventBroadcaster (BaseObserver)          │
   │   ─ user_speaking, asr_partial/final,    │
   │     llm_start/delta/end, tts_start/end,  │
   │     bot_speaking                          │
   │   → fan-out 给 primary emit + monitors    │
   └──────────────────────────────────────────┘
```

**说明.** Pipecat 用 **Frame** 作为统一传递单位。`transport.input()` 把
WebSocket binary 包装成 `InputAudioRawFrame`，沿 pipeline 一路向下游推。
`user_agg` 是关键的 turn-管理节点：本地 VAD 检测说话起止 + speech-timeout
策略判定 turn 结束 (替代了 Pipecat 默认的 SmartTurn 重型 ML 推理)。

`EventBroadcaster` 是 observer 不是 processor — 它**旁路**所有 frame 走过的
点，提取 ASR / LLM delta / TTS 边界 / 说话状态等转成 JSON 事件向外 emit。

源码：`bot.py:1276` (`_build_nova_sonic_pipeline`) 与 `bot.py:1390`
(`_build_pipeline`)，EventBroadcaster 在 `bot.py:1087`。

---

## Diagram 5 · KB Injection Flow (synthetic user message)

```
   场景启动时 (例如 PHONE_SCENARIO=acme-security-support):
   ─────────────────────────────────────────────────

   bot.py:_kb_seed_messages(scenario_key, lang_key)
            │
            ▼
   读取 KB_SCENARIOS[scenario_key]["kb_path"]
            │
            ▼
   _load_kb()  →  body = open(kb_path).read()  // ~26 K chars
            │
            ▼
   返回 messages = [
     { role: "user",      content: "<intro>\n\n" + body },
     { role: "assistant", content: "<ack>"           },
   ]
            │
            ▼
   for m in messages:
       LLMContext.add_message(m)
            │
            ▼
   ┌───────────────────────────────────────────────────┐
   │  LLMContext (传给 LLMService)                      │
   │                                                    │
   │  [system] 你是 Tina, 客服助手 ...                  │   ← 短规则
   │  [user]   "以下是技术文档:\n\n" + <KB body>        │   ← KB 注入
   │  [assistant] "好的, 我已读完文档, 可以开始帮客户"  │   ← ack
   │  [user]   <真实通话第一句>                          │   ← 之后才进
   │  [assistant] ...                                   │
   │  ...                                              │
   └───────────────────────────────────────────────────┘
```

**说明.** Nova Sonic v2 的 system prompt 字符上限大约 22-25 K，直接把 KB
塞进 system 会触发 "Error processing responses" 而崩溃。**绕开方法**：把
KB body 包装成一条**合成的 user message**（再配一条 assistant ack），让
模型**当作历史对话**读进来。这等价于"给模型先讲一遍文档"，回答时模型自然
grounding 在 KB 上。

源码：`bot.py:_kb_seed_messages` (line 930)，`KB_SCENARIOS` 的 `kb_intro`
和 `kb_ack` 是多语种映射。Engine A/B 都走这条路 — KB 不依赖具体引擎。

---

## Diagram 6 · Barge-in Timing (打断时序)

```
   时间轴 →

  bot.py             voice-server                Pipecat / Nova
  /phone/ws          (Node)                      Sonic
   │                  │                            │
   │ ◄──── audio ─────┤  caller talks (8→16 kHz)   │
   │                  │                            │
   │  Silero VAD detects speech start              │
   │                  │                            │
   │  EventBroadcaster:                            │
   │   { type: "user_speaking", value: true }      │
   │ ────── WS text ──►                            │
   │                  │                            │
   │                  │  rtpSession.setMuted(true) │  ← 关键
   │                  │  · clearQueue()            │
   │                  │  · drop new sendAudio()    │
   │                  │                            │
   │                  │  caller 听到立即静音       │
   │                  │  (无残留 TTS 尾巴)          │
   │                  │                            │
   │  …caller 说完话 → SpeechTimeoutUserTurnStop   │
   │  EventBroadcaster:                            │
   │   { type: "user_speaking", value: false }     │
   │   { type: "llm_start" }                       │
   │   { type: "tts_start" }                       │
   │ ────── WS text ──►                            │
   │                  │                            │
   │                  │  rtpSession.setMuted(false)│  ← 解 mute
   │                  │  (任一: llm_start /        │
   │                  │   tts_start /              │
   │                  │   user_speaking=false 触发) │
   │                  │                            │
   │ ◄── 24 kHz PCM ──┤  bot 新一轮 audio 输出     │
```

**说明.** "打不断" 的根因是 RTP 缓冲了几百毫秒的旧 TTS audio。仅清队列
不够，Nova Sonic 还会持续推新 audio 进来 (它没察觉用户已经打断) — 必须
**进入 mute 模式**：清队列 + 拒收新 audio，直到一个明确的"新 turn 开始"
信号。

mute 触发点 = `user_speaking=true` / `asr_partial` / `asr_final` 任一；
解 mute 触发点 = `llm_start` / `tts_start` / `user_speaking=false` 任一。
之所以三个 unmute 触发都要：

- `llm_start` / `tts_start` — 模型真的开始下一轮，正常路径
- `user_speaking=false` 兜底 — 模型可能"装没听见"继续旧 turn (Nova Sonic
  偶尔不响应中断)，这时不能让 caller 永久静音，靠用户停止说话解 mute

源码：`voice-server/src/sip/rtp-session.ts:setMuted` (line 128) 与
`voice-server/src/server.ts:onEvent` 路由 (line 61).

---

## Diagram 7 · Web Monitor Fan-out

```
                ┌─────────────────────────────────────────┐
                │  ACTIVE_SESSIONS[call_id] = {           │
                │    primary_emit:  <phone WS>,           │
                │    monitors:      [<mon1>, <mon2>, ...] │
                │  }                                       │
                └─────────────────────────────────────────┘
                                  ▲
                                  │ fan_emit = _multi_emit(
                                  │   () => session_emits(call_id))
                                  │
   Pipecat                        │
   EventBroadcaster ──── emit ────┤
                                  │
                ┌─────────────────┼─────────────────────┐
                │                 │                     │
                ▼                 ▼                     ▼
           primary emit    monitor emit #1      monitor emit #2
           (call leg WS)   (browser /monitor)   (browser /monitor)
                │                 │                     │
                ▼                 ▼                     ▼
            phone speaks    Monitor UI 显示       Monitor UI 显示
            audio + JSON    JSON events only      JSON events only


   Browser side:
   ┌──────────────────────────────────┐
   │  GET /api/calls           ─────► │  返回 ACTIVE_SESSIONS 列表
   │  WSS /monitor/ws?call_id= ─────► │  attach 到指定通话
   └──────────────────────────────────┘
```

**说明.** 一个通话在 `bot.py` 里登记为 `ACTIVE_SESSIONS[call_id]`，附带
`primary_emit` (主腿，发音频 + 事件) 和 `monitors` 列表 (只发事件)。
EventBroadcaster 输出每个事件时通过 `_multi_emit` 包装的 callable 一次性
fan-out 给所有 emit 目标。

监控浏览器并不参与音频流：它通过 `WSS /monitor/ws?call_id=<uuid>` 加入
监听列表，只接收 JSON 事件 (asr_partial/final, llm_delta, tts_start/end,
user_speaking, bot_speaking)。所以可以多个监听同时跑，互不干扰。

源码：`bot.py:1001` (`ACTIVE_SESSIONS`) / `bot.py:1031` (`session_register`)
/ `bot.py:1058` (`session_attach_monitor`) / `bot.py:1736`
(`/monitor/ws` endpoint)。`/api/calls` 在 `bot.py:1675`。

---

## 小结：哪里看代码

| 主题 | 入口符号 | 文件 |
|---|---|---|
| 顶层架构 | `app = FastAPI(...)` | `bot.py` |
| Engine A pipeline | `_build_nova_sonic_pipeline` | `bot.py:1276` |
| Engine B pipeline | `_build_pipeline` | `bot.py:1390` |
| Phone path entry | `phone_ws_endpoint` | `bot.py:1689` |
| Web path entry | `ws_endpoint` | `bot.py:1618` |
| KB 注入 | `_kb_seed_messages` | `bot.py:930` |
| 事件 fan-out | `EventBroadcaster` | `bot.py:1087` |
| Session 注册 | `ACTIVE_SESSIONS` + `session_register` | `bot.py:1001-1080` |
| 8→16 kHz 上采样 | `sendPCM8` | `voice-server/src/pipecat-client.ts` |
| 24→8 kHz + RTP | `RtpSession.sendAudio` | `voice-server/src/sip/rtp-session.ts` |
| Mute 模式 | `RtpSession.setMuted` | `voice-server/src/sip/rtp-session.ts:128` |
| Barge-in 路由 | `client.onEvent` | `voice-server/src/server.ts:61` |

需要更细的代码地图见 [01-code-map.md](./01-code-map.md)；部署/运维的
具体命令见 [03-runbook.md](./03-runbook.md)。
