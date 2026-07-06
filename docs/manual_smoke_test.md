# Manual Smoke Test — Demo Management Unification + LLM Tools

End-to-end runbook for the unified Demo / Scenario refactor (T1–T7) and the
per-demo `end_call` / `transfer_to_human` LLM tools.

This runbook is **manual** because the validation requires real PSTN calls
against Chime SDK Voice Connector and a real browser session against the
prod CloudFront distribution. It is the acceptance gate for T8.

## Environment

| Field | Value |
|---|---|
| Stack | `genaiic-voicebot` (us-east-1) |
| Public IP (EIP) | `<PROD_EIP>` |
| EC2 instance | `<EC2_INSTANCE_ID>` |
| CloudFront | `https://d1pgfy89z1l3mf.cloudfront.net/` |
| PSTN entry (zh-HK) | `+1 555-000-1111` (Chime VC `yue-test`, `<VOICE_CONNECTOR_ID>`) |
| DDB history | `genaiic-voicebot-call-history` |
| Demo under test | `it-helpdesk` (zh-HK) + `default` (en-US, no-KB sanity) |

> **DO NOT** widen SG `<SECURITY_GROUP_ID>`. It is locked to the AWS-published
> Chime VC CIDRs (`99.77.254.0/24`, `3.80.16.0/23`); previous incidents flooded
> Bedrock / MiniMax tokens via fake INVITEs from PSTN scanners.

## Pre-flight

1. `git log --oneline -1` should land on the unified-demo merge commit (current
   head: `36f335a Unify Scenario / Demo as a single concept + add per-demo LLM
   tool selection` or later).
2. `curl -s https://d1pgfy89z1l3mf.cloudfront.net/api/admin/tools -u admin:<pw>`
   returns both `end_call` and `transfer_to_human` with
   `scope: ["phone","web"]`.
3. `curl -s https://d1pgfy89z1l3mf.cloudfront.net/api/admin/demos -u admin:<pw>
   | jq '.demos[] | select(.id=="it-helpdesk") | .tools'` →
   `["end_call","transfer_to_human"]`.
4. SSM tail in two panes:
   ```bash
   aws ssm start-session --target <EC2_INSTANCE_ID> --region us-east-1
   sudo tail -f /var/log/voicebot.log
   sudo tail -f /var/log/voiceserver.log
   ```

## Phase A — Phone + Nova Sonic + it-helpdesk (zh-HK)

### Step 1 · Confirm demo tools

Open `https://d1pgfy89z1l3mf.cloudfront.net/admin/` → **Demos** → `it-helpdesk`
→ Tools tab. Confirm both `end_call` and `transfer_to_human` are checked. If
not, check them and Save.

### Step 2 · Confirm phone defaults

`https://d1pgfy89z1l3mf.cloudfront.net/admin/` → **Phone Defaults** →
`PHONE_ENGINE = nova-sonic`, `PHONE_LANG = zh-HK`, `PHONE_SCENARIO =
it-helpdesk` (note: now labelled "Demo"), `PHONE_VOICE = tiffany`. Save.
This restarts the bot; wait ~5s.

### Step 3 · Place call — say "拜拜"

Dial `+1 555-000-1111`. After Sam's greeting, say (Cantonese):
> 我冇嘢喇,拜拜

**Expected — voicebot.log:**
```
[tools] demo=it-helpdesk scope=phone registered=['end_call', 'transfer_to_human']
FunctionCallFromLLM(end_call) reason=user_requested
[end_call] tool fired reason=user_requested
[history] write_outcome reason=user_requested
```

**Expected — voiceserver.log:**
```
[SIP] Sending BYE for call=<call-id>
[SIP] BYE sent, RTP closed
```

**Expected — DDB:**
```bash
aws dynamodb get-item --region us-east-1 \
  --table-name genaiic-voicebot-call-history \
  --key '{"call_id":{"S":"<call-id>"}}' \
  --query 'Item.outcome.S' --output text
# → user_requested
```

→ AC `2a376d38` PASS / FAIL.

### Step 4 · Place call — say "转人工"

Dial again. After greeting, say:
> 我要轉真人客服

**Expected — voicebot.log:**
```
FunctionCallFromLLM(transfer_to_human) topic=...
[transfer_to_human] tool fired topic=<caller issue>
[history] mark_transfer transfer_requested=true
```

**Expected — DDB top-level row attributes (T6 patch surfaces these at the row
top level so the Connect Flow Lambda can read them on next dip):**
```bash
aws dynamodb get-item --region us-east-1 \
  --table-name genaiic-voicebot-call-history \
  --key '{"call_id":{"S":"<call-id>"}}' \
  --query 'Item.{tr:transfer_requested.BOOL,topic:transfer_topic.S}'
# → {"tr": true, "topic": "<caller issue>"}
```

→ AC `fdf03951` PASS / FAIL.

## Phase B — Phone + 三段式 (Bedrock) + it-helpdesk

### Step 5 · Switch to pipeline engine

```bash
aws ssm send-command --region us-east-1 --instance-ids <EC2_INSTANCE_ID> \
  --document-name AWS-RunShellScript --parameters \
  'commands=["sed -i s/^PHONE_ENGINE=.*/PHONE_ENGINE=pipeline/ /opt/voicebot/.env && systemctl restart voicebot && sleep 3 && systemctl is-active voicebot"]'
```

Confirm `is-active = active`. Wait 10s for VAD warmup.

