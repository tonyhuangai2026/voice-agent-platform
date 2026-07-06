# 03 · Runbook (部署 / 运维 / 已知 hotfix)

> 拿到这份文档你就能独立完成「新账号一键部署 → Chime VC 配置 → 故障排查」整条链路。
>
> 若需要更深的部署细节, 见 [deploy/README.md](../../deploy/README.md). 本文不重复, 只补充。

---

## 1 · 一键部署

```bash
cd /home/ubuntu/test_audio_framework/deploy
MINIMAX_API_KEY=sk-...   \
SITE_PASSWORD=GenAIIC-tonyhh  \
./deploy.sh
```

要点:

- **Stack 名**: 默认 `genaiic-voicebot` (`STACK_NAME` env 可覆盖); 副本部署时改成 `voicebot` 等
- **区域强制 us-east-1**: CloudFront origin-facing prefix list `pl-3b927c52` 仅在 us-east-1 有效, Nova Sonic v2 也仅 us-east-1
- **MiniMax key 可空**: 不用 MiniMax 时留空, UI 切到 Polly / Nova Sonic 即可。Web 默认 voice 是 MiniMax 的, 第一次连上会 TTS 失败, 顶部下拉切走
- **首次部署 5-8 min** (EC2 boot + pip install + npm install + tsc)
- 输出会给一个 CloudFront URL (`https://*.cloudfront.net/`), 浏览器打开就能用

部署脚本细节 (S3 桶创建、tarball 打包 exclude、CFN 参数) 见
[deploy/README.md](../../deploy/README.md).

---

## 2 · Chime SDK Voice Connector 手动配置 (4 步)

CFN 不能完全自动化 Chime 号码申请, 以下 4 步在 AWS 控制台一次性完成:

1. **Chime SDK → Voice Connectors → Create Voice Connector**
   - Region: `us-east-1`
   - Encryption: 不开 (Chime VC inbound 是 SIP TLS 可选, 我们走 UDP)

2. **Origination 配置**
   - Add route → Host: 用 CFN 输出的 `PublicIP` (e.g. `13.220.150.25`)
   - Port: `5060`, Protocol: `UDP`, Priority: `1`, Weight: `100`
   - **每次 EC2 stop/start 后 IP 都会变**, 必须手动同步, 见 §5 hotfix 8

3. **Phone numbers**
   - Order new number 或 Assign existing
   - Inbound calling rules → Route to Voice Connector → 选刚建的 VC

4. **(可选) 安全收紧**
   - SG ingress 默认 `0.0.0.0/0`; 想锁的话用 Chime IP 段
   - <https://docs.aws.amazon.com/chime-sdk/latest/dg/network-config.html>

测试: 拨打那个号, 应听到 bot 开场白 (默认 Tina)。打开 Web Monitor
模式 (CloudFront URL → 顶部切到 Monitor) 实时看通话事件流。

---

## 3 · SSM 热更新 (绕开 CFN user-data 不重跑)

**为什么需要**: `aws cloudformation deploy` 只在 instance 属性变化时 replace EC2, 不会重跑
user-data。这意味着改了 `bot.py` 重新 deploy 后 EC2 上的代码没变。见 §5 hotfix 7.

**热更新流程**:

```bash
# 1. 本地打 tarball
cd /home/ubuntu/test_audio_framework
TS=$(date +%Y%m%d-%H%M%S)
tar -czf /tmp/hotfix-$TS.tar.gz \
  --exclude='voice-server/node_modules' \
  --exclude='voice-server/dist' \
  --exclude='.venv' --exclude='__pycache__' --exclude='.git' \
  bot.py voice-server static deploy

# 2. 上传 S3
aws s3 cp /tmp/hotfix-$TS.tar.gz \
  s3://genaiic-voicebot-deploy-<account>-us-east-1/hotfix-$TS.tar.gz \
  --region us-east-1

# 3. SSM 推送 + 重启
INSTANCE_ID=$(aws cloudformation describe-stacks \
  --stack-name genaiic-voicebot --region us-east-1 \
  --query 'Stacks[0].Outputs[?OutputKey==`InstanceId`].OutputValue' \
  --output text)

aws ssm send-command \
  --instance-ids "$INSTANCE_ID" \
  --document-name AWS-RunShellScript \
  --region us-east-1 \
  --parameters '{"commands":[
     "set -e",
     "aws s3 cp s3://genaiic-voicebot-deploy-<account>-us-east-1/hotfix-'$TS'.tar.gz /tmp/hf.tar.gz --region us-east-1",
     "sudo -u ubuntu tar -xzf /tmp/hf.tar.gz -C /opt/voicebot",
     "cd /opt/voicebot/voice-server && sudo -u ubuntu npx tsc",
     "chown -R ubuntu:ubuntu /opt/voicebot",
     "systemctl restart voicebot voiceserver",
     "sleep 4",
     "systemctl is-active voicebot voiceserver"
   ]}' \
  --output text --query 'Command.CommandId'
```

