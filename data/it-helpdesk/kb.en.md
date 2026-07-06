# IT Help Desk on Amazon Connect — Knowledge Base

> Self-service-first voice solution for the ITSC team.
> Powered by Amazon Connect + Nova Sonic (speech-to-speech) + AWS Lambda + Case (ITSM).
> Identity is verified via SMS OTP — no voice enrollment.

---

## 1 · Solution Overview

Design principle: **voice first → intent detection → self-serve when possible →
graceful escalation otherwise**, with end-to-end auto-ticketing.

### 1.1 Three pillars

- **Voice entry & identity** — Amazon Connect terminates PSTN/SIP inbound
  calls. Identity verification uses **SMS OTP** (employee ID + registered
  mobile + 6-digit code). Simple, reliable, zero user onboarding.

- **Nova Sonic S2S model** — Amazon Nova Sonic is a single end-to-end
  speech-to-speech model that handles ASR + NLU + TTS. Natural prosody,
  low latency, barge-in friendly. Replaces the traditional Lex + Polly stack.

- **Automation & ticketing** — AWS Lambda calls Active Directory / Entra ID
  to perform the unlock, and automatically creates / updates / resolves
  incidents in Case (ITSM).

### 1.2 Key targets

| Metric | Target |
|---|---|
| Self-service rate | ≥ 65% |
| Average call length | < 90 s |
| Ticket automation | 100% |
| P1 pickup time | < 30 s |

---

## 2 · Reference Architecture

### 2.1 End-to-end call path

```
Employee → PSTN/SIP → Amazon Connect (Contact Flow / IVR)
                         │
                         ├─► Nova Sonic (Speech-to-Speech LLM, ASR+NLU+TTS)
                         │       │
                         │       └─► AWS Lambda (orchestration)
                         │              ├─► Active Directory / Entra ID
                         │              ├─► Case (ITSM)
                         │              └─► DynamoDB (OTP store, session)
                         │
                         ├─► Pinpoint / SNS (SMS OTP delivery)
                         ├─► Kinesis Video Streams ─► S3 (recording archive)
                         └─► CloudWatch + Contact Lens (analytics)

         │ Routing decision
         ├─► Self-serve OK → Auto-resolve (call ends)
         └─► Needs human → Agent Workspace (CCP + screen pop)
```

### 2.2 Service stack

| Service | Role |
|---|---|
| Amazon Connect | IVR · Routing · Agent desktop |
| Nova Sonic | End-to-end speech-to-speech LLM |
| AWS Lambda | AD unlock · Tickets · Orchestration |
| Pinpoint / SNS | SMS OTP delivery |
| Contact Lens | Call analytics · Sentiment |
| Case | ITSM ticketing system |
| DynamoDB | OTP store · Session context |
| S3 + KMS | Recording archive · Retention |

---

## 3 · Demo Scenarios

Five representative ITSC call patterns, each with its own call flow,
automation, and escalation strategy.

### 3.1 Scenario 1 · Account Unlock via Phone (fully automated)

**Trigger**: caller asks to unlock their account; phone self-service is
eligible (registered mobile is on file, policy allows it).
**Routing pill**: ● Fully automated · S2S model.

#### Flow

```
1. Inbound call → Connect contact flow → start Nova Sonic bidirectional
   S2S session.
2. Nova Sonic: "Hi, IT service desk here. How can I help?"
3. Caller: "My account is locked, please unlock it."
4. Nova Sonic intent = UnlockAccount, slot empId.
5. Nova Sonic asks for employee ID, caller reads it; Sonic reads back digit
   by digit to confirm.
6. Lambda fn-send-otp:
     - looks up registered mobile in AD
     - calls Pinpoint/SNS to send a 6-digit OTP
     - stores OTP in DynamoDB with TTL 5 min, max 3 attempts
7. Nova Sonic asks the caller to read the SMS code aloud.
8. Lambda fn-ad-unlock unlocks the AD account via Graph API / PowerShell.
9. Same Lambda calls Case REST API: create + auto-resolve Incident,
    Category = "Access/Unlock", Caller = verified employee.
10. Nova Sonic confirms ticket number; SNS sends a confirmation SMS;
    call ends.
```

