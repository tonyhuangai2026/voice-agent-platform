# Connect Repair 语音演示脚本（家电上门维修）

> 现场对着麦克风/电话念客户台词，把语音 bot 逐步驱动去调用挂载的 6 个
> MCP 工具（verifyCustomer / verifyCustomerByPhoneAndName / requestRepair /
> trackRepair / cancelRepair / faqSearch）。所有台词都用过**实测跑通的真实
> 测试数据**，对着真 AgentCore 后台能跑通。
>
> demo id: `connect-repair` ｜ 语言: 普通话(zh-CN) + 粤语(zh-HK) ｜ 角色: 客服 Sam

---

## 0. 演示前准备（一次性）

MCP 工具调用需要 LLM function-calling，所以必须用 **pipeline 引擎**（Bedrock），
不能用 Nova Sonic 端到端。

1. 打开 Admin → **Web 默认** (或 **Phone 默认**)：
   - Engine = `pipeline`
   - Demo = `connect-repair`
   - Language = 普通话 (zh-CN) 或 粤语 (zh-HK)
   - TTS / Voice 按现场喜好
   - 保存（新会话生效，已开的会话不受影响）
2. （可选自检）Admin → **MCP 服务器** → connect-repair 行点 **Test**：
   应返回 **6 个工具**，证明 SigV4 连接通。
3. 到 `/talk` 点中间按钮开始，或拨电话线。

> ⚠️ 现场提示：所有编号、电话、验证码 bot 都会**逐位读回确认**，这是设计行为
> （语音场景防听错），不是卡顿。号码请你也逐位念。

---

## 1. Happy Path — 报修（verifyCustomer → requestRepair）

**演示重点**：强制身份核验在前 → 报修工具拿到 10 位工单号。

| # | 你（客户）念 | bot 会做什么 / 预期 |
|---|------------|-------------------|
| 1 | （bot 先开场）"你好，这里是家电维修服务，我是客服 Sam，请问有什么可以帮您？" | 开场白 |
| 2 | **"我家空调坏了，想报修。"** | Sam 复述确认，并说要先核验身份，请你报手机号 + 手机号后四位 |
| 3 | **"手机号 13800001234，后四位 1234。"** | 调用 **verifyCustomer**(userNumber=13800001234, smsToken=1234) → 拿到 customerId 令牌（内部，不会念给你）。确认身份通过 |
| 4 | **"空调不制冷，需要上门检修。"** | Sam 开始收集报修信息，会逐项问下面这些 |
| 5 | **"美的（Midea）牌的，型号不太清楚。"** | 记下 brand=Midea（型号可选，不强求） |
| 6 | **"地址是广东省深圳市南山区。"** | province=广东省 / city=深圳市 / district=南山区 |
| 7 | 若 Sam 问版本/套餐：**"smart version。"** | productsubCategory 必须 ∈ {smart version, premium version, elite version} |
| 8 | （信息齐了） | 调用 **requestRepair** → 返回 **10 位工单号 woNumber**，Sam 逐位读给你听 |
| 9 | **"好的，麻烦记一下工单号。"** | ✅ 把 bot 念的 10 位号记下来（每次都不同），第 2、3 节要用 |

**实测参数**（可直接照念）：
- userNumber `13800001234`，smsToken `1234`
- 大家电 / smart version / 广东省·深圳市·南山区 / 品牌 Midea / "空调不制冷"

---

## 2. 查询进度（trackRepair）

承接上一通，或新开一通（新开需重新核验拿令牌）。

| # | 你念 | bot / 预期 |
|---|------|-----------|
| 1 | **"我想查一下刚才那个维修工单的进度。"** | Sam 要 10 位工单号（若新会话还会先重新核验身份） |
| 2 | **"工单号是 X-X-X-…（念第 1 节记下的 10 位）。"** | 调用 **trackRepair**(woNumber, customerId) → 念出当前状态（如 `pending` 待处理） |
| 3 | **"知道了，谢谢。"** | ✅ 状态来自工具，非 bot 编造 |

