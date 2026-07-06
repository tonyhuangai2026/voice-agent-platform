# First-run admin setup / 首次设置管理员

> The admin account is created through an interactive **first-run setup wizard**
> the first time you open the site. There is **no** `ADMIN_PASSWORD` seed
> anymore.
>
> 管理员账号在**首次打开站点**时通过**首次设置向导**交互创建，**不再**使用
> `ADMIN_PASSWORD` 自动建号。

---

## English

### Why this exists

The old flow seeded an `admin` account from the `ADMIN_PASSWORD` parameter at
boot. That was removed because the CloudFormation user-data wrote `.env` with an
**unquoted heredoc**, so the instance shell expanded `$`, backticks, and other
special characters in the password **before** it was bcrypt-hashed
(e.g. `my$ecret` → `my`, `` `whoami` `` → executed as a command). The seeded
hash therefore did not match the password the operator typed, and login always
failed. The fix has two parts: the heredoc is now quoted (`<<'EOF'`) so
passwords survive byte-for-byte, **and** the admin account is created
interactively so there is no silent corruption path at all.

### The flow

After a fresh deploy the user table has no accounts, so:

1. Open the CloudFront `URL` from the stack outputs (allow 3–5 min for
   CloudFront to propagate).
2. The router sees `GET /api/auth/setup-status` → `{"needs_setup": true}` and
   redirects you to **`/setup`**.
3. Enter an **admin username** and **password** (confirm the password).
4. The frontend calls `POST /api/auth/setup`. On success the first admin account
   is created (`role=admin`), the session cookie is issued (**auto-login**), and
   you land on the admin home page.

### After setup — it self-closes

Once any account exists the wizard is permanently disabled and cannot reset or
overwrite an existing admin:

- `GET /api/auth/setup-status` → `{"needs_setup": false}`
- `POST /api/auth/setup` → `409 already initialized`
- Visiting `/setup` in the browser redirects away.
- Normal logins use the `/login` page (`POST /api/auth/login`), unchanged.

This is enforced server-side (the frontend guard is only a convenience): the
`setup` endpoint re-checks `needs_setup` and the underlying conditional
DynamoDB write means even a concurrent race produces exactly one admin; the
loser gets `409`, never `500`.

### Recovery if you are locked out

Because `ADMIN_PASSWORD` no longer re-seeds anything, the **only** way to get
the wizard back is to make the user table empty again. There is no
password-reset endpoint and no automatic re-seed.

The users table is DynamoDB, default name **`genaiic-voicebot-users`** (override
with the `USERS_TABLE` env var), partition key **`username`** (string). Connect
to the instance with SSM Session Manager — SSH is not exposed:

```bash
aws ssm start-session --target <InstanceId> --region us-east-1

# Inspect the table name actually in use (in case USERS_TABLE was overridden):
grep -E '^USERS_TABLE=' /opt/voicebot/.env || echo "USERS_TABLE not set -> default genaiic-voicebot-users"
TABLE=${USERS_TABLE:-genaiic-voicebot-users}

# List the current accounts:
aws dynamodb scan --table-name "$TABLE" --region us-east-1 \
  --projection-expression 'username,#r' \
  --expression-attribute-names '{"#r":"role"}'

# Delete a specific admin row (replace the username):
aws dynamodb delete-item --table-name "$TABLE" --region us-east-1 \
  --key '{"username":{"S":"admin"}}'
```

When the table holds **zero** accounts again, `setup-status` returns
`{"needs_setup": true}` and the next visit to the site sends you back to
`/setup`. (Deleting the whole table also works — a missing table reads as empty,
so the wizard reappears — but then it must be re-created with the same
`username` partition key before the wizard can write to it.) **Delete only the
rows you intend to; this is a destructive, irreversible operation.**

---

## 中文

### 背景

旧逻辑在启动时用 `ADMIN_PASSWORD` 参数自动创建 `admin` 账号。该机制已废弃：
CloudFormation 的 user-data 用**未加引号的 heredoc** 写 `.env`，实例 shell 会在
密码被 bcrypt 哈希**之前**展开其中的 `$`、反引号等特殊字符（例如
`my$ecret` → `my`，`` `whoami` `` 被当成命令执行），导致哈希的并非运维输入的原始
密码，登录必然失败。修复分两步：heredoc 现已加引号（`<<'EOF'`）让密码逐字符
保留，**并且**改为交互式创建管理员，从根本上消除静默损坏的路径。

### 流程

全新部署后用户表为空：

1. 打开栈输出里的 CloudFront `URL`（CloudFront 需 3–5 分钟生效）。
2. 路由检测到 `GET /api/auth/setup-status` → `{"needs_setup": true}`，自动跳转到
   **`/setup`**。
3. 输入**管理员用户名**和**密码**（并确认密码）。
4. 前端调用 `POST /api/auth/setup`。成功后创建首个管理员账号（`role=admin`），
   下发会话 Cookie（**自动登录**），进入后台首页。

### 设置后——向导自我关闭

一旦存在任何账号，向导即永久关闭，且无法重置或覆盖已有管理员：

- `GET /api/auth/setup-status` → `{"needs_setup": false}`
- `POST /api/auth/setup` → `409 already initialized`
- 浏览器访问 `/setup` 会跳回。
- 正常登录走 `/login`（`POST /api/auth/login`），行为不变。

这是**服务端**强制的（前端守卫只是便利）：`setup` 端点会复查 `needs_setup`，底层
DynamoDB 条件写保证即便并发也只会成功创建一个管理员，失败方返回 `409` 而非 `500`。

### 锁死后的恢复

由于 `ADMIN_PASSWORD` 不再重新建号，**唯一**让向导重新出现的方法是再次把用户表
清空。没有密码重置端点，也没有自动重新建号。

用户表是 DynamoDB，默认名 **`genaiic-voicebot-users`**（可用 `USERS_TABLE` 环境
变量覆盖），分区键为 **`username`**（字符串）。用 SSM Session Manager 连接实例
（未开放 SSH）：

```bash
aws ssm start-session --target <InstanceId> --region us-east-1

# 确认实际使用的表名（以防 USERS_TABLE 被覆盖）：
grep -E '^USERS_TABLE=' /opt/voicebot/.env || echo "未设置 USERS_TABLE -> 默认 genaiic-voicebot-users"
TABLE=${USERS_TABLE:-genaiic-voicebot-users}

# 列出当前账号：
aws dynamodb scan --table-name "$TABLE" --region us-east-1 \
  --projection-expression 'username,#r' \
  --expression-attribute-names '{"#r":"role"}'

# 删除某个管理员行（替换用户名）：
aws dynamodb delete-item --table-name "$TABLE" --region us-east-1 \
  --key '{"username":{"S":"admin"}}'
```

当表中账号数为**零**时，`setup-status` 返回 `{"needs_setup": true}`，下次访问站点
即跳回 `/setup`。（直接删整张表也可以——表缺失会被当作空表，向导同样重现——但之后
需用同样的 `username` 分区键重新建表，向导才能写入。）**只删你确实要删的行；该操作
具有破坏性且不可逆。**