返回的 `CommandId` 用 `aws ssm get-command-invocation --command-id $ID
--instance-id $INSTANCE_ID --region us-east-1` 看输出。整个流程 < 1 min。

> 想完全自动化 deploy + reload, 把以上脚本封进 `deploy/hotfix.sh`。

---

## 4 · 常用运维命令

```bash
# 进入 EC2 (无需 SSH key, 走 SSM Session Manager)
aws ssm start-session --target $INSTANCE_ID --region us-east-1

# 看实时日志
sudo tail -f /var/log/voicebot.log     # Pipecat / FastAPI / Bedrock 调用
sudo tail -f /var/log/voiceserver.log  # SIP UAS / RTP / barge-in 事件

# 看 user-data bootstrap (首次部署排查)
sudo tail -f /var/log/user-data.log

# 服务管理
sudo systemctl status voicebot voiceserver
sudo systemctl restart voicebot voiceserver
sudo systemctl daemon-reload && sudo systemctl restart voicebot

# 检查 .env (生产)
sudo cat /opt/voicebot/.env

# Bedrock CloudWatch 查 token usage
aws cloudwatch get-metric-statistics \
  --namespace AWS/Bedrock --region us-east-1 \
  --metric-name InputSpeechTokenCount \
  --dimensions Name=ModelId,Value=amazon.nova-2-sonic-v1:0 \
  --start-time $(date -u -d "1 hour ago" +%Y-%m-%dT%H:%M:%S) \
  --end-time   $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 60 --statistics Sum

# Web Monitor (浏览器)
# https://<cloudfront>/  → 顶部切到 Monitor 模式
# → 选 active call_id → 看 ASR / LLM delta / TTS 起止 / 说话状态
```

---

## 5 · 已知 hotfix 清单 (8 条)

每条三段式: 症状 / 根因 / 解决 (含 `文件:函数` 引用)。

### Hotfix 1 · 8 → 16 kHz 上采样 (Nova Sonic 必要)

- **症状**: 电话呼入只听到开场白, 之后 bot 完全不响应; 日志出现
  `Error processing responses ... Timed out waiting for audio bytes`
- **根因**: Nova Sonic v2 期待 16 kHz 输入, voice-server 早期版本直接
  发原始 8 kHz μ-law-decoded PCM 进 `/phone/ws`, 模型识别不出, 等 55 s
  超时。Pipeline 模式 + Transcribe 8 kHz mode 也存在类似稳定性问题
- **解决**: voice-server 在 `voice-server/src/pipecat-client.ts:sendPCM8`
  (line 92) 调用 `upsample8to16(pcm8)` 后再 WS 发送。bot.py phone path 的
  `input_sample_rate` 默认 `INPUT_SAMPLE_RATE = 16000`

### Hotfix 2 · voice-server `setMuted()` 模式 (打断不干净)

- **症状**: 用户开口后 bot 还在讲, 听感是"语音残留 200-500 ms 才停"
- **根因**: 仅清出栈队列 (clearQueue) 不够, Nova Sonic 还在持续往 WS
  推新 audio 进来, 几十毫秒就把队列填回去
- **解决**: `voice-server/src/sip/rtp-session.ts:setMuted` (line 128) —
  进 mute 模式时清队列 + 让 `sendAudio` 直接丢弃新数据, 直到显式解 mute

### Hotfix 3 · 解 mute trigger (打断后 bot 不开口)

- **症状**: 打断后 bot 永久静音, 直到挂断
- **根因**: 早期解 mute 仅靠 `bot_speaking=true`, 而 Nova Sonic 不一定
  fire `BotStoppedSpeakingFrame` → `bot_speaking` 不会 toggle off→on, mute
  永远不解
- **解决**: `voice-server/src/server.ts:onEvent` (line 61) — 三个 unmute
  trigger 任一即解: `llm_start` / `tts_start` / `user_speaking=false`。
  最后一个是兜底 (Nova Sonic 偶尔不响应中断)

### Hotfix 4 · SileroVADAnalyzer 必须保留

- **症状**: 打断信号完全不发, voice-server 收不到 `user_speaking=true`
- **根因**: Nova Sonic 自己服务端 VAD 的事件不一定/不及时 emit。Pipecat
  本地 Silero VAD 才是产生 `UserStartedSpeakingFrame` 最快、最可靠的源
