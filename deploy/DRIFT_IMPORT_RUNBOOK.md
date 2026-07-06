# CFN 模板漂移收敛 Runbook — 导入既有资源 + Retain 加固

把一个**已经漂移**的 voicebot CloudFormation 栈收敛回「模板 == 现实」，使 `deploy.sh`
今后能干净跑、不再需要 SSM 手动打补丁，且**不丢任何现有数据 / 不冲掉手工加的权限**。

本文档基于 2026-06-15 在 `genaiic-voicebot`（us-east-1）实际执行并验证的过程，参数化为
任意栈 / 区域，可照搬到 `staging` / `hksummit` / `setuptest` 及客户 eu-central-1 环境。

> **核心原理**：当物理资源（如 DynamoDB 表）存在但不在栈里时，CFN `deploy` 会试图
> CREATE 它 → `AlreadyExists` → 整栈回滚。修法是 **resource import**（采纳而非重建），
> 再用全量模板把其余漂移（IAM / 参数 / SG 参数化 / UserData）一次 deploy 对齐。

---

## 0. 参数（按环境替换）

```bash
STACK=genaiic-voicebot          # 目标栈名
REGION=us-east-1                # 部署区域
INSTANCE_ID=<EC2_INSTANCE_ID> # 该栈的 EC2 实例（describe-stack-resources 查）
```

**环境差异值——不要写死，执行时查证：**

```bash
# CloudFront origin-facing prefix list id（随区域不同：us-east-1≈pl-3b927c52，eu-central-1 另算）
aws ec2 describe-managed-prefix-lists --region "$REGION" \
  --filters Name=prefix-list-name,Values=com.amazonaws.global.cloudfront.origin-facing \
  --query 'PrefixLists[0].PrefixListId' --output text

# Bedrock 推理区域：通常 us-east-1（us.* inference profile），即使 EC2 在别的区
# → 部署时作为 BedrockRegion 参数传入
```

---

## 1. 诊断：确认漂移与「哪些资源在栈外」

```bash
# 栈当前管理的资源
aws cloudformation describe-stack-resources --stack-name "$STACK" --region "$REGION" \
  --query 'StackResources[].LogicalResourceId' --output table

# 物理表是否存在 + 有多少数据（不能丢的）
aws dynamodb describe-table --table-name "${STACK}-users" --region "$REGION" \
  --query 'Table.{Status:TableStatus,Items:ItemCount,Keys:KeySchema}' --output json
```

若 `UsersTable` **不在** describe-stack-resources、但物理表 `${STACK}-users` **存在** → 典型漂移，继续。

---

## 2. 准备两份模板

IMPORT changeset 有硬约束：**只能包含被导入的资源，模板与栈现状除此之外零差异**。
因此 import 那一步不能直接用仓库全量模板（它通常比线上新好几代）。

```bash
# 模板 A（import 专用）= 线上实际模板 + 仅追加待导入资源(带 DeletionPolicy: Retain)
aws cloudformation get-template --stack-name "$STACK" --region "$REGION" \
  --template-stage Original --output json \
  | python3 -c "import sys,json;sys.stdout.write(json.load(sys.stdin)['TemplateBody'])" \
  > /tmp/cfn-deployed.yaml

# 手动/脚本在 /tmp/cfn-deployed.yaml 的 HistoryTable 块之后插入 UsersTable 定义，
# 资源级加上：
#     DeletionPolicy: Retain
#     UpdateReplacePolicy: Retain
# （UsersTable 的属性必须与 describe-table 输出逐项一致：KeySchema/BillingMode/AttributeDefinitions）
# 存为 /tmp/cfn-import-A.yaml

# 校验：A 与线上模板应仅差「新增的被导入资源块」
diff /tmp/cfn-deployed.yaml /tmp/cfn-import-A.yaml      # 应只显示新增块
aws cloudformation validate-template --region "$REGION" --template-body file:///tmp/cfn-import-A.yaml

# 模板 B（最终）= 仓库 deploy/cloudformation.yaml（已含 UsersTable + 两表 Retain +
# IAM/参数/SG 参数化等全部最新形态）。这是 import 之后用来全量对齐的模板。
aws cloudformation validate-template --region "$REGION" --template-body file://deploy/cloudformation.yaml
```

