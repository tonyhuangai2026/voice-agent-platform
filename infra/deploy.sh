#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# deploy.sh - Deploy Voice Agent Platform (full stack)
#
# Usage:
#   ./deploy.sh                        # Full deploy (stack + docker + ECS + Lambda + frontend)
#   ./deploy.sh --stack-only           # Only create/update CloudFormation stack
#   ./deploy.sh --deploy-only          # Only build, push image, and update ECS service
#   ./deploy.sh --lambda-only          # Only deploy Lambda function code
#   ./deploy.sh --frontend-only        # Only build and deploy frontend
# ============================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
OUTBOUND_ROOT="$(cd "${PROJECT_ROOT}/../didi-outbound" && pwd)"

# --- Load .env if present (won't override already-exported vars) ---
ENV_FILE="${SCRIPT_DIR}/../.env"
if [ -f "$ENV_FILE" ]; then
  set -a
  source "$ENV_FILE"
  set +a
fi

STACK_NAME="voice-agent-platform"
IMAGE_TAG="${IMAGE_TAG:-latest}"
AWS_REGION="${AWS_REGION:-us-east-1}"

# --- Parse arguments ---
STACK_ONLY=false
DEPLOY_ONLY=false
LAMBDA_ONLY=false
FRONTEND_ONLY=false
for arg in "$@"; do
  case "$arg" in
    --stack-only)    STACK_ONLY=true ;;
    --deploy-only)   DEPLOY_ONLY=true ;;
    --lambda-only)   LAMBDA_ONLY=true ;;
    --frontend-only) FRONTEND_ONLY=true ;;
    *) echo "Unknown argument: $arg"; exit 1 ;;
  esac
done

# --- Helpers ---
log() { echo "==> $*"; }

check_deps() {
  for cmd in aws docker jq; do
    if ! command -v "$cmd" &>/dev/null; then
      echo "Error: '$cmd' is required but not installed."
      exit 1
    fi
  done
}

get_stack_output() {
  local key="$1"
  aws cloudformation describe-stacks \
    --stack-name "${STACK_NAME}" \
    --region "${AWS_REGION}" \
    --query "Stacks[0].Outputs[?OutputKey=='${key}'].OutputValue" \
    --output text
}

# --- Step 1: Deploy CloudFormation ---
deploy_stack() {
  log "Deploying CloudFormation stack: ${STACK_NAME}"

  # Prompt for Twilio credentials if not set
  if [ -z "${TWILIO_ACCOUNT_SID:-}" ]; then
    read -rp "TWILIO_ACCOUNT_SID: " TWILIO_ACCOUNT_SID
  fi
  if [ -z "${TWILIO_API_SID:-}" ]; then
    read -rp "TWILIO_API_SID: " TWILIO_API_SID
  fi
  if [ -z "${TWILIO_API_SECRET:-}" ]; then
    read -rsp "TWILIO_API_SECRET: " TWILIO_API_SECRET
    echo
  fi
  if [ -z "${TWILIO_FROM_NUMBER:-}" ]; then
    read -rp "TWILIO_FROM_NUMBER: " TWILIO_FROM_NUMBER
  fi

  aws cloudformation deploy \
    --template-file "${SCRIPT_DIR}/cloudformation.yaml" \
    --stack-name "${STACK_NAME}" \
    --region "${AWS_REGION}" \
    --capabilities CAPABILITY_NAMED_IAM \
    --parameter-overrides \
      TwilioAccountSid="${TWILIO_ACCOUNT_SID}" \
      TwilioApiSid="${TWILIO_API_SID}" \
      TwilioApiSecret="${TWILIO_API_SECRET}" \
      TwilioFromNumber="${TWILIO_FROM_NUMBER}" \
      TwilioVerifiedCallerId="${TWILIO_VERIFIED_CALLER_ID:-}" \
      SipEndpoint="${SIP_ENDPOINT:-}" \
      AwsRegion="${AWS_REGION}" \
      ImageTag="${IMAGE_TAG}" \
      VoiceId="${VOICE_ID:-tiffany}" \
      Temperature="${TEMPERATURE:-0.7}" \
      TopP="${TOP_P:-0.9}" \
      MaxTokens="${MAX_TOKENS:-1024}" \
      CustomersTable="${CUSTOMERS_TABLE:-outbound-customers}" \
      PromptsTable="${PROMPTS_TABLE:-outbound-prompts}" \
      CallRecordsTable="${CALL_RECORDS_TABLE:-outbound-call-records}" \
      FlowsTable="${FLOWS_TABLE:-outbound-flow-configs}" \
      ConnectInstanceId="${CONNECT_INSTANCE_ID:?CONNECT_INSTANCE_ID required}" \
      ConnectRegion="${CONNECT_REGION:-us-west-2}" \
      JWTSecret="${JWT_SECRET:?JWT_SECRET environment variable is required}" \
      InviteCode="${INVITE_CODE:?INVITE_CODE environment variable is required}" \
    --no-fail-on-empty-changeset

  log "CloudFormation stack deployed successfully"
}

