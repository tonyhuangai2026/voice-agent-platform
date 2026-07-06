# IT 服務台知識庫 · Amazon Connect

> ITSC 團隊嘅語音優先解決方案。
> Amazon Connect + Nova Sonic(端到端語音模型) + AWS Lambda + Case (ITSM)。
> 身份驗證用 SMS OTP — 唔需要聲紋註冊。

---

## 1 · 整體方案

設計原則:**語音優先 → 意圖識別 → 可以自助就自助 → 唔得就優雅升級**,
全程自動開單。

### 1.1 三大支柱

- **語音入口同身份驗證** — Amazon Connect 接 PSTN/SIP 入站電話。
  身份驗證用 **SMS OTP**(員工編號 + 已登記手機 + 6 位短訊驗證碼)。
  簡單可靠,員工零額外步驟。

- **Nova Sonic 端到端模型** — Amazon Nova Sonic 係單一端到端語音模型,
  內置 ASR + NLU + TTS。語調自然、低延遲、支援打斷,
  取代咗傳統嘅 Lex + Polly 雙服務架構。

- **自動化同單據** — AWS Lambda 調 Active Directory / Entra ID 解鎖,
  並自動喺 Case 開單、更新、關單。

### 1.2 關鍵指標

| 指標 | 目標 |
|---|---|
| 自助成功率 | ≥ 65% |
| 平均通話時長 | < 90 秒 |
| 單據自動化率 | 100% |
| P1 接聽時長 | < 30 秒 |

---

## 2 · 參考架構

### 2.1 端到端通話鏈路

```
員工 → PSTN/SIP → Amazon Connect (Contact Flow / IVR)
                       │
                       ├─► Nova Sonic (端到端語音 LLM, ASR+NLU+TTS)
                       │       │
                       │       └─► AWS Lambda (業務編排)
                       │              ├─► Active Directory / Entra ID
                       │              ├─► Case (ITSM)
                       │              └─► DynamoDB (OTP / session)
                       │
                       ├─► Pinpoint / SNS (SMS OTP 投遞)
                       ├─► Kinesis Video Streams ─► S3 (錄音歸檔)
                       └─► CloudWatch + Contact Lens (分析)

       │ 路由決策
       ├─► 自助 OK → 自動結案(掛電話)
       └─► 要真人 → Agent Workspace (CCP + 屏幕彈窗)
```

### 2.2 服務清單

| 服務 | 角色 |
|---|---|
| Amazon Connect | IVR · 路由 · 客服桌面 |
| Nova Sonic | 端到端語音模型 |
| AWS Lambda | AD 解鎖 · 單據 · 編排 |
| Pinpoint / SNS | SMS OTP 發送 |
| Contact Lens | 通話分析 · 情緒識別 |
| Case | ITSM 單據系統 |
| DynamoDB | OTP 存儲 · 上下文 |
| S3 + KMS | 錄音歸檔 · 保留策略 |

---

## 3 · 五個演示場景

ITSC 團隊五種典型話務模式,每個有自己嘅話務流、自動化同升級策略。

### 3.1 場景一 · 電話自助解鎖(全自動)

**觸發**:客戶要解鎖 account,而且合資格電話自助(已登記手機、政策容許)。
**路由標籤**:● 全自動 · S2S 模型。

#### 流程

```
1. 入站電話 → Connect contact flow → 啟動 Nova Sonic 雙向 S2S session。
2. Nova Sonic:「你好,IT 服務台。」
3. 客戶:「我 account 俾人鎖咗,可唔可以幫我解鎖。」
4. Nova Sonic 識別意圖 = UnlockAccount,準備收 empId 槽位。
5. 叫客戶報員工編號,逐位讀番一次確認。
6. Lambda fn-send-otp:
     - 查 AD 攞登記手機
     - 調 Pinpoint/SNS 發 6 位 OTP
     - 寫入 DynamoDB,TTL 5 分鐘,最多試 3 次
7. Nova Sonic 叫客戶讀番短訊嘅 6 位碼。
8. Lambda fn-ad-unlock 調 Graph API / PowerShell 解鎖。
9. 同一個 Lambda 調 Case REST API:開單同自動關 Incident,
    Category = Access/Unlock,Caller = 已驗證員工。
10. Nova Sonic 念番單號;SNS 發確認短訊;通話結束。
```

