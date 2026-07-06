# Manual Phone Test — Hangup / Transfer Tools

LLM-driven `end_call` and `transfer_to_human` tools are wired into the phone
pipeline (Nova Sonic and three-stage Bedrock). Default-on for the running
EC2 voicebot via `PHONE_TOOLS_ENABLED=1`.

## Phone number

Dial **+1 555-000-1111** (yue-test Chime Voice Connector → Nova Sonic →
HK / EN / CN / JP support persona).

## Test scripts

For each language, wait for the bot's greeting, then say one of the
hang-up / transfer phrases below. Expected behaviour: bot speaks a brief
polite farewell **first**, then within ~2 seconds the call disconnects.

### English (en-US)
- "Thank you, that's all. Goodbye." → `end_call(reason="user_requested")`
- "Please transfer me to a real human agent." → `transfer_to_human(topic=...)`
- After resolving an issue, "Yes, that worked, we're all set." →
  `end_call(reason="task_completed")`

### Cantonese (zh-HK)
- 「唔該晒，我唔需要喇，再見。」 → `end_call(reason="user_requested")`
- 「我想搵真人客服。」 → `transfer_to_human(topic=...)`
- 「搞掂晒喇，多謝。」 (after a confirmed resolution) →
  `end_call(reason="task_completed")`

### Mandarin (zh-CN)
- 「谢谢，没别的事了，再见。」 → `end_call(reason="user_requested")`
- 「我要人工客服。」 → `transfer_to_human(topic=...)`
- 「问题解决了，谢谢。」 (after a confirmed resolution) →
  `end_call(reason="task_completed")`

### Japanese (ja-JP)
- 「ありがとうございました、これで結構です。さようなら。」 →
  `end_call(reason="user_requested")`
- 「人間のオペレーターに繋いでください。」 →
  `transfer_to_human(topic=...)`
- 「解決しました、ありがとうございました。」 (after a confirmed
  resolution) → `end_call(reason="task_completed")`

### Counter-example (must NOT trigger hangup)

A bare "Thank you" / 「多謝」 / 「谢谢」 / 「ありがとう」 alone — without
an explicit goodbye and without confirming the issue is resolved — should
**not** end the call. The bot must keep the dialogue going and ask "Is
there anything else I can help with?"

## Expected behaviour

1. Bot says a brief farewell sentence (e.g., "Glad to help, have a great
   day, goodbye." / 「多謝你嘅來電，再見。」).
2. Within ~2 seconds (the `GRACE_SECONDS` grace period in
   `call_control_tools.py`), the pipeline pushes `EndTaskFrame`, the
   WebSocket closes, and the SIP BYE propagates to Chime → PSTN.
3. The PSTN side hears tone / disconnect.

## Where to look for evidence

### voicebot.log (`/var/log/voicebot.log` on the EC2)

```
sudo grep -E "registering call-control tools call_id=" /var/log/voicebot.log
sudo grep -E "(end_call|transfer_to_human) call_id=" /var/log/voicebot.log
```

Expected:
- One `registering call-control tools call_id=<id>` line per phone leg.
- One `end_call call_id=<id> reason=<...>` line per LLM-issued hangup.
- One `transfer_to_human call_id=<id> topic=...` line per transfer.

### voice-server log (Node SIP bridge, journalctl)

```
sudo journalctl -u voiceserver --since "10 minutes ago" | grep -E "pipecat-closed|SIP BYE|endCall"
```

Expected:
- `pipecat-closed` event fires when `/phone/ws` closes from the bot side.
- A SIP BYE is sent to Chime.

## Rollback

If the tool registration is causing problems, disable it without
redeploying code:

```bash
ssh ubuntu@<ec2-public-ip>
sudo sed -i 's/^PHONE_TOOLS_ENABLED=.*/PHONE_TOOLS_ENABLED=0/' /opt/voicebot/.env
sudo systemctl restart voicebot
```

After this, the phone pipeline still runs but no tools are registered with
the LLM, and the bot can no longer hang up itself — calls end only on
caller hangup.

## Deployment record

- Tarball: `s3://genaiic-voicebot-deploy-<AWS_ACCOUNT_ID>-us-east-1/code-hangup-1779293622.tar.gz`
- Followup tarball with loguru fix: see task `c185f333-a71c-4203-835e-f568aac536e5` report.
- EC2 instance: `<EC2_INSTANCE_ID>` (`genaiic-voicebot-ec2`,
  public IP `54.221.119.13`).