# --- Step 2: Build and push Docker image ---
build_and_push() {
  local account_id
  account_id=$(aws sts get-caller-identity --query Account --output text)
  local ecr_uri="${account_id}.dkr.ecr.${AWS_REGION}.amazonaws.com/voice-agent-server"

  log "Logging in to ECR"
  aws ecr get-login-password --region "${AWS_REGION}" | \
    docker login --username AWS --password-stdin "${account_id}.dkr.ecr.${AWS_REGION}.amazonaws.com"

  log "Building Docker image: ${ecr_uri}:${IMAGE_TAG}"
  docker build --platform linux/amd64 -t "${ecr_uri}:${IMAGE_TAG}" "${PROJECT_ROOT}/voice-server/"

  log "Pushing image to ECR"
  docker push "${ecr_uri}:${IMAGE_TAG}"

  log "Image pushed: ${ecr_uri}:${IMAGE_TAG}"
}

# --- Step 3: Force new ECS deployment ---
update_ecs_service() {
  log "Forcing new ECS deployment"
  aws ecs update-service \
    --cluster voice-agent-cluster \
    --service voice-agent-service \
    --desired-count 1 \
    --force-new-deployment \
    --region "${AWS_REGION}" \
    --query 'service.deployments[0].status' \
    --output text

  log "Waiting for service to stabilize..."
  aws ecs wait services-stable \
    --cluster voice-agent-cluster \
    --services voice-agent-service \
    --region "${AWS_REGION}"

  log "ECS service updated successfully"
}

# --- Step 4: Deploy Lambda function code ---
deploy_lambda() {
  local lambda_name
  lambda_name=$(get_stack_output "LambdaFunctionName")

  if [ -z "$lambda_name" ]; then
    echo "Error: Could not get LambdaFunctionName from stack outputs"
    exit 1
  fi

  log "Packaging Lambda function code"
  local zip_file="/tmp/lambda-deploy-$$.zip"
  rm -f "$zip_file"

  (cd "${OUTBOUND_ROOT}/backend/src" && zip "$zip_file" *.py)

  log "Deploying Lambda function: ${lambda_name}"
  aws lambda update-function-code \
    --function-name "$lambda_name" \
    --zip-file "fileb://${zip_file}" \
    --region "${AWS_REGION}" \
    --query 'FunctionName' \
    --output text

  rm -f "$zip_file"

  log "Waiting for Lambda update to complete..."
  aws lambda wait function-updated \
    --function-name "$lambda_name" \
    --region "${AWS_REGION}"

  log "Lambda function deployed successfully"
}

# --- Step 5: Build and deploy frontend ---
deploy_frontend() {
  local api_url bucket_name distribution_id voice_server_url

  api_url=$(get_stack_output "ApiGatewayUrl")
  bucket_name=$(get_stack_output "FrontendBucketName")
  distribution_id=$(get_stack_output "FrontendDistributionId")
  voice_server_url=$(get_stack_output "CloudFrontDomain")

  if [ -z "$api_url" ] || [ -z "$bucket_name" ] || [ -z "$distribution_id" ]; then
    echo "Error: Could not get frontend stack outputs (ApiGatewayUrl, FrontendBucketName, FrontendDistributionId)"
    exit 1
  fi

  # Prepend https:// if CloudFrontDomain is a bare domain
  if [ -n "$voice_server_url" ] && [[ ! "$voice_server_url" =~ ^https?:// ]]; then
    voice_server_url="https://${voice_server_url}"
  fi

  log "Building frontend with API URL: ${api_url}"
  if [ -n "$voice_server_url" ]; then
    log "Voice server URL: ${voice_server_url}"
  fi
  (cd "${OUTBOUND_ROOT}/frontend" && VITE_API_BASE="${api_url}" VITE_VOICE_SERVER_BASE="${voice_server_url:-}" npm run build)

  log "Syncing frontend to S3: ${bucket_name}"
  aws s3 sync "${OUTBOUND_ROOT}/frontend/dist" "s3://${bucket_name}" \
    --delete \
    --region "${AWS_REGION}"

  log "Invalidating CloudFront cache: ${distribution_id}"
  aws cloudfront create-invalidation \
    --distribution-id "$distribution_id" \
    --paths '/*' \
    --query 'Invalidation.Id' \
    --output text

  log "Frontend deployed successfully"
}

# --- Print outputs ---
print_outputs() {
  log "Stack outputs:"
  aws cloudformation describe-stacks \
    --stack-name "${STACK_NAME}" \
    --region "${AWS_REGION}" \
    --query 'Stacks[0].Outputs' \
    --output table
}

# ============================================================
# Main
# ============================================================
check_deps

if [ "$LAMBDA_ONLY" = true ]; then
  deploy_lambda
  print_outputs
elif [ "$FRONTEND_ONLY" = true ]; then
  deploy_frontend
  print_outputs
elif [ "$DEPLOY_ONLY" = true ]; then
  build_and_push
  update_ecs_service
  print_outputs
elif [ "$STACK_ONLY" = true ]; then
  deploy_stack
  print_outputs
else
  deploy_stack
  build_and_push
  update_ecs_service
  deploy_lambda
  deploy_frontend
  print_outputs
fi

log "Done!"
