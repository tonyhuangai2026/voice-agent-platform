# Changelog

All notable changes to Voice Agent Platform will be documented in this file.

## [1.0.0] - 2024-02-25

### 🎉 首次发布

完整的企业级语音AI外呼平台，基于 Amazon Nova Sonic 和 AWS 无服务器架构。

### ✨ 新功能

#### 认证与安全
- 🔐 JWT Token 认证系统
- 📧 邀请码注册机制
- 👤 用户登录/登出
- 🔒 全局 API 保护
- 🔑 环境变量配置安全密钥

#### 项目管理
- 📊 多项目隔离支持
- 📈 项目统计仪表盘
- ⚙️ 项目级配置管理
- 🎯 项目切换器（Header 位置）

#### 客户管理
- 👥 客户 CRUD 操作
- 📥 CSV 批量导入
- 🏷️ 客户标签展示（最近通话）
- 📞 单个/批量外呼
- 📝 客户备注字段
- 🔍 客户搜索和过滤

#### 提示词系统
- 📝 自定义 AI 提示词模板
- 🔄 变量替换支持（`{{customer_name}}`, `{{notes}}`）
- 💾 提示词版本管理
- 🌐 项目级/全局提示词
- ✏️ 富文本编辑器

#### 语音流配置
- 🎯 通话流程管理
- 🔊 Nova Sonic 语音选择
- ⚡ 流程激活/停用
- 🔧 流程参数配置

#### 实时监控
- 📡 活跃通话实时列表
- 💬 实时转录查看（Server-Sent Events）
- ⏱️ 通话时长实时统计
- 👁️ 对话轮次监控
- 🔄 3秒自动刷新

#### 通话记录
- 📜 完整通话历史
- 💭 对话转录展示
- 🗂️ 状态过滤（完成/活跃）
- 🔍 客户搜索
- 📊 通话统计数据
- 🗑️ 记录删除功能

#### 标签系统
- 🏷️ 自定义标签维度
- ☑️ 单选/多选类型
- 🎨 标签可视化展示
- ✏️ 手动标注界面
- 🤖 AI 自动标注（Claude Sonnet 4.6）
- 📊 标签聚合统计

#### 通话日志
- 📋 详细事件日志记录
  - Call started/ended
  - User utterances
  - Assistant responses
  - Errors and warnings
  - Farewell detection
  - Max duration timeout
- 🐛 Debug 信息完整
- ⏰ 30天自动过期（DynamoDB TTL）
- 🔍 按 callSid 快速查询
- 📊 结构化元数据存储

#### UI/UX
- 🎨 浅色主题设计
- 📱 响应式布局
- 🎯 直观的导航结构
- 💫 流畅的交互动画
- ⚡ 快速加载体验

### 🏗️ 技术架构

#### 前端
- React 18 + TypeScript
- Ant Design 5.x UI 组件
- Vite 构建工具
- Axios HTTP 客户端
- Context API 状态管理
- Server-Sent Events 实时流

#### 后端 API
- AWS Lambda (Python 3.11)
- API Gateway (HTTP API)
- DynamoDB 数据存储
- AWS Bedrock (Claude Sonnet 4.6)
- JWT 认证中间件

#### 语音服务
- Node.js 20 + TypeScript
- Fastify Web 框架
- WebSocket 实时通信
- Amazon Nova Sonic AI
- Twilio Voice API
- DynamoDB 日志存储

#### 基础设施
- CloudFormation IaC
- ECS Fargate 容器服务
- ECR Docker 镜像仓库
- CloudFront CDN
- Application Load Balancer
- S3 静态托管
- DynamoDB 8张表
- CloudWatch 日志

### 📊 DynamoDB 表结构

| 表名 | 主键 | GSI | 用途 |
|-----|------|-----|------|
| `outbound-users` | email | - | 用户认证 |
| `outbound-customers` | customer_id | phone-index | 客户信息 |
| `outbound-projects` | project_id | status-index | 项目管理 |
| `outbound-prompts` | prompt_id | - | 提示词模板 |
| `outbound-flow-configs` | flow_id | - | 流程配置 |
| `outbound-call-records` | callSid | status-startTime-index | 通话记录 |
| `label-configs` | label_id | project-index | 标签配置 |
| `call-logs` | callSid + timestamp | - | 通话日志（TTL 30天） |

### 🔒 安全特性

- ✅ JWT Token 7天有效期
- ✅ 密码 SHA256 哈希
- ✅ 邀请码验证注册
- ✅ 环境变量隔离敏感信息
- ✅ CloudFormation NoEcho 参数
- ✅ HTTPS 全站加密
- ✅ CORS 跨域保护
- ✅ API 全局认证中间件
- ✅ 401 自动登出机制

### 📦 部署特性

- ✅ 一键部署脚本（`deploy.sh`）
- ✅ 分步部署支持
  - `--stack-only`: 仅基础设施
  - `--deploy-only`: 仅语音服务
  - `--lambda-only`: 仅 API 服务
  - `--frontend-only`: 仅前端
- ✅ 环境变量自动注入
- ✅ CloudFormation 完整管理
- ✅ Docker 多平台构建
- ✅ 自动 ECR 推送
- ✅ ECS 滚动更新
- ✅ CloudFront 缓存失效

### 🐛 修复的问题

#### 安全修复
- 🔒 移除邀请码硬编码（改为环境变量）
- 🔒 移除 JWT Secret 弱默认值（强制配置）
- 🔒 移除前端 API endpoint 硬编码
- 🔒 添加 .secrets 文件到 .gitignore
- 🔒 Lambda 环境变量强制验证

#### 功能修复
- 🐛 修复 Customer Management 标签显示逻辑
  - 移除 DynamoDB scan 的 Limit=1 限制
  - 正确按 startTime 逆序排序
  - 显示真正最近一通电话的标签
- 🐛 修复标签显示格式
  - 同时显示标签名和值（`标签名: 值`）
  - 支持多个标签完整展示
- 🐛 修复提示词变量替换
  - 只保留 `{{customer_name}}` 和 `{{notes}}`
  - 移除未使用的 phone_number 和 debt_amount

#### 性能优化
- ⚡ DynamoDB 查询优化
- ⚡ 前端组件懒加载
- ⚡ API 响应缓存
- ⚡ CloudFront CDN 加速

### 📚 文档

- ✅ 完整的 README.md
- ✅ 中文快速开始指南（README.zh-CN.md）
- ✅ 系统架构 SVG 图
- ✅ API 文档
- ✅ 部署文档
- ✅ 故障排查指南
- ✅ 安全最佳实践

### 🔄 已知限制

- 密码使用 SHA256 单次哈希（建议未来升级到 bcrypt）
- 无速率限制（建议添加 API Gateway throttling）
- 无账户锁定机制
- Token 无刷新机制（固定 7 天）
- 无 2FA 支持

### 📝 升级说明

首次发布，无需升级。