#### Targets

- Identity method: SMS OTP
- OTP validity: 5 minutes
- Max attempts: 3
- Voice engine: Nova Sonic
- Goal: zero human touch, < 90 seconds, no voice enrollment

#### Example dialog

> Sam: "Hi, this is Sam from the IT service desk. How can I help?"
> Caller: "My account is locked."
> Sam: "Got it — let me get that unlocked. Could you give me your employee ID?"
> Caller: "W123456."
> Sam: "Just to confirm, W-one-two-three-four-five-six. Correct?"
> Caller: "Yes."
> Sam: "I just texted a 6-digit code to your phone on file. Can you read it back to me?"
> Caller: "Eight two four one five seven."
> Sam: "Thanks. … You're unlocked. Ticket INC-zero-zero-one-two-three-four-five.
>      Anything else?"

---

### 3.2 Scenario 2 · Redirect to Virtual Agent for unlock

**Trigger**: caller asks to unlock their account, but phone self-service
is **not eligible** (no registered mobile, policy requires stronger MFA,
caller is in a tier that requires digital verification).
**Routing pill**: ● Digital hand-off.

#### Flow

```
1. Inbound call → Nova Sonic intent = UnlockAccount.
2. Contact flow checks contact attributes → phone self-service NOT allowed.
3. Nova Sonic: "I'll send a secure link to your work Teams or SMS so we
   can finish the unlock there."
4. Lambda sends a one-time deep-link token (TTL 5 min) to the employee
   via SNS SMS + Teams bot.
5. Virtual Agent (Copilot Studio / Amazon Q Business) "Unlock" topic
   takes over; runs MFA challenge, then continues the unlock.
6. The VA invokes the SAME fn-ad-unlock Lambda — phone and digital
   channels stay consistent, with one ticket taxonomy.
7. Ticket number + audit trail are written back to the original Connect
   contact as attributes for unified analytics.
```

#### Why hand off, not force phone

Voice + AD unlock requires strong identity. SMS OTP alone is fine for
simple account unlocks; for callers in higher-risk groups we route to
the digital channel where we can run a stronger MFA challenge.

---

### 3.3 Scenario 3 · MFA Re-registration enquiry — education + digital handoff

**Trigger**: caller asks how to re-register their MFA / bind a new
authenticator device.
**Routing pill**: ● Education + digital delivery.

#### Why we don't do this purely on voice

Binding a new MFA device is a **sensitive operation**. We don't perform
it purely over the phone — too risky. Instead: short voice education,
then push the detailed guide to Teams + SMS.

#### Flow

```
1. Caller: "How do I re-register my MFA?"
2. Nova Sonic intent = MfaReRegister.
3. Sam reads a concise 3-step summary:
     - Remove old device in your account portal
     - Go to aka.ms/mfasetup
     - Scan the QR code with the new authenticator app
4. Sam: "Want me to text you the detailed walk-through?"
5. On confirmation, Lambda pushes a Teams adaptive card + KB deep link.
6. Case opens a Service Request (NOT an Incident), status = Awaiting user.
7. Sam confirms: "Sent to your Teams. SR-zero-zero-zero-nine-eight-seven
   has been logged. Have a great day."
8. If the SR is not completed in 48 hours, an agent callback flow is
   auto-triggered.
```

---

### 3.4 Scenario 4 · Caller insists on a human — graceful escalation

**Trigger**:
- Caller says "agent", "human", "real person", or
- Two consecutive no-match events on Nova Sonic, or
- Sentiment trend negative for 2+ turns.
**Routing pill**: ● Human escalation.

**Rule**: never force self-service. The "say agent any time" fallback
is available throughout the call.

#### Flow

```
1. Nova Sonic detects SpeakToHuman intent (or fall-through trigger).
2. Sam: "No problem, I'll connect you to a specialist."
3. Contact flow writes contact attributes:
     empId, lastIntent, otpStatus, ticketId, transcriptUri
4. Skill-based routing to queue:
     - Account / Network / Endpoint
     - VIP / Normal priority
5. Agent CCP answers; CTI adapter does screen pop with a pre-filled
   ticket in Case Agent Workspace — agent is context-aware from word 1.
6. After-call work auto-completes the ticket; agent only adjusts as needed.
```