#### 關鍵參數

- 身份驗證:SMS OTP
- OTP 有效期:5 分鐘
- 最多嘗試:3 次
- 語音引擎:Nova Sonic
- 目標:零人工、< 90 秒、唔需要聲紋註冊

#### 對話例

> Sam:「你好,呢度係 IT 服務台嘅 Sam,有咩可以幫到你?」
> 客戶:「我 account 俾人鎖咗。」
> Sam:「了解,等我幫你解鎖。請問你員工編號?」
> 客戶:「W123456。」
> Sam:「再確認下,W-1-2-3-4-5-6,啱唔啱?」
> 客戶:「啱。」
> Sam:「我啱啱發咗一個 6 位短訊驗證碼到你電話,可唔可以讀番俾我聽?」
> 客戶:「8 2 4 1 5 7。」
> Sam:「多謝…你嘅 account 已經解鎖咗,單號 INC-0-0-1-2-3-4-5,
>      仲有冇其他要幫手?」

---

### 3.2 場景二 · 轉虛擬客服解鎖

**觸發**:客戶要解鎖,但**唔合資格電話自助**(冇登記手機、政策要更強 MFA、
高風險用戶組)。
**路由標籤**:● 數字渠道交接。

#### 流程

```
1. 入站 → Nova Sonic 識別意圖 = UnlockAccount。
2. Contact Flow 檢查 contact attributes → 客戶唔合資格電話自助。
3. Nova Sonic:「我即刻發個安全鏈接到你嘅 Teams 或者短訊,
   去嗰邊完成解鎖。」
4. Lambda 透過 SNS 短訊 + Teams bot 發一次性深鏈(TTL 5 分鐘)。
5. Virtual Agent (Copilot Studio / Amazon Q Business) 嘅「解鎖」
   topic 接手,跑 MFA 挑戰然後繼續解鎖。
6. VA 調**同一個** fn-ad-unlock Lambda — 電話同數字渠道行為一致,
   單據分類都一致。
7. 單號同審計寫番原 Connect contact 做 attributes,統一分析。
```

#### 點解唔強逼電話自助

語音 + AD 解鎖要強身份驗證。簡單解鎖 SMS OTP 夠用,
但高風險用戶組要走數字渠道做更強嘅 MFA 挑戰。

---

### 3.3 場景三 · MFA 重新綁定 — 教育 + 數字渠道

**觸發**:客戶問點重新綁定 MFA / 點換新設備。
**路由標籤**:● 教育 + 數字推送。

#### 點解唔喺電話度做

綁新 MFA 係**敏感操作**,純語音渠道做風險太大。改成:
口頭講重點 + 推詳細步驟到 Teams + 短訊。

#### 流程

```
1. 客戶:「我換咗手機,MFA 點重新綁?」
2. Nova Sonic 識別意圖 = MfaReRegister。
3. Sam 口頭講 3 步重點:
     - 喺 account portal 入面刪除舊設備
     - 開 aka.ms/mfasetup
     - 用新嘅認證 app 掃二維碼
4. Sam:「需要我將詳細步驟發俾你嗎?」
5. 客戶確認後,Lambda 推一張 Teams adaptive card + KB 深鏈。
6. Case 開一張 Service Request(唔係 Incident),狀態 Awaiting user。
7. Sam:「已經發咗去你 Teams,單號 SR-0-0-0-9-8-7,有問題再嚟電。」
8. 48 小時仲未完成,系統自動觸發客服回撥流程。
```

---

### 3.4 場景四 · 客戶堅持要真人 — 優雅升級

**觸發**:
- 客戶話「人工」、「真人」、「搵個人嚟」,或者
- Nova Sonic 連續兩次 no-match,或者
- 情緒連續 2 輪以上偏負面。
**路由標籤**:● 人工升級。

**原則**:絕對唔強逼自助。「隨時可以話 搵人工」嘅兜底全程都喺度。

#### 流程

