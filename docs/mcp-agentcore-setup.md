# Connecting the bot to your AWS Bedrock AgentCore MCP server
# 将语音机器人接入你自己的 AWS Bedrock AgentCore MCP 服务

This bot integrates Model Context Protocol (MCP) servers **by configuration, not
code**. If you already have an MCP server deployed on **AWS Bedrock AgentCore**,
follow these steps to let the bot call its tools. No code changes required.

本机器人**通过配置（而非改代码）**接入 MCP 服务。如果你已经在 **AWS Bedrock
AgentCore** 上部署了 MCP 服务，按下面步骤即可让机器人调用它的工具，无需改任何代码。

---

## 0. Prerequisite — IAM permission (REQUIRED) / 前提：IAM 权限（必做）

The bot signs AgentCore calls with the EC2 instance role using AWS SigV4 — **no
secret is stored**. That role must be allowed to invoke your runtime. The
CloudFormation template does **not** include this permission, so add it once.

机器人用 EC2 实例角色以 AWS SigV4 签名调用 AgentCore（**不存任何密钥**）。该角色必须
被授权调用你的 runtime。CloudFormation 模板**未包含**此权限，需手动加一次。

1. Find the instance role (logical id `InstanceRole`): in the AWS console go to
   **IAM → Roles** and search for `<STACK_NAME>-InstanceRole-…`
   (e.g. `voicebot-InstanceRole-ABC123`).
2. Add an inline policy (e.g. name it `agentcore-invoke`) with this statement —
   replace the region, account id, and runtime name with **your own**:

在 IAM 控制台找到实例角色 `<栈名>-InstanceRole-…`，添加一条 inline policy（如命名
`agentcore-invoke`），把区域 / 账号 / runtime 名换成**你自己的**：

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "InvokeAgentCore",
      "Effect": "Allow",
      "Action": "bedrock-agentcore:InvokeAgentRuntime",
      "Resource": [
        "arn:aws:bedrock-agentcore:<REGION>:<ACCOUNT_ID>:runtime/<RUNTIME_NAME>",
        "arn:aws:bedrock-agentcore:<REGION>:<ACCOUNT_ID>:runtime/<RUNTIME_NAME>/*"
      ]
    }
  ]
}
```

> `<REGION>` is where your AgentCore runtime lives (e.g. `eu-central-1` or
> `us-east-1`). It does **not** have to match the bot's deploy region.
> `<REGION>` 是你 AgentCore runtime 所在区域，**不必**和机器人部署区相同。

---

## 1. Build the AgentCore invocation URL / 拼接 AgentCore 调用 URL

AgentCore is invoked over HTTPS at this URL shape. The runtime ARN must be
**URL-encoded** (every `:` → `%3A`, every `/` → `%2F`):

调用 URL 格式如下。runtime ARN 必须 **URL 编码**（`:` → `%3A`，`/` → `%2F`）：

```
https://bedrock-agentcore.<REGION>.amazonaws.com/runtimes/<URL-ENCODED-ARN>/invocations?qualifier=DEFAULT
```

Easiest way to produce it — run this once with your ARN:
最省事的生成方法（用你的 ARN 跑一次）：

```bash
python3 - <<'PY'
from urllib.parse import quote
REGION = "eu-central-1"   # your AgentCore region / 你的 AgentCore 区域
ARN = "arn:aws:bedrock-agentcore:eu-central-1:111122223333:runtime/my_mcp_server-abc123"
print(f"https://bedrock-agentcore.{REGION}.amazonaws.com"
      f"/runtimes/{quote(ARN, safe='')}/invocations?qualifier=DEFAULT")
PY
```

---

## 2. Register the MCP server in the Admin console / 在 Admin 界面注册 MCP 服务

1. Open the bot URL (the CloudFront URL printed by `deploy.sh`) and log in as admin.
2. Go to **MCP Servers** → **Add server** and fill in:

打开机器人地址（`deploy.sh` 输出的 CloudFront URL），用管理员登录 → **MCP 服务器** →
**添加服务**，填写：

| Field / 字段 | Value / 值 |
|---|---|
| **ID** | a short slug, e.g. `my-agentcore` (lowercase, 2-63 chars) |
| **Transport** | `streamable_http` |
| **URL** | the URL from step 1 / 第 1 步拼出的 URL |
| **Auth / 认证** | **AWS SigV4** |
| **Service** | `bedrock-agentcore` |
| **Region** | your AgentCore region, e.g. `eu-central-1` / 你的 AgentCore 区域 |

SigV4 stores **no secret** — it signs at connect time with the instance role.
SigV4 **不存密钥**，连接时用实例角色实时签名。

Save. / 保存。

---

## 3. Test the connection / 测试连接

On the server row, click **Test**. It connects (3 s timeout), lists the tools,
and disconnects, returning `{ok, tools, error}`:

在该服务行点 **Test**（测试）。它会连接（3 秒超时）、列出工具、断开，返回 `{ok, tools, error}`：

- **Success / 成功** → you see the tool names exposed by your MCP server.
- **Fails / 失败** → check, in order: the IAM policy in step 0 (most common),
  the region in the auth config, and the URL encoding in step 1.

最常见的失败原因是第 0 步的 IAM 权限没加对。

---

## 4. Mount the MCP server on a demo / 把 MCP 挂到 demo 上

A registered server isn't used until a demo mounts it.

注册后的服务还要挂到某个 demo 才会生效。

1. Go to **Demos**, open the demo you want.
2. In the **MCP** section, check your server, and save.
3. The change applies to the **next** new session (web or phone).

去 **Demos** 页，打开目标 demo → 在 **MCP** 区勾选你的服务 → 保存。**下一通新会话**生效。

> MCP tool calls need LLM function-calling, so run the demo with the
> **pipeline** engine (not Nova Sonic). Set this under Admin → Web / Phone
> defaults → Engine = `pipeline`.
> MCP 工具调用需要 LLM function-calling，所以该 demo 要用 **pipeline** 引擎
> （不是 Nova Sonic）。在 Admin → Web/Phone 默认里把 Engine 设为 `pipeline`。

---

## Notes / 说明

- The MCP registry lives in `config/mcp_servers.json` on the instance. It is
  gitignored and contains **no secrets** for SigV4 servers (only service +
  region). You can edit it directly instead of using the UI, then restart the
  service — but the Admin console is the supported path.
- Header-based auth (e.g. `Authorization: Bearer …`) is also supported for
  non-AgentCore MCP servers; those header values ARE stored and are masked in
  the UI. SigV4 is the right choice for AgentCore.

- MCP 注册表是实例上的 `config/mcp_servers.json`，已 gitignore；SigV4 服务**不含密钥**
  （只有 service + region）。也可直接改该文件再重启服务，但推荐用 Admin 界面。
- 非 AgentCore 的 MCP 也支持 Header 认证（如 `Authorization: Bearer …`），这类 header
  值会被存储并在界面中掩码显示。接 AgentCore 请用 SigV4。
