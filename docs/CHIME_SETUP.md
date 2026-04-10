# Amazon Chime SDK Voice Connector 配置指南

本文档介绍如何为 Voice Agent Platform 配置 Amazon Chime SDK Voice Connector，实现 PSTN 电话接入。

## 架构概览

```
来电者 (PSTN)
    ↓ 拨打 Chime 分配的电话号码
Amazon Chime Voice Connector
    ↓ SIP INVITE (UDP:5060)
Voice Agent Server (ECS EC2 + Elastic IP)
    ↓ RTP 双向音频流 (UDP:10000-20000)
Amazon Bedrock Nova Sonic (语音 AI)
```

Voice Connector 作为 PSTN 网关，将来电通过标准 SIP/RTP 协议转发到我们的服务器，无需 Twilio 等第三方服务。

## 前置条件

- AWS 账号，已开通 Amazon Chime SDK 访问权限
- AWS CLI v2 已配置
- Voice Agent Platform CloudFormation 栈已部署（参见主 README）

## 步骤一：申请电话号码

1. 打开 **AWS Console → Amazon Chime SDK → Phone number management**
2. 点击 **Provision phone numbers**
3. 选择 **Voice Connector** 用途
4. 选择国家和号码类型：
   - **US Local DID**：约 $1/月，最容易申请
   - **US Toll-Free**：约 $2/月
5. 搜索可用号码，选择一个，确认购买

> **注意**：首次申请可能需要在 **Service Quotas** 中提额，或提交 **AWS Support Case**。某些国家的号码需要地址证明。审批通常需要 1-2 个工作日。

## 步骤二：创建 Voice Connector

1. 打开 **Amazon Chime SDK Console → Voice Connectors**
2. 点击 **Create voice connector**
3. 填写：
   - **Name**：如 `voice-agent-vc`
   - **AWS Region**：选择 `us-east-1`（与 Bedrock Nova Sonic 同区域）
4. 创建后记录 **Outbound host name**，格式如：
   ```
   xxxxx.voiceconnector.chime.aws
   ```
   这就是部署时需要的 `CHIME_VOICE_CONNECTOR_HOST`。

## 步骤三：关闭加密要求

> **这一步非常关键！** Voice Connector 默认要求 TLS + SRTP 加密，但我们的 SIP/RTP 实现使用明文 UDP。不关闭会导致来电完全无法接通。

```bash
aws chime-sdk-voice update-voice-connector \
  --voice-connector-id <your-voice-connector-id> \
  --name "voice-agent-vc" \
  --no-require-encryption \
  --region us-east-1
```

验证：
```bash
aws chime-sdk-voice get-voice-connector \
  --voice-connector-id <your-voice-connector-id> \
  --region us-east-1 \
  --query 'VoiceConnector.RequireEncryption'
# 应返回: false
```

## 步骤四：绑定号码到 Voice Connector

在 **Phone number management** 中，将步骤一申请到的号码关联到刚创建的 Voice Connector。

也可通过 CLI：
```bash
aws chime-sdk-voice associate-phone-numbers-with-voice-connector \
  --voice-connector-id <your-voice-connector-id> \
  --e164-phone-numbers "+1XXXXXXXXXX" \
  --region us-east-1
```

## 步骤五：部署 Voice Agent Platform

参见主 README 的安装部署章节。部署完成后，从 CloudFormation 输出获取 **GatewayPublicIP**（Elastic IP）：

```bash
aws cloudformation describe-stacks \
  --stack-name voice-agent-platform \
  --query 'Stacks[0].Outputs[?OutputKey==`GatewayPublicIP`].OutputValue' \
  --output text --region us-east-1
```

## 步骤六：配置 Voice Connector Origination

将来电路由到你的服务器：

```bash
aws chime-sdk-voice put-voice-connector-origination \
  --voice-connector-id <your-voice-connector-id> \
  --origination '{
    "Routes": [
      {
        "Host": "<GatewayPublicIP>",
        "Port": 5060,
        "Protocol": "UDP",
        "Priority": 1,
        "Weight": 1
      }
    ],
    "Disabled": false
  }' \
  --region us-east-1
```

## 步骤七：配置 Voice Connector Termination

允许你的服务器通过 Voice Connector 发起外呼：

```bash
# 设置 SIP 认证凭据（用于外呼）
aws chime-sdk-voice put-voice-connector-termination-credentials \
  --voice-connector-id <your-voice-connector-id> \
  --credentials '[{"Username":"<username>","Password":"<password>"}]' \
  --region us-east-1

# 启用 Termination
aws chime-sdk-voice put-voice-connector-termination \
  --voice-connector-id <your-voice-connector-id> \
  --termination '{
    "CpsLimit": 1,
    "CallingRegions": ["US"],
    "CidrAllowedList": ["<GatewayPublicIP>/32"],
    "Disabled": false
  }' \
  --region us-east-1
```

## 步骤八：验证

1. 拨打申请到的电话号码
2. 应该立即接通并听到 AI 问候
3. 检查 CloudWatch 日志确认 SIP INVITE 和 RTP 会话：
   ```bash
   aws logs tail /ecs/voice-agent-server --region us-east-1 --follow
   ```

## 启用 Voice Connector 日志（可选，用于调试）

```bash
aws chime-sdk-voice put-voice-connector-logging-configuration \
  --voice-connector-id <your-voice-connector-id> \
  --logging-configuration '{"EnableSIPLogs": true, "EnableMediaMetricLogs": true}' \
  --region us-east-1
```

日志位置：
- SIP 消息：`/aws/ChimeVoiceConnectorSipMessages/<vc-id>`
- 通话指标：`/aws/ChimeVoiceConnectorLogs/<vc-id>`

## 费用参考（us-east-1）

| 项目 | 费用 |
|---|---|
| 电话号码 (US Local DID) | ~$1/月 |
| 入站通话 | ~$0.002/分钟 |
| 出站通话 | ~$0.01/分钟 |
| Bedrock Nova Sonic | 按用量计费 |

## 常见问题

### 来电打不通
1. 确认 `RequireEncryption` 已设为 `false`
2. 确认 Origination 指向正确的 Elastic IP 和端口 5060/UDP
3. 确认安全组开放了 UDP 5060 和 UDP 10000-20000
4. 确认 Elastic IP 已绑定到 EC2 实例
5. 检查 Chime SIP 日志看 INVITE 是否发出

### 接通但没有声音
1. 确认安全组开放了 UDP 10000-20000（RTP 端口）
2. 确认 `PUBLIC_IP` 环境变量设置正确（应为 Elastic IP）
3. 检查 CloudWatch 日志是否有 RTP session 建立

### 无法打断 AI 说话
确认部署了包含 `RtpSession.clearQueue()` 的最新版本。当 Nova Sonic 检测到用户打断时，需要清空 RTP 发送缓冲区。

## 清理资源

```bash
# 1. 释放电话号码（Console 或 CLI）
aws chime-sdk-voice disassociate-phone-numbers-from-voice-connector \
  --voice-connector-id <your-voice-connector-id> \
  --e164-phone-numbers "+1XXXXXXXXXX" \
  --region us-east-1

# 2. 删除 Voice Connector
aws chime-sdk-voice delete-voice-connector \
  --voice-connector-id <your-voice-connector-id> \
  --region us-east-1

# 3. 释放电话号码
aws chime-sdk-voice delete-phone-number \
  --phone-number-id "<phone-number-id>" \
  --region us-east-1

# 4. 删除 CloudFormation 栈
cd infra && ./deploy.sh --destroy
```