---

## 3. 取消工单（cancelRepair）

| # | 你念 | bot / 预期 |
|---|------|-----------|
| 1 | **"这个工单我不想修了，帮我取消。"** | Sam 要 10 位工单号（+ 同一令牌） |
| 2 | **"工单号 X-X-X-…（同上 10 位）。"** | 调用 **cancelRepair** → 确认取消 |
| 3 | （演示边界）**"再帮我取消一次。"** | 已取消/已完成再取消会失败，Sam 会如实告知（不会假装成功） |

---

## 4. 常见问题（faqSearch — 免身份核验）

**演示重点**：faqSearch 不需要令牌，任何时候可问。

| # | 你念 | bot / 预期 |
|---|------|-----------|
| 1 | **"你们空调保修多久？"** | 直接调用 **faqSearch**(query) → 念检索结果（无需先核验身份） |
| 2 | **"上门维修怎么收费？"** | 再次 faqSearch；查不到时 Sam 会说"帮您转人工同事"，不会瞎编 |

---

## 5. 备用核验路径（verifyCustomerByPhoneAndName）

**演示重点**：主核验查不到时，自动转手机号 + 姓名的备用核验，二次失败转人工不死循环。

| # | 你念 | bot / 预期 |
|---|------|-----------|
| 1 | **"我要报修，但我记不清短信验证码了。"** | Sam 先试 verifyCustomer；若返回 CUSTOMER_NOT_FOUND / INVALID_USER_NUMBER… |
| 2 | **"我手机号 13800001234，名字叫张伟。"** | 转 **verifyCustomerByPhoneAndName**(phoneNumber, fullName) |
| 3 | （若再次查不到） | Sam 礼貌地说帮你转人工，**不会反复重试**（设计行为） |

---

## 6. 粤语版关键台词（zh-HK）

把默认语言切成粤语后，照念这几句即可走通同样流程：

- 报修：**"我部冷氣壞咗，想報修。"**
- 报手机：**"電話 13800001234，後四位 1234。"**
- 描述 + 地址：**"冷氣唔凍，要上門整。地址係廣東省深圳市南山區。"**
- 查询：**"幫我查下嗰張維修單嘅進度，單號係 …"**
- 取消：**"呢張單唔修喇，幫我取消。"**
- FAQ：**"你哋冷氣保養期幾耐？"**

---

## 7. 现场话术小抄（讲解者用）

演示时可以这样向观众点题：

1. **"这个维修能力，bot 本身一行业务代码都没有——全部来自挂载的 MCP server。"**
   （manifest 里 `tools: []`，能力来自 `mcp_servers: [connect-repair]`）
2. **"MCP server 跑在 AWS Bedrock AgentCore 上，bot 用 EC2 实例角色 SigV4 签名直连，
   没有任何写死的密钥。"**
3. **"身份核验是强制的——任何报修/查询/取消之前，bot 一定先 verifyCustomer 拿令牌，
   令牌整轮对话复用。"**
4. **"工单号、状态都是工具真返回的，bot 不会编。"**（防幻觉）
5. 想换一套维修后台？**"只在 admin 里换个 MCP server 配置，不动代码。"**

---

## 8. 出问题时（现场排障）

| 现象 | 可能原因 / 处理 |
|------|----------------|
| bot 说"我只是文字客服"之类 | 引擎选错了（用了非 pipeline）；确认 Engine=pipeline + Demo=connect-repair |
| 一直不调用工具 | 同上；或网络/IAM，先在 admin MCP 页点 connect-repair 的 **Test** 看是否出 6 工具 |
| Test 报错 | SigV4/IAM 问题；prod 实例角色需有 `bedrock-agentcore:InvokeAgentRuntime`（已配） |
| 报修说核验失败 | 用实测数据 `13800001234 / 1234`；或走第 5 节备用核验 |
| 工单号每次不一样 | 正常，requestRepair 每次生成新的 10 位 woNumber，记当次那个即可 |