- **解决**: `bot.py:_build_nova_sonic_pipeline` (line 1276) 的
  `LLMUserAggregatorParams(vad_analyzer=SileroVADAnalyzer(), ...)` 必须保留

### Hotfix 5 · SpeechTimeoutUserTurnStopStrategy 替换 SmartTurn

- **症状**: 用户讲完到 bot 开口之间多 1-2 s 静默, 听感"反应慢"
- **根因**: Pipecat 默认 turn-stop 策略是 `LocalSmartTurnAnalyzerV3` (ONNX),
  对每个 speech end 跑 ML 推理, 端到端再加 1-1.5 s
- **解决**: `bot.py:_build_nova_sonic_pipeline` (line 1351) 把
  `user_turn_strategies` 设为 `UserTurnStrategies(stop=[SpeechTimeoutUserTurnStopStrategy(user_speech_timeout=0.4)])`,
  用 0.4 s VAD 静默判 turn 结束。Nova Sonic 服务端会再做最终确认

### Hotfix 6 · MiniMax `MINIMAX_GROUP_ID=""` 空字符串陷阱

- **症状**: MiniMax TTS 报 `insufficient balance` 但账户余额充足
- **根因**: Pipecat MiniMax service 把 `?GroupId=` 拼到 URL, 即使 group_id
  是空字符串。MiniMax 把空 group_id 当成不同 (未充值) 账户
- **解决**: `bot.py:SimpleMiniMaxTTSService.run_tts` (line ~272) 在
  `group_id` 为空时把 query string 整个截掉 (`url.split("?", 1)[0]`)。
  **同时**: `.env` 里**不要写** `MINIMAX_GROUP_ID=`(空), 让代码读不到该 env
  最稳

### Hotfix 7 · CFN deploy 不重跑 user-data

- **症状**: 改了 bot.py / voice-server 后 `./deploy.sh`, EC2 上代码却没变
- **根因**: `aws cloudformation deploy` 只在 instance 属性变 (instance type, AMI 等)
  时 replace EC2 → 重跑 user-data; 仅改 user-data 字符串内容不会触发 replace
- **解决**: 用 §3 SSM 热更新流程把新 tarball 推到 EC2 + `tsc` 编译 +
  `systemctl restart voicebot voiceserver`。或者把代码 hash 写进 CFN
  metadata 强制 replace

### Hotfix 8 · EC2 公网 IP 漂移 → Chime VC origination 失效

- **症状**: 重新部署 / EC2 stop+start 后, 拨电话进 SIP 直接超时
- **根因**: CFN 默认 EC2 公网 IP 不固定; Chime VC origination 还指向旧 IP
- **解决**: 部署后立即拿 `aws cloudformation describe-stacks ... PublicIP`,
  调用:
  ```bash
  aws chime-sdk-voice put-voice-connector-origination \
    --voice-connector-id <vc-uuid> --region us-east-1 \
    --origination '{"Routes":[{"Host":"<NEW_IP>","Port":5060,"Protocol":"UDP","Priority":1,"Weight":1}],"Disabled":false}'
  ```
  根本性方案: 给 EC2 挂 EIP, IP 永久固定 (CFN template 加 `AWS::EC2::EIP`)

---

## 6 · Admin UI 操作 (运行时配置 + Demo)

T3+T4 之后, Admin UI 取代了 "改代码 / 改 env / 重启" 这条老路径。

### 6.1 登录

- URL: `https://<cloudfront-or-ec2>/admin/`
- 弹出浏览器原生 Basic Auth: 用户名 `admin`, 密码 = CFN parameter `AdminPassword`
- 如果 `AdminPassword` 为空 → 服务返回 503 ("admin disabled"), 这是故意的, 防止空密码误开放

### 6.2 改 Web 默认 (浏览器 /ws 入口)

1. 登录后默认进入 `/admin/web` (Web 默认配置页)
2. 改 engine / lang / scenario / model / provider / voice / minimax_model 任意字段
3. 点 "保存" → toast 提示 "已保存"
4. **生效粒度**: 新建浏览器会话生效 (用户刷新 / 新开 tab 时拉 `/api/config` 拿新默认). 已打开的 Talk 会话不变。

### 6.3 改 Phone 默认 (PSTN /phone/ws)

1. 切到 `/admin/phone`
2. 改字段 + 保存
3. **生效粒度**: per-call hot-reload — 下一通新通话生效, 进行中通话不变。**不需要 systemctl restart**。
4. 实测验证: 看 voicebot.log 应有 `phone WS using runtime config: engine=... lang=... scenario=...` 这行, 反映你刚保存的值。

### 6.4 加新 Demo

无需改代码, 流程:

