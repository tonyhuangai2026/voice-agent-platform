# Pipeline 三段式响应延迟分析报告

> Web 模式：mic → Silero VAD → AWS Transcribe STT → Bedrock LLM → MiniMax TTS → 浏览器
> 电话模式：SIP/RTP → 同上（或 Nova Sonic S2S 端到端）
>
> 分析日期：2026-05-23
> 代码基线：`bot.py` HEAD（feature/prod-eip）

---

## 一、各段延迟来源（按从大到小估）

| 段 | 默认 / 当前配置 | 估计耗时 | 文件位置 |
|---|---|---|---|
| **VAD turn-stop（pipeline 模式）** | 跑 Pipecat 默认 SmartTurn ONNX | **1.0 ~ 1.5 s** ⚠️ | `bot.py:1845` |
| LLM TTFT | nova-2-lite + KB 长 system prompt + 5 场景 | 600 ~ 1200 ms | `bot.py:1809` |
| TTS TTFB | MiniMax `speech-2.8-turbo` SSE 首字节 | 400 ~ 700 ms | `bot.py:1525` |
| STT final | Transcribe 默认（无 partial-stabilization） | 300 ~ 500 ms | `bot.py:1800` |
| 网络 | EC2 (us-east-1) → MiniMax (CN) | 200 ~ 400 ms RTT | — |

---

## 二、最大单点瓶颈：pipeline 模式 turn-stop 策略不一致 🔴

`_build_nova_sonic_pipeline`（电话 / Nova Sonic 路径，`bot.py:1686-1688`）已经把默认 SmartTurn 换成短超时：

```python
user_turn_strategies=UserTurnStrategies(
    stop=[SpeechTimeoutUserTurnStopStrategy(user_speech_timeout=0.4)],
)
```

**但 `_build_pipeline`（web + 电话 pipeline fallback，`bot.py:1843-1846`）没有传 `user_turn_strategies`**，所以仍跑 SmartTurn ONNX。这就是「客户讲完到 LLM 开始」普遍 1+ 秒的主因，与 Nova Sonic 路径有 ~1 s 差距完全是这个配置漏掉了。

**改法（5 行）：**

```python
user_agg, assistant_agg = LLMContextAggregatorPair(
    context,
    user_params=LLMUserAggregatorParams(
        vad_analyzer=SileroVADAnalyzer(),
        user_turn_strategies=UserTurnStrategies(
            stop=[SpeechTimeoutUserTurnStopStrategy(user_speech_timeout=0.4)],
        ),
    ),
)
```

**预期收益：500 ~ 1000 ms。** 单这一项就能让响应感受从「明显卡」变「自然」。

---

## 三、其他可调点（按 ROI 排序）

### A · LLM 端（中收益，零成本）

#### A1 · `max_tokens=256` 偏大（`bot.py:1817`）
每轮 LLM 都跑到 256 token 上限或遇停止符。客服场景每句一两句话足够，**降到 128 或 96**，节省 50 ~ 150 ms 输出时间。

#### A2 · KB 注入位置（`bot.py:1837-1841`）
现在 KB 整段塞进上下文做 user/assistant 配对。每次新会话首轮 LLM 要读 1500 ~ 2500 token KB → TTFT 增加 200 ~ 500 ms。
- **短期**：确认 KB 命中 Bedrock prompt cache（Nova 系列支持 `cachePoint`）。
- **中期**：把 KB 摘要（150 token）+ "需要详情时调 tool 取" 模式取代全文注入。

#### A3 · 模型选择
`nova-2-lite` 是 Nova 家族第二快。**`nova-micro` 在 zh-CN / zh-HK / ja-JP 客服 turn-by-turn 场景表现可接受**，TTFT 比 lite 低 ~200 ms。可以 A/B：把 `web.model` 切成 `nova-micro` 跑两天观察用户满意度。

### B · TTS 端（中收益）

#### B1 · MiniMax TTFB 占大头
当前已用 SSE 流式（`stream=True`，`bot.py:326`）+ `speech-2.8-turbo`，是 HTTP API 最快配置。再要快只能换 **MiniMax WebSocket TTS API**（`/v1/tts/ws`）—— 比 HTTP SSE 低 100 ~ 200 ms TTFB，但要新写 service。优先级中。

#### B2 · Chunk 切分
句末流式拆 chunk 已经是 20 ms（`bot.py:401-409`），没有改进空间。