```
1. Nova Sonic 識別 SpeakToHuman 意圖(或者觸發兜底)。
2. Sam:「冇問題,我即刻幫你轉俾專門嘅同事。」
3. Contact flow 寫 contact attributes:
     empId, lastIntent, otpStatus, ticketId, transcriptUri
4. 按技能 + 優先級路由 queue:
     - Account / Network / Endpoint
     - VIP / 普通
5. 客服 CCP 接聽;CTI adapter 屏幕彈窗預填 Case 單據 — 第一句話
   就上下文對齊。
6. 通話後處理(ACW)自動補完單據,客服只做必要調整。
```

#### 語氣

平靜、致歉,唔強推。「唔好意思機器搞唔掂,等我即刻搵專人嚟處理。」

---

### 3.5 場景五 · 嚴重事故(P1) — 緊急通道

**觸發**:客戶用關鍵字:
- 「生產掛咗」、「production down」、「production outage」
- 「成間公司都登唔到」、「成個 office 都受影響」
- 「critical」、「emergency」、「緊急」
- Contact Lens 二級訊號:情緒 = 強烈負面。

**路由標籤**:● P1 緊急通道。

#### 流程(完全跳過自助)

```
1. 客戶:「生產環境完全掛咗!」
2. Nova Sonic 識別意圖 = ReportIncident, severity = CRITICAL。
3. Contact Lens 確認:情緒強烈負面。
4. **跳過所有自助** — 唔好問員工編號或者任何非必要嘅嘢,
   速度優先於驗證。
5. Lambda 並行 fan-out:
     - Case:開 P1 Incident,自動建戰時室
     - PagerDuty:呼 on-call(P1)
     - Teams:戰時室頻道
     - 高管通知
6. Sam:「已經升級做 P1,單號 INC-0-0-9-9-0-0-1,
   即刻幫你接埋值班經理。」
7. 直接接 Major Incident Manager 技能組,跳過普通 queue,SLA < 30 秒。
8. Contact Lens 實時將轉錄推俾 MIM,客戶唔使重複講多次。
9. 事後:錄音 + 轉錄歸檔到 S3,掛去 PIR(事後復盤)記錄上面。
```

---

## 4 · 路由同升級矩陣

```
入站電話
   │
   ▼
收員工編號
   │
   ▼
Nova Sonic 意圖分類
   │
   ├── UnlockAccount + OTP 合資格        →  場景 1(自動解鎖)
   ├── UnlockAccount + OTP 唔合資格      →  場景 2(轉 VA)
   ├── MfaReRegister                      →  場景 3(教育 + 推指引)
   ├── SpeakToHuman / 連續兩次 no-match   →  場景 4(優雅人工)
   ├── ReportIncident severity=P1         →  場景 5(P1 緊急通道)
   └── 其他                               →  兜底:FAQ 播報 + 轉人工
```

---

## 5 · 安全、合規、可觀測

### 5.1 SMS OTP 身份驗證

- 員工編號 + 登記手機 + 6 位 OTP
- TTL 5 分鐘,最多試 3 次
- 限流:每個員工 10 分鐘最多 1 個 OTP
- 唔需要聲紋註冊,員工零成本

### 5.2 錄音同轉錄

- S3 server-side encryption + KMS CMK
- Object Lock 保留策略(合規)
- Contact Lens 自動 redact PII(卡號、PIN、身份證等)

### 5.3 可觀測

- CloudWatch dashboard:自助率、放棄率、queue 等待、P1 接聽時長
- QuickSight:每週報告俾 ITSC manager
- 單通話鑽取:Connect contact ID → Lambda log → Case 單 → Contact Lens 轉錄

---

## 6 · 常見客戶原話(意圖訓練參考)

| 客戶原話 | 意圖 |
|---|---|
| 「我 account 俾人鎖咗」、「登唔到」、「話我試太多次」 | UnlockAccount |
| 「我換咗新手機 MFA 點算」、「認證 app 喺舊手機度」 | MfaReRegister |
| 「轉人工」、「搵個真人」、「我要同人講」 | SpeakToHuman |
| 「生產掛咗」、「全公司都登唔到」、「呢度生產事故」 | ReportIncident severity=P1 |

---

## 7 · 知識庫冇覆蓋嘅時候

如果客戶嘅問題唔喺上面 5 個場景入面,亦唔喺 FAQ 列表入面,**唔好作答**。
照實話:

> 「呢個問題超出我喺電話上面可以處理嘅範圍,等我幫你轉去專門嘅同事。」

然後走場景四(人工升級)。