#### Tone

Calm, apologetic, not pushy. "I'm sorry the bot couldn't get you sorted —
let me get a person on this right away."

---

### 3.5 Scenario 5 · Critical Incident (P1) — express lane

**Trigger**: caller uses critical-severity keywords:
- "production is down" / "production outage"
- "everyone is affected" / "the whole office can't log in"
- "critical" / "emergency"
- Contact Lens secondary signal: sentiment = NEGATIVE high.

**Routing pill**: ● P1 express lane.

#### Flow (skip self-service entirely)

```
1. Caller: "Production is completely down!"
2. Nova Sonic intent = ReportIncident, severity = CRITICAL.
3. Contact Lens confirms: NEGATIVE high sentiment.
4. SKIP all self-service — do NOT ask for employee ID or non-essential
   info first. Speed beats verification here.
5. Lambda fan-out (parallel):
     - Case: open P1 Incident, auto-create war room
     - PagerDuty: page on-call (P1)
     - Teams: war-room channel
     - Exec notifications
6. Sam: "Escalated as P1, ticket INC-zero-zero-nine-nine-zero-zero-one.
   Connecting the on-call manager now."
7. Direct connect to Major Incident Manager skill group, bypassing the
   normal queue. SLA < 30 seconds.
8. Contact Lens streams the live transcript to the MIM so the caller
   does not have to repeat the story.
9. Post-incident: recording + transcript archived to S3, attached to
   the PIR (Post Incident Review) record.
```

---

## 4 · Routing & Escalation Matrix

```
Inbound call
   │
   ▼
Capture employee ID
   │
   ▼
Nova Sonic intent classification
   │
   ├── UnlockAccount + OTP eligible      ─►  Scenario 1 (auto unlock)
   ├── UnlockAccount + OTP not eligible  ─►  Scenario 2 (redirect to VA)
   ├── MfaReRegister                      ─►  Scenario 3 (education + push)
   ├── SpeakToHuman / 2× no-match         ─►  Scenario 4 (graceful human)
   ├── ReportIncident severity=P1         ─►  Scenario 5 (P1 express lane)
   └── Other                              ─►  Fallback: FAQ playback +
                                              human escalation
```

---

## 5 · Security, Compliance & Observability

### 5.1 SMS OTP identity

- Employee ID + registered mobile + 6-digit OTP
- TTL 5 minutes, max 3 attempts
- Rate limit: 1 OTP per employee per 10 minutes
- No voice enrollment, zero onboarding effort

### 5.2 Recording & transcripts

- S3 server-side encryption with KMS CMK
- Object Lock retention (regulatory)
- Contact Lens auto-redacts PII (card numbers, PINs, SSN, etc.)

### 5.3 Observability

- CloudWatch dashboards: self-service rate, abandon rate, queue wait,
  P1 pickup time
- QuickSight: weekly report to the ITSC manager
- Per-call drill-down: Connect contact ID → Lambda invocation logs →
  Case ticket → Contact Lens transcript

---

## 6 · Frequently Asked Caller Phrases (intent training reference)

| Caller phrase | Intent |
|---|---|
| "My account is locked", "I can't log in", "It says too many failed attempts" | UnlockAccount |
| "I got a new phone, how do I set up MFA again?", "My authenticator app is on the old phone" | MfaReRegister |
| "Connect me to a person", "Get me a real human", "I want to talk to someone" | SpeakToHuman |
| "Production is down", "Nothing is working", "The whole company can't log in", "It's an outage" | ReportIncident severity=P1 |

---

## 7 · What to do when the KB doesn't cover something

If the caller's question is not in the 5 scenarios above and not in the
"FAQ phrases" list, do NOT invent steps. Say:

> "That one's outside what I can do on this line. Let me hand you to a
> specialist who can help."

Then route to Scenario 4 (human escalation).
