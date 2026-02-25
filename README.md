# Voice Agent Platform

一个基于 AWS 和 Amazon Nova Sonic 的企业级语音 AI 外呼平台，支持实时语音对话、多项目管理、通话监控和智能标签系统。

![Architecture](docs/architecture.svg)

## 📋 目录

- [功能特性](#-功能特性)
- [系统架构](#-系统架构)
- [技术栈](#-技术栈)
- [前置要求](#-前置要求)
- [安装部署](#-安装部署)
- [配置说明](#-配置说明)
- [使用指南](#-使用指南)
- [API 文档](#-api-文档)
- [安全说明](#-安全说明)
- [故障排查](#-故障排查)

## 🚀 功能特性

### 核心功能

#### 1. **用户认证系统**
- 🔐 JWT Token 认证
- 📧 邀请码注册机制
- 👤 用户登录/登出
- 🔒 全局 API 保护

#### 2. **多项目管理**
- 📊 多项目隔离（Project-based）
- 📈 项目仪表盘（统计数据）
- ⚙️ 项目级配置管理

#### 3. **客户管理**
- 👥 客户信息管理（姓名、手机、备注）
- 📥 CSV 批量导入
- 🏷️ 客户标签显示（最近通话）
- 📞 单个/批量外呼

#### 4. **提示词管理（Prompt Management）**
- 📝 自定义 AI 提示词模板
- 🔄 支持变量替换（`{{customer_name}}`, `{{notes}}`）
- 💾 提示词版本管理
- 🌐 项目级/全局提示词

#### 5. **语音流管理（Flow Management）**
- 🎯 通话流程配置
- 🔊 语音选择（Nova Sonic voices）
- ⚡ 流程激活/停用

#### 6. **实时通话监控（Live Monitor）**
- 📡 活跃通话实时显示
- 💬 实时转录查看（SSE 流式）
- ⏱️ 通话时长统计
- 👁️ 对话轮次监控

#### 7. **通话记录管理（Call History）**
- 📜 完整通话记录
- 💭 对话转录查看
- 🗂️ 状态过滤（完成/进行中）
- 🏷️ 手动标签标注
- 🤖 AI 自动标签（Claude Sonnet 4.6）
- 🔍 通话日志查看（Debug）

#### 8. **标签系统（Label Management）**
- 🏷️ 自定义标签维度
- ☑️ 单选/多选支持
- 🎨 标签可视化
- 🤖 AI 自动分类
- 📊 标签统计分析

#### 9. **通话日志系统**
- 📋 详细的通话事件日志
- 🐛 Debug 信息记录
- ⏰ 自动 30 天过期（TTL）
- 🔍 按通话 ID 查询

### 技术特性

- ⚡ **实时语音处理**：Amazon Nova Sonic voice-to-voice AI
- 🌊 **流式响应**：WebSocket 实时通信
- 🔄 **自动重试机制**：错误自动恢复
- 📊 **可扩展架构**：ECS Fargate 自动伸缩
- 🔒 **企业级安全**：JWT + 环境变量配置
- 🌐 **CDN 加速**：CloudFront 全球分发
- 💾 **NoSQL 存储**：DynamoDB 无服务器数据库

## 🏗️ 系统架构

### 架构组件

#### 前端层
- **React + TypeScript**：现代化 SPA 应用
- **Ant Design**：企业级 UI 组件库
- **CloudFront + S3**：静态资源托管与 CDN

#### API 层
- **API Gateway**：REST API 入口
- **Lambda (Python)**：无服务器业务逻辑
  - 用户认证
  - 客户管理
  - 项目管理
  - 标签配置
  - AI 自动标注

#### 语音处理层
- **ECS Fargate**：容器化 Node.js 服务
- **WebSocket**：实时双向通信
- **Amazon Nova Sonic**：语音 AI 模型
- **Twilio**：语音通话网关

#### 数据层
- **DynamoDB 表结构**：
  - `outbound-users` - 用户认证
  - `outbound-customers` - 客户信息
  - `outbound-projects` - 项目管理
  - `outbound-prompts` - 提示词模板
  - `outbound-flow-configs` - 流程配置
  - `outbound-call-records` - 通话记录
  - `label-configs` - 标签配置
  - `call-logs` - 通话日志（带 TTL）

### 数据流

```
┌─────────┐     HTTPS     ┌────────────┐
│  User   │ ───────────> │  Frontend  │
└─────────┘               └─────┬──────┘
                                │
                    ┌───────────┴──────────┐
                    │                      │
              REST API              WebSocket (SSE)
                    │                      │
            ┌───────▼──────┐       ┌──────▼───────┐
            │ API Gateway  │       │ Voice Server │
            │      +       │       │   (ECS)      │
            │   Lambda     │       └──────┬───────┘
            └───────┬──────┘              │
                    │                     │
                    │              ┌──────▼───────┐
                    │              │    Twilio    │
                    │              │  (Outbound)  │
                    │              └──────────────┘
                    │                     │
            ┌───────▼──────┐              │
            │   DynamoDB   │ <────────────┘
            └──────────────┘       Nova Sonic
                    │                     ▲
            ┌───────▼──────┐              │
            │   Bedrock    │──────────────┘
            │ (Nova Sonic) │
            └──────────────┘
```

## 💻 技术栈

### 前端
- **框架**：React 18 + TypeScript
- **UI 库**：Ant Design 5.x
- **状态管理**：React Context API
- **HTTP 客户端**：Axios
- **构建工具**：Vite

### 后端
- **语音服务**：Node.js 20 + TypeScript
- **API 服务**：Python 3.11
- **Web 框架**：Fastify (WebSocket)
- **实时通信**：Server-Sent Events (SSE)

### AWS 服务
- **计算**：Lambda, ECS Fargate
- **存储**：S3, DynamoDB
- **网络**：CloudFront, ALB, API Gateway
- **容器**：ECR
- **AI**：Amazon Bedrock (Nova Sonic)
- **认证**：自研 JWT 系统

### 第三方服务
- **语音通话**：Twilio Voice API
- **AI 标注**：Anthropic Claude Sonnet 4.6

## 📦 前置要求

### 必需
- AWS 账号（具备管理员权限）
- Twilio 账号（带可用电话号码）
- Node.js >= 20
- Python >= 3.11
- Docker（用于本地构建）
- AWS CLI v2
- 域名（可选，用于生产环境）

### AWS 配置
```bash
# 配置 AWS CLI
aws configure
# 输入：Access Key, Secret Key, Region (us-east-1), Output format (json)

# 验证配置
aws sts get-caller-identity
```

### Twilio 配置
1. 注册 Twilio 账号：https://www.twilio.com/
2. 购买电话号码
3. 创建 API Key
4. 获取以下凭证：
   - Account SID
   - API Key SID
   - API Key Secret
   - 电话号码（E.164 格式，如 +1234567890）

## 🚀 安装部署

### 1. 克隆仓库
```bash
git clone <repository-url>
cd voice-agent-platform
```

### 2. 配置环境变量

复制环境变量模板：
```bash
cp .env.example .env
```

编辑 `.env` 文件，填入实际值：
```bash
# Twilio 凭证
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxx
TWILIO_API_SID=SKxxxxxxxxxxxx
TWILIO_API_SECRET=your_secret_here
TWILIO_FROM_NUMBER=+1234567890

# AWS 区域
AWS_REGION=us-east-1

# 其他配置保持默认
```

### 3. 配置认证密钥

创建安全配置文件：
```bash
cd infra
cp .secrets.example .secrets
```

编辑 `.secrets` 文件：
```bash
# 生成强随机 JWT Secret
openssl rand -hex 32

# 编辑 .secrets
nano .secrets
```

填入密钥：
```bash
export JWT_SECRET="<生成的64位随机字符串>"
export INVITE_CODE="your-secret-invite-code"
```

### 4. 部署基础设施

#### 完整部署（首次部署）
```bash
cd infra
source .secrets  # 加载认证密钥
./deploy.sh      # 部署所有组件
```

这将依次执行：
1. 创建 CloudFormation 堆栈
2. 创建所有 DynamoDB 表
3. 构建并推送 Docker 镜像到 ECR
4. 部署 ECS 服务
5. 部署 Lambda 函数
6. 构建并部署前端到 S3

#### 分步部署
```bash
# 只部署基础设施
./deploy.sh --stack-only

# 只部署语音服务器（ECS）
./deploy.sh --deploy-only

# 只部署 Lambda API
./deploy.sh --lambda-only

# 只部署前端
./deploy.sh --frontend-only
```

### 5. 获取访问地址

部署完成后，查看输出：
```bash
aws cloudformation describe-stacks \
  --stack-name voice-agent-platform \
  --query 'Stacks[0].Outputs'
```

关键输出：
- **FrontendUrl**：前端访问地址（例如：`https://d2nwk8t6a2isa.cloudfront.net`）
- **CloudFrontDomain**：语音服务器地址（配置到 Twilio webhook）
- **ApiGatewayUrl**：API Gateway 地址

### 6. 配置 Twilio Webhook

1. 登录 Twilio Console
2. 进入 Phone Numbers > Manage > Active Numbers
3. 选择你的电话号码
4. 在 "Voice & Fax" 部分：
   - **A CALL COMES IN**: Webhook
   - **URL**: `<CloudFrontDomain>/voice-income` （例如：`https://d18w266j8eiz37.cloudfront.net/voice-income`）
   - **HTTP**: POST
5. 保存配置

## ⚙️ 配置说明

### 环境变量完整列表

#### 认证与安全
```bash
JWT_SECRET=<64位随机字符串>          # JWT 签名密钥
INVITE_CODE=<邀请码>                 # 用户注册邀请码
```

#### Twilio 配置
```bash
TWILIO_ACCOUNT_SID=ACxxxxxxxxx       # Twilio 账号 SID
TWILIO_API_SID=SKxxxxxxxxx           # Twilio API Key SID
TWILIO_API_SECRET=xxxxxxxxxx         # Twilio API Secret
TWILIO_FROM_NUMBER=+1234567890       # 外呼电话号码
```

#### AWS 配置
```bash
AWS_REGION=us-east-1                 # 主区域
CONNECT_REGION=us-west-2             # Amazon Connect 区域
DYNAMODB_REGION=us-east-1            # DynamoDB 区域
```

#### DynamoDB 表名
```bash
CUSTOMERS_TABLE=outbound-customers
PROMPTS_TABLE=outbound-prompts
FLOWS_TABLE=outbound-flow-configs
CALL_RECORDS_TABLE=outbound-call-records
PROJECTS_TABLE=outbound-projects
LABEL_CONFIGS_TABLE=label-configs
USERS_TABLE=outbound-users
CALL_LOGS_TABLE=call-logs
```

#### Nova Sonic 配置
```bash
VOICE_ID=tiffany                     # 语音 ID (tiffany/matthew/joey/salli)
TEMPERATURE=0.7                      # 模型温度 (0.0-1.0)
TOP_P=0.9                            # Top-p 采样
MAX_TOKENS=1024                      # 最大 token 数
MAX_CALL_DURATION_MS=1200000         # 最大通话时长（20分钟）
```

## 📖 使用指南

### 首次使用

#### 1. 注册账号
1. 访问前端 URL
2. 点击 "Register" 标签
3. 填写信息：
   - Name（姓名）
   - Email（邮箱）
   - Password（密码，至少6位）
   - Invite Code（邀请码）
4. 注册成功后自动登录

#### 2. 创建项目
1. 点击顶部 "Manage" 按钮
2. 点击 "Create Project"
3. 填写项目信息：
   - Project Name（项目名称）
   - Description（描述）
   - Status（状态：active/inactive）
4. 保存后自动切换到新项目

#### 3. 配置提示词
1. 点击左侧 "Prompts" 菜单
2. 点击 "Create Prompt" 按钮
3. 填写提示词：
   - Prompt Name（名称）
   - Prompt Content（内容）
     - 可用变量：`{{customer_name}}`, `{{notes}}`
   - Active（是否激活）
4. 保存

#### 4. 导入客户
1. 点击左侧 "Customers" 菜单
2. 点击 "Import CSV" 按钮
3. 准备 CSV 文件格式：
   ```csv
   customer_name,phone_number,email,notes,voice_id,prompt_id
   张三,+8613800138000,zhangsan@example.com,VIP客户,tiffany,prompt-id-xxx
   ```
4. 粘贴 CSV 内容并提交

#### 5. 创建标签
1. 点击左侧 "Labels" 菜单
2. 点击 "Create Label" 按钮
3. 配置标签：
   - Label Name（标签名称，如 "客户意向"）
   - Options（选项列表，用逗号分隔）
   - Selection Type（单选/多选）
4. 保存

#### 6. 发起外呼
1. 在 "Customers" 页面选择客户
2. 点击 "Call" 按钮
3. 系统自动发起外呼
4. 可在 "Live Monitor" 查看实时通话

### 日常使用

#### 查看实时通话
1. 点击 "Live Monitor"
2. 查看当前活跃通话列表
3. 点击通话可查看实时转录

#### 查看通话记录
1. 点击 "Call History"
2. 查看所有通话记录
3. 点击 "View" 查看对话内容
4. 点击 "Label" 手动标注
5. 点击 "Auto" AI 自动标注
6. 点击 "Logs" 查看详细日志

#### 标注管理
**手动标注**：
1. 在 Call History 点击 "Label"
2. 根据标签配置选择/填写标签值
3. 保存

**自动标注**：
1. 在 Call History 点击 "Auto"
2. 系统使用 Claude Sonnet 4.6 分析对话
3. 自动应用所有已配置的标签

#### 客户管理增强
- 客户列表显示最近一通电话的标签
- 标签格式：`标签名: 值`
- 点击客户查看详细信息

## 📚 API 文档

### 认证 API

#### 注册
```http
POST /api/auth/register
Content-Type: application/json

{
  "email": "user@example.com",
  "password": "password123",
  "name": "John Doe",
  "invite_code": "your-invite-code"
}
```

#### 登录
```http
POST /api/auth/login
Content-Type: application/json

{
  "email": "user@example.com",
  "password": "password123"
}
```

#### 验证 Token
```http
GET /api/auth/verify
Authorization: Bearer <token>
```

### 客户管理 API

#### 列出客户
```http
GET /api/customers?project_id=<project_id>&limit=100
Authorization: Bearer <token>
```

#### 创建客户
```http
POST /api/customers
Authorization: Bearer <token>
Content-Type: application/json

{
  "customer_name": "张三",
  "phone_number": "+8613800138000",
  "email": "zhangsan@example.com",
  "notes": "VIP客户",
  "project_id": "project-id-xxx"
}
```

#### 批量导入
```http
POST /api/customers/import
Authorization: Bearer <token>
Content-Type: application/json

{
  "csv_content": "customer_name,phone_number,...\n张三,+8613800138000,...",
  "project_id": "project-id-xxx"
}
```

### 通话记录 API

#### 列出通话记录
```http
GET /api/call-records?limit=100&status=completed
Authorization: Bearer <token>
```

#### 获取通话日志
```http
GET /api/call-records/{call_sid}/logs
Authorization: Bearer <token>
```

#### 更新通话标签
```http
PUT /api/call-records/{call_sid}/labels
Authorization: Bearer <token>
Content-Type: application/json

{
  "labels": {
    "label-id-1": "选项A",
    "label-id-2": ["选项1", "选项2"]
  }
}
```

#### AI 自动标注
```http
POST /api/call-records/{call_sid}/auto-label
Authorization: Bearer <token>
```

### 实时监控 API

#### 活跃通话列表
```http
GET /api/active-calls
```

#### 实时转录流（SSE）
```http
GET /api/live-transcript/{call_sid}
```

## 🔒 安全说明

### 认证机制
- **JWT Token**：7天有效期
- **密码加密**：SHA256 哈希存储
- **邀请码验证**：注册需要有效邀请码
- **API 保护**：所有业务 API 需要认证

### 环境变量保护
- `.env` 文件已加入 `.gitignore`
- `.secrets` 文件已加入 `.gitignore`
- CloudFormation 参数使用 `NoEcho: true`

### 最佳实践
1. **定期轮换密钥**：
   ```bash
   # 生成新的 JWT Secret
   openssl rand -hex 32

   # 更新 CloudFormation
   source .secrets
   ./deploy.sh --stack-only
   ```

2. **限制 IAM 权限**：仅授予必需权限
3. **启用 CloudTrail**：审计所有 API 调用
4. **定期备份 DynamoDB**：开启 Point-in-Time Recovery
5. **监控异常登录**：设置 CloudWatch 告警

## 🐛 故障排查

### 前端无法访问
**症状**：前端页面 404 或加载失败

**解决方案**：
```bash
# 检查 CloudFront 分发状态
aws cloudfront list-distributions

# 清除 CloudFront 缓存
aws cloudfront create-invalidation \
  --distribution-id <DISTRIBUTION_ID> \
  --paths "/*"
```

### 登录失败
**症状**：提示 "Invalid email or password"

**解决方案**：
1. 检查 JWT_SECRET 是否正确配置
2. 验证 Lambda 环境变量：
   ```bash
   aws lambda get-function-configuration \
     --function-name outbound-api \
     --query 'Environment.Variables'
   ```
3. 查看 Lambda 日志：
   ```bash
   aws logs tail /aws/lambda/outbound-api --follow
   ```

### 通话无法接通
**症状**：点击 Call 后无响应或立即挂断

**解决方案**：
1. 检查 Twilio Webhook 配置
2. 验证 ECS 服务状态：
   ```bash
   aws ecs describe-services \
     --cluster voice-agent-cluster \
     --services voice-agent-service
   ```
3. 查看 ECS 日志：
   ```bash
   aws logs tail /ecs/voice-agent-service --follow
   ```

### 实时转录无数据
**症状**：Live Monitor 显示通话但无转录

**解决方案**：
1. 检查浏览器控制台是否有 SSE 连接错误
2. 验证 CORS 配置
3. 检查 WebSocket/SSE 连接

## 📊 监控和日志

### CloudWatch 日志位置
- **Lambda API**：`/aws/lambda/outbound-api`
- **Voice Server**：`/ecs/voice-agent-service`
- **Call Logs**：存储在 DynamoDB `call-logs` 表（30天 TTL）

### 关键指标
- Lambda 调用次数、错误率
- DynamoDB 读写容量
- ECS CPU/内存使用率
- 通话成功率

## 🔄 更新和维护

### 更新前端
```bash
cd /path/to/voice-agent-platform/infra
./deploy.sh --frontend-only
```

### 更新 Lambda API
```bash
cd /path/to/voice-agent-platform/infra
./deploy.sh --lambda-only
```

### 更新语音服务器
```bash
cd /path/to/voice-agent-platform/infra
./deploy.sh --deploy-only
```

### 更新基础设施
```bash
cd /path/to/voice-agent-platform/infra
source .secrets
./deploy.sh --stack-only
```


---

**Built with ❤️ using Amazon Nova Sonic and AWS**
