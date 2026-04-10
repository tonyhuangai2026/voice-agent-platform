# Amazon Chime SDK Voice Connector Setup Guide

This guide covers how to configure Amazon Chime SDK Voice Connector for the Voice Agent Platform to enable PSTN phone connectivity.

## Architecture Overview

```
Caller (PSTN)
    ↓ Dials Chime-assigned phone number
Amazon Chime Voice Connector
    ↓ SIP INVITE (UDP:5060)
Voice Agent Server (ECS EC2 + Elastic IP)
    ↓ Bidirectional RTP audio (UDP:10000-20000)
Amazon Bedrock Nova Sonic (Voice AI)
```

Voice Connector acts as a PSTN gateway, forwarding inbound calls to our server via standard SIP/RTP protocol, eliminating the need for third-party services like Twilio.

## Prerequisites

- AWS account with Amazon Chime SDK access enabled
- AWS CLI v2 configured
- Voice Agent Platform CloudFormation stack deployed (see main README)

## Step 1: Provision a Phone Number

1. Open **AWS Console → Amazon Chime SDK → Phone number management**
2. Click **Provision phone numbers**
3. Select **Voice Connector** as the product type
4. Choose country and number type:
   - **US Local DID**: ~$1/month, easiest to provision
   - **US Toll-Free**: ~$2/month
5. Search for available numbers, select one, and confirm

> **Note**: First-time provisioning may require a quota increase via **Service Quotas** or an **AWS Support Case**. Some countries require address verification. Approval typically takes 1-2 business days.

## Step 2: Create a Voice Connector

1. Open **Amazon Chime SDK Console → Voice Connectors**
2. Click **Create voice connector**
3. Configure:
   - **Name**: e.g., `voice-agent-vc`
   - **AWS Region**: Select `us-east-1` (same region as Bedrock Nova Sonic)
4. After creation, note the **Outbound host name**:
   ```
   xxxxx.voiceconnector.chime.aws
   ```
   This is the `CHIME_VOICE_CONNECTOR_HOST` needed for deployment.

## Step 3: Disable Encryption Requirement

> **Critical step!** Voice Connector defaults to requiring TLS + SRTP encryption, but our SIP/RTP implementation uses plaintext UDP. Failing to disable this will prevent all calls from connecting.

```bash
aws chime-sdk-voice update-voice-connector \
  --voice-connector-id <your-voice-connector-id> \
  --name "voice-agent-vc" \
  --no-require-encryption \
  --region us-east-1
```

Verify:
```bash
aws chime-sdk-voice get-voice-connector \
  --voice-connector-id <your-voice-connector-id> \
  --region us-east-1 \
  --query 'VoiceConnector.RequireEncryption'
# Should return: false
```

## Step 4: Associate Phone Number with Voice Connector

In **Phone number management**, associate the number from Step 1 with the Voice Connector.

Or via CLI:
```bash
aws chime-sdk-voice associate-phone-numbers-with-voice-connector \
  --voice-connector-id <your-voice-connector-id> \
  --e164-phone-numbers "+1XXXXXXXXXX" \
  --region us-east-1
```

## Step 5: Deploy Voice Agent Platform

See the main README for deployment instructions. After deployment, retrieve the **GatewayPublicIP** (Elastic IP) from CloudFormation outputs:

```bash
aws cloudformation describe-stacks \
  --stack-name voice-agent-platform \
  --query 'Stacks[0].Outputs[?OutputKey==`GatewayPublicIP`].OutputValue' \
  --output text --region us-east-1
```

## Step 6: Configure Voice Connector Origination

Route inbound calls to your server:

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

## Step 7: Configure Voice Connector Termination

Allow your server to make outbound calls through the Voice Connector:

```bash
# Set SIP credentials (for outbound calls)
aws chime-sdk-voice put-voice-connector-termination-credentials \
  --voice-connector-id <your-voice-connector-id> \
  --credentials '[{"Username":"<username>","Password":"<password>"}]' \
  --region us-east-1

# Enable Termination
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

## Step 8: Verify

1. Call the provisioned phone number
2. You should hear the AI greeting immediately
3. Check CloudWatch logs to confirm SIP INVITE and RTP session:
   ```bash
   aws logs tail /ecs/voice-agent-server --region us-east-1 --follow
   ```

## Enable Voice Connector Logging (Optional, for debugging)

```bash
aws chime-sdk-voice put-voice-connector-logging-configuration \
  --voice-connector-id <your-voice-connector-id> \
  --logging-configuration '{"EnableSIPLogs": true, "EnableMediaMetricLogs": true}' \
  --region us-east-1
```

Log locations:
- SIP messages: `/aws/ChimeVoiceConnectorSipMessages/<vc-id>`
- Call metrics: `/aws/ChimeVoiceConnectorLogs/<vc-id>`

## Cost Reference (us-east-1)

| Item | Cost |
|---|---|
| Phone number (US Local DID) | ~$1/month |
| Inbound calls | ~$0.002/minute |
| Outbound calls | ~$0.01/minute |
| Bedrock Nova Sonic | Pay-per-use |

## Troubleshooting

### Calls don't connect
1. Verify `RequireEncryption` is set to `false`
2. Verify Origination points to the correct Elastic IP on port 5060/UDP
3. Verify security groups allow inbound UDP 5060 and UDP 10000-20000
4. Verify the Elastic IP is associated with the EC2 instance
5. Check Chime SIP logs to see if INVITE was sent

### Call connects but no audio
1. Verify security groups allow inbound UDP 10000-20000 (RTP ports)
2. Verify the `PUBLIC_IP` environment variable is set correctly (should be the Elastic IP)
3. Check CloudWatch logs for RTP session establishment

### Cannot interrupt AI speech (barge-in)
Ensure you have deployed the latest version with `RtpSession.clearQueue()` support. When Nova Sonic detects user interruption, it clears the RTP outbound buffer to stop stale audio playback.

## Clean Up

```bash
# 1. Disassociate phone number
aws chime-sdk-voice disassociate-phone-numbers-from-voice-connector \
  --voice-connector-id <your-voice-connector-id> \
  --e164-phone-numbers "+1XXXXXXXXXX" \
  --region us-east-1

# 2. Delete Voice Connector
aws chime-sdk-voice delete-voice-connector \
  --voice-connector-id <your-voice-connector-id> \
  --region us-east-1

# 3. Release phone number
aws chime-sdk-voice delete-phone-number \
  --phone-number-id "<phone-number-id>" \
  --region us-east-1

# 4. Delete CloudFormation stack
cd infra && ./deploy.sh --destroy
```