> 若线上模板已经领先（例如已含 UsersTable），跳过 import，直接走第 5 步。

---

## 3. 执行前安全措施（生产必做）

```bash
# 3a. 确认无活跃通话（避免 restart/变更打断真实来电）
aws ssm send-command --region "$REGION" --instance-ids "$INSTANCE_ID" \
  --document-name AWS-RunShellScript \
  --parameters 'commands=["bash -lc \"systemctl is-active voicebot; tail -n 5 /var/log/voicebot.log\""]'

# 3b. 备份所有有状态表（IMPORT 不动数据，但兜底）
aws dynamodb create-backup --region "$REGION" \
  --table-name "${STACK}-users" --backup-name "${STACK}-users-preimport"
aws dynamodb create-backup --region "$REGION" \
  --table-name "${STACK}-call-history" --backup-name "${STACK}-callhistory-preimport"
# 等两个 backup 状态 AVAILABLE：aws dynamodb list-backups --region "$REGION" --table-name ...

# 3c. 记录基线（事后比对实例是否被替换）
aws cloudformation describe-stacks --stack-name "$STACK" --region "$REGION" \
  --query 'Stacks[0].StackStatus' --output text
```

---

## 4. 导入（用模板 A）

```bash
# 4a. 创建 IMPORT changeset（参数全部 UsePreviousValue；ResourcesToImport 映射逻辑id→物理表名）
aws cloudformation create-change-set --region "$REGION" \
  --stack-name "$STACK" --change-set-name import-userstable \
  --change-set-type IMPORT --capabilities CAPABILITY_IAM \
  --resources-to-import '[{"ResourceType":"AWS::DynamoDB::Table","LogicalResourceId":"UsersTable","ResourceIdentifier":{"TableName":"'"${STACK}"'-users"}}]' \
  --template-body file:///tmp/cfn-import-A.yaml \
  --parameters <对线上栈每个参数逐个 ParameterKey=...,UsePreviousValue=true>

# 4b. 【人工审阅，必做】唯一变更应是 Action=Import / UsersTable，无任何 Remove/Replace
aws cloudformation describe-change-set --region "$REGION" \
  --stack-name "$STACK" --change-set-name import-userstable \
  --query 'Changes[].{Action:ResourceChange.Action,Logical:ResourceChange.LogicalResourceId,Replace:ResourceChange.Replacement}'

# 4c. 确认无误后执行 → 等 IMPORT_COMPLETE
aws cloudformation execute-change-set --region "$REGION" \
  --stack-name "$STACK" --change-set-name import-userstable

# 4d. 验证：UsersTable 现为栈内资源 + 数据未变
aws cloudformation describe-stack-resources --stack-name "$STACK" --region "$REGION" \
  --query "StackResources[?LogicalResourceId=='UsersTable']"
aws dynamodb describe-table --table-name "${STACK}-users" --region "$REGION" --query 'Table.ItemCount'
```

---

## 5. 全量对齐（用模板 B = 仓库模板），changeset 先审后执行