```bash
# 在 EC2 上 SSM 进去后
sudo -i
cd /opt/voicebot/data
mkdir bank-of-china
cat > bank-of-china/manifest.yaml <<'YAML'
id: bank-of-china
label: 银行客服 (BOC)
lang: zh-CN
system:
  zh-CN: |
    你是中国银行的智能客服, 用普通话回答用户的银行业务咨询...
greeting:
  zh-CN: 您好, 我是中国银行智能客服, 请问有什么可以帮您的?
YAML
echo '客户文档内容...' > bank-of-china/kb.md
chown -R ubuntu:ubuntu bank-of-china
```

然后回到 Admin UI:
1. 切到 `/admin/demos`
2. 点 "重新扫描" → toast 显示 "扫描完成, 发现 N 个 demo"
3. 列表里出现新 demo
4. 切到 `/admin/web` 或 `/admin/phone`, scenario 下拉选 `bank-of-china`, 保存
5. 拨电话 (Phone) 或刷新页面 (Web) 即生效

### 6.5 备份与恢复

- 持久化文件: `/opt/voicebot/config/runtime.json` (per Vue session 持久化的当前默认)
- 备份: `aws ssm start-session --target ... && cat /opt/voicebot/config/runtime.json > /tmp/backup.json`
- 恢复: 把备份文件 scp 回 `/opt/voicebot/config/runtime.json` + `systemctl restart voicebot` 或在 Admin UI 上点保存触发 reload

### 6.6 故障排查

- Admin UI 打不开 (浏览器空白): 检查 `static/admin/dist/index.html` 是否存在; 如果 user-data 没构建成功, 可以 SSM 进去手动 `cd /opt/voicebot/static/admin && npm install && npm run build`, 然后 `systemctl restart voicebot`
- Admin UI 401 反复弹窗: 确认 ADMIN_PASSWORD 已写到 `.env`; 不要混用 SitePassword
- 保存后 phone 通话仍走老 engine: 那是 in-flight call 不切的预期行为, 挂掉再拨即可

### 6.7 Demo UI 操作 (Vue 3 SPA)

T4-Demo 重写之后, 浏览器入口 `https://<host>/` 是 Vue 3 + Naive UI SPA. 风格与
Admin UI 一致 (主色 #0084FF, 暗 / 浅主题切换).

**入口路由**:
- `/` → 自动重定向到 `/#/talk`
- `#/talk` — 大圆按钮 + 转写气泡 + 总结 + 调试 Drawer
- `#/monitor` — 选 active call_id 看事件流 (PSTN + Web 通话都能监听)
- 顶部右上角 `🛠 Admin` 链接跳到 `/admin/`

**鉴权**: 沿用 SitePassword (`require_password` dep). 浏览器会用 Basic Auth 弹窗.
Admin 密码独立 (ADMIN_PASSWORD), 二者无关.

**没有配置控件** — 这是 T4-Demo 的核心改动:
- ❌ 没有 engine / lang / scenario / model / voice / minimax_model 下拉
- ❌ 没有提示词编辑器
- ✅ 顶部状态栏只展示当前后端默认 (`{engine} · {lang} · {scenario}`), 旁边 `ⓘ` 提示去 Admin
- ✅ 改默认请去 `/admin/web` 或 `/admin/phone`, 保存后下一次新建会话生效

**旧 UI**: `static/index.html.legacy` 保留作复现参考, **不被路由** (访问 /legacy 会 404).

**调试**: 点顶部 `🔧 调试` 按钮打开 NDrawer, 看到完整 EventBroadcaster 事件流 (ASR / LLM /
TTS / VAD 颜色编码). 业务演示时不用打开.

**总结**: 录音中或结束后点顶部 `📋 总结`, 后端走 POST `/api/summary` 返回 markdown, 前端 marked
+ DOMPurify 渲染到 NModal.

**故障**: GET `/` 返回 404 → 检查 `/opt/voicebot/static/admin/dist/index.html` 是否存在.
如果 user-data 没构建成功 (npm install 超时等), SSM 进 EC2 手动 `cd /opt/voicebot/static/admin
&& npm install && npm run build`, 然后 `systemctl restart voicebot`.

---

## 7 · 还会去哪里看

- 部署脚本 / CFN 参数 / S3 桶细节: [deploy/README.md](../../deploy/README.md)
- 代码地图: [01-code-map.md](./01-code-map.md)
- 架构 / 数据流图: [02-architecture.md](./02-architecture.md)
- 环境变量清单 (含 GroupId 陷阱完整说明): [05-config-and-env.md](./05-config-and-env.md)
- 成本与风险: [04-cost-and-risks.md](./04-cost-and-risks.md)