### Step 6 · Repeat steps 3 + 4

Dial. Say "拜拜". Then dial again. Say "转人工".

**Expected — voicebot.log (note the engine label):**
```
[tools] demo=it-helpdesk scope=phone registered=['end_call', 'transfer_to_human']
[BedrockLLMService] tool_use end_call args={"reason": "user_requested"}
[BedrockLLMService] tool_use transfer_to_human args={"topic": "..."}
```

DDB rows + SIP BYE same as Phase A.

→ AC `872601e1` PASS / FAIL.

**Restore Nova Sonic afterwards:**
```bash
aws ssm send-command --region us-east-1 --instance-ids <EC2_INSTANCE_ID> \
  --document-name AWS-RunShellScript --parameters \
  'commands=["sed -i s/^PHONE_ENGINE=.*/PHONE_ENGINE=nova-sonic/ /opt/voicebot/.env && systemctl restart voicebot"]'
```

## Phase C — Web (双管线)

### Step 7 · Web + Nova Sonic + zh-HK

Open `https://d1pgfy89z1l3mf.cloudfront.net/demo/`. Pick:
- Demo: `it-helpdesk`
- Engine: `Nova Sonic`
- Language: `zh-HK`

Click **Start**. After greeting, say or type "再见".

**Expected — voicebot.log:**
```
[tools] demo=it-helpdesk scope=web registered=['end_call', 'transfer_to_human']
FunctionCallFromLLM(end_call) reason=user_requested
[end_call] tool fired (web scope, mark_transfer=None, write_outcome=None)
WebSocket disconnect
```

**Expected — DDB:** no new row (web scope passes `None` for `mark_transfer` /
`write_outcome` / `history_append`). Verify via:
```bash
PRE=$(aws dynamodb scan --region us-east-1 \
  --table-name genaiic-voicebot-call-history --select COUNT --query Count)
# ...do the web call...
POST=$(aws dynamodb scan --region us-east-1 \
  --table-name genaiic-voicebot-call-history --select COUNT --query Count)
# PRE == POST (no new outcome row)
```

→ AC `9f48614a` PASS / FAIL.

### Step 8 · Web + 三段式 (Bedrock + Polly)

Same demo, switch Engine to `三段式 / Pipeline (Bedrock)`. Click Start. Say
"再见". Repeat the log + DDB checks.

→ AC `fd659cc0` PASS / FAIL (looks for the second `[tools] scope=web` line).

### Step 9 · Confirm both `[tools] scope=web` log lines

```bash
sudo grep -E '\[tools\] demo=it-helpdesk scope=web' /var/log/voicebot.log | tail -5
```

Should show one line per web pipeline build (Nova Sonic + 三段式).

## Phase D — Tools toggle

### Step 10 · Empty the demo's tools list

Admin UI → Demos → `it-helpdesk` → Tools tab → uncheck both → Save.

Or via REST:
```bash
curl -X PATCH -u admin:<pw> \
  -H 'Content-Type: application/json' \
  -d '{"tools":[]}' \
  https://d1pgfy89z1l3mf.cloudfront.net/api/admin/demos/it-helpdesk
```

### Step 11 · Rescan + restart

```bash
curl -X POST -u admin:<pw> \
  https://d1pgfy89z1l3mf.cloudfront.net/api/admin/demos/rescan

aws ssm send-command --region us-east-1 --instance-ids <EC2_INSTANCE_ID> \
  --document-name AWS-RunShellScript \
  --parameters 'commands=["systemctl restart voicebot"]'
```

### Step 12 · Phone call must NOT trigger end_call

Dial `+1 555-000-1111`. After greeting, say "拜拜".

**Expected — voicebot.log:**
```
[tools] demo=it-helpdesk scope=phone registered=[]
```
No `FunctionCallFromLLM(end_call)`. The bot continues conversing or hangs up
on the natural inactivity timeout. Manual hangup ends the call.

→ AC `16841e90` PASS / FAIL.

### Step 13 · Restore tools

Re-check both tools, save, rescan, restart. Re-test step 3 to confirm the
behaviour is restored.

## Phase E — Default demo + no KB

### Step 14 · Web + default + en-US + Nova Sonic

Admin → Demos → confirm `default` exists with `tools: []` and the
`description: Default (no demo)`.

`https://d1pgfy89z1l3mf.cloudfront.net/demo/` → Demo `default`, Engine
`Nova Sonic`, Language `en-US`. Click Start. Say a free-form greeting.

**Expected:**
- voicebot.log shows pipeline builds without an "Unknown KB" or "missing KB"
  error. The system prompt should include the demo's default `system` text
  without a KB body.
- The bot greets you ("Hi, how can I help?" or whatever is in the default
  manifest greeting). No traceback in logs.

```bash
sudo grep -E 'demo=default' /var/log/voicebot.log | tail -3
sudo grep -iE 'kb missing|kb not found|FileNotFoundError' /var/log/voicebot.log | tail -5
# second grep should be empty
```

→ AC `eea478ca` PASS / FAIL.

## Reporting

Once all 14 steps run, paste a 14-row PASS / FAIL table into
`chorus_report_work` for T8 (`4a857eb8-f06b-457b-9491-6eab57e3c08a`)
along with at least 6 verbatim log lines or SIP traces as evidence.

If anything FAILs:
- Capture the exact log window and the call_id.
- Reopen the relevant T1–T7 task or open a follow-up bug, do not silently
  mark the AC pending.