```bash
# 5a. 建 UPDATE changeset（dry-run）
aws cloudformation create-change-set --region "$REGION" \
  --stack-name "$STACK" --change-set-name reconcile-full \
  --change-set-type UPDATE --capabilities CAPABILITY_IAM \
  --template-body file://deploy/cloudformation.yaml \
  --parameters \
    <线上已有参数 UsePreviousValue=true> \
    ParameterKey=BedrockRegion,ParameterValue=<查证值> \
    ParameterKey=CloudFrontPrefixListId,ParameterValue=<查证值>

# 5b. 【人工审阅，必做】逐条看 Changes，重点：
aws cloudformation describe-change-set --region "$REGION" \
  --stack-name "$STACK" --change-set-name reconcile-full \
  --query 'Changes[].{Action:ResourceChange.Action,Logical:ResourceChange.LogicalResourceId,Replace:ResourceChange.Replacement,Scope:ResourceChange.Scope}'
# 对每个非平凡变更深挖 Details[].Target.{Name,RequiresRecreation}：
aws cloudformation describe-change-set --region "$REGION" --stack-name "$STACK" \
  --change-set-name reconcile-full \
  --query 'Changes[?ResourceChange.LogicalResourceId==`Instance`].ResourceChange.Details'

# ⚠️ 红线检查（任一不满足就停下，别执行）：
#   - SecurityGroup：最好完全不在变更列表；若在，必须确认 Chime CIDR 入站规则
#     (99.77.254.0/24 + 3.80.16.0/23, UDP 5060 + 10000-10999) 前后不变。
#   - InstanceRole：RequiresRecreation=Never，且模板含 bedrock-agentcore:InvokeAgentRuntime
#     （否则会冲掉手工加的 AgentCore/MCP 权限）。
#   - Instance：若 UserData 变更，RequiresRecreation 应为 Conditionally/Never（UserData 更新
#     不替换运行中实例）；任何 Replacement=True 都意味着重建 EC2 → 停机 + EIP 重关联，慎重。
#   - 任何 DynamoDB 表出现 Replacement=True → 立即停止（会丢数据）。

# 5c. 全部红线通过后执行 → 等 UPDATE_COMPLETE
aws cloudformation execute-change-set --region "$REGION" \
  --stack-name "$STACK" --change-set-name reconcile-full
```

---

## 6. 执行后验证（全绿才算完成）

```bash
# 实例未被替换（与 3c 基线对比）
aws cloudformation describe-stack-resources --stack-name "$STACK" --region "$REGION" \
  --query "StackResources[?LogicalResourceId=='Instance'].PhysicalResourceId" --output text   # 应 == $INSTANCE_ID
# 数据未丢
aws dynamodb describe-table --table-name "${STACK}-users" --region "$REGION" --query 'Table.ItemCount'
# 两表都带 Retain（防未来误删）
aws cloudformation get-template --stack-name "$STACK" --region "$REGION" --template-stage Original --output text | grep -c "DeletionPolicy: Retain"
# 漂移清零：线上模板 == 仓库模板（资源/参数层）
# 服务健康
aws ssm send-command --region "$REGION" --instance-ids "$INSTANCE_ID" --document-name AWS-RunShellScript \
  --parameters 'commands=["bash -lc \"systemctl is-active voicebot; curl -s -o /dev/null -w %{http_code} http://127.0.0.1:7860/api/admin/health\""]'
```

> **代码刷新独立于 CFN**：UserData 只在实例**创建**时运行，普通 update / import **不会**刷新
> `/opt/voicebot` 的代码。若本次同时要上线代码改动，仍按 CLAUDE.md 的 SSM tar+restart 后置步骤
> 单独做（restart 前确认无活跃通话），并 `grep` 一个已改 token 确认上线。

---

## 7. 照搬到其它栈 / 客户环境

| 环境 | STACK | REGION | 备注 |
|---|---|---|---|
| 主 prod | `genaiic-voicebot` | us-east-1 | 已于 2026-06-15 执行完成（本 runbook 的来源）|
| staging | `genaiic-voicebot-staging` | us-east-1 | 无 EIP；若同样漂移照本流程 |
| HK Summit | `genaiic-voicebot-hksummit` | us-east-1 | 无 PSTN，SG 红线不适用 |
| setuptest | `genaiic-voicebot-setuptest` | us-east-1 | 测试栈，可先在这里演练全流程 |
| **客户** | （客户栈名） | **eu-central-1** | prefix-list / BedrockRegion 用第 0 步命令查证；见下 |

**客户 eu-central-1（账号 154305462659）责任归属：**
本仓库只提供**模板（`deploy/cloudformation.yaml`）+ 本 runbook**。客户环境的实际执行
**必须由持有客户 AWS 凭证的人**在能访问该账号的环境中进行——本仓库的开发机连的是我方账号
（<AWS_ACCOUNT_ID>），**没有也不应有**客户凭证。客户侧执行时：
- 第 0 步用 `eu-central-1` 查 prefix-list id（与 us-east-1 的 `pl-3b927c52` 不同）；
- `BedrockRegion` 一般仍填 `us-east-1`（Anthropic/Nova 模型的 inference profile 区）；
- 其余步骤（备份→import→审阅→deploy→验证）完全照搬。