#### B3 · 首字节技巧
LLM 在生成第一个完整子句时立刻发给 TTS，不等整段。Pipecat 默认按句子边界（`。`/`！`/`？`/`.`/`!`/`?`）切分。**verify 一下**：

```bash
grep -n "TextAggregator\|text_aggregator" bot.py
```

如果有自定义聚合器换成了 paragraph 级，要换回 sentence 级。

### C · STT 端（低收益）

#### C1 · 启用 `partial_results_stability=high`（`bot.py:1806`）
```python
settings=AWSTranscribeSTTService.Settings(
    language=lang["stt"],
    enable_partial_results_stabilization=True,
    partial_results_stability="high",
)
```
稳定 partial 出现更早，配合 400 ms 静音 timeout 可以「在客户停顿前」就开始 LLM。

#### C2 · 语言 lock
`Settings(language=lang["stt"])` 已经做了，没问题。

#### C3 · 自定义词
客户尾音吃字情况，可以加 `vocabulary_name=<custom>` 上传场景词（员工编号格式 W123456、INC- 工单号）。**这是正确率优化不是速度优化。**

### D · VAD 参数（低收益但简单）

`SileroVADAnalyzer()` 全默认。可以传：

```python
SileroVADAnalyzer(params=VADParams(
    stop_secs=0.4,
    start_secs=0.2,
    confidence=0.7,
))
```

- `stop_secs=0.4` 与 turn-stop 协同（已经够快）
- `start_secs=0.2` 让 barge-in 触发更敏，掐 TTS 更准

### E · 网络（不动）

EC2 us-east-1 → MiniMax CN endpoint 跨国 RTT 200 ~ 400 ms，每次 SSE 连接握手都付一次。MiniMax 没公开 us-east-1 endpoint，这块改不了——除非换 TTS 提供商（Azure Neural / ElevenLabs us-east 部署）。客服场景 MiniMax 中文音色优势大，不建议换。

---

## 四、优先级建议

| 优先级 | 改动 | 预期收益 | 工作量 |
|---|---|---|---|
| **P0** | pipeline 模式加 `SpeechTimeoutUserTurnStopStrategy(0.4)` | -500 ~ 1000 ms | 5 行 |
| **P1** | `max_tokens` 256 → 128 | -50 ~ 150 ms | 1 行 |
| **P1** | Transcribe 加 `partial_results_stability=high` | -100 ~ 200 ms | 1 行 |
| **P2** | Bedrock prompt caching 接 KB | -200 ~ 500 ms 首轮 | 1 天 |
| **P2** | A/B 切 `nova-micro` | -200 ms TTFT | 配置 + 监控 |
| **P3** | MiniMax HTTP → WebSocket TTS | -100 ~ 200 ms TTFB | 2~3 天 |

---

## 五、最低限度改动方案（推荐马上做）

只动 **P0 + P1** 三处，共 ~7 行代码：

```python
# bot.py:1843 附近,_build_pipeline 内
user_agg, assistant_agg = LLMContextAggregatorPair(
    context,
    user_params=LLMUserAggregatorParams(
        vad_analyzer=SileroVADAnalyzer(),
        user_turn_strategies=UserTurnStrategies(
            stop=[SpeechTimeoutUserTurnStopStrategy(user_speech_timeout=0.4)],
        ),
    ),
)

# bot.py:1817
settings=LLMSettings(
    model=model_id,
    system_instruction=system_prompt,
    max_tokens=128,           # was 256
),

# bot.py:1806
settings=AWSTranscribeSTTService.Settings(
    language=lang["stt"],
    enable_partial_results_stabilization=True,
    partial_results_stability="high",
),
```

**累计预期收益：650 ~ 1350 ms**，端到端从「客户停止说话到第一个字节 TTS 出声」从约 2.5 s 降到 1.2 ~ 1.5 s。

---

## 六、参考文件

- `bot.py:1597-1752` — Nova Sonic 路径（已优化的参考实现）
- `bot.py:1755-1910` — pipeline 路径（待优化）
- `bot.py:288-411` — MiniMax SSE TTS 实现
- `data/it-helpdesk/manifest.yaml` — 场景 system prompt 长度参考
- `data/it-helpdesk/kb.*.md` — KB 长度参考（影响 LLM TTFT）
