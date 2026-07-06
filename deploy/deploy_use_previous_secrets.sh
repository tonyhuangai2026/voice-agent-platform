#!/usr/bin/env bash
# Same packaging + upload as deploy.sh, but reuses the three NoEcho
# CloudFormation parameters (MinimaxApiKey / SitePassword / AdminPassword)
# from the existing stack via UsePreviousValue=true. Used when the stack
# already exists and the operator does not want to re-type the secrets.

set -euo pipefail

STACK_NAME=${STACK_NAME:-genaiic-voicebot}
REGION=${REGION:-us-east-1}
INSTANCE_TYPE=${INSTANCE_TYPE:-t3.medium}

cd "$(dirname "$0")"
PROJECT_ROOT="$(cd .. && pwd)"

echo "-- Stack: $STACK_NAME  Region: $REGION  InstanceType: $INSTANCE_TYPE"

if ! aws cloudformation describe-stacks --stack-name "$STACK_NAME" --region "$REGION" >/dev/null 2>&1; then
  echo "ERROR: stack $STACK_NAME does not exist in $REGION. This helper only updates an existing stack." >&2
  echo "       Use deploy.sh for the initial create." >&2
  exit 1
fi

ACCOUNT=$(aws sts get-caller-identity --query Account --output text --region "$REGION")
BUCKET="${STACK_NAME}-deploy-${ACCOUNT}-${REGION}"

if ! aws s3api head-bucket --bucket "$BUCKET" --region "$REGION" 2>/dev/null; then
  echo "ERROR: deploy bucket $BUCKET missing." >&2
  exit 1
fi

if [ -f "$PROJECT_ROOT/static/admin/package.json" ]; then
  echo "-- Building admin SPA"
  ( cd "$PROJECT_ROOT/static/admin" && [ -d node_modules ] || npm install --no-fund --no-audit; npm run build )
fi

TS=$(date +%Y%m%d-%H%M%S)
TARBALL=/tmp/voicebot-${TS}.tar.gz
echo "-- Packaging code -> $TARBALL"
tar -czf "$TARBALL" \
  --exclude='.venv' \
  --exclude='__pycache__' \
  --exclude='pipecat' \
  --exclude='.env' \
  --exclude='.git' \
  --exclude='.claude' \
  --exclude='*.wav' \
  --exclude='deploy' \
  --exclude='memory' \
  --exclude='voice-server/node_modules' \
  --exclude='voice-server/dist' \
  --exclude='static/admin/node_modules' \
  --exclude='static/admin/dist/.vite' \
  --exclude='config/runtime.json' \
  --exclude='tests/__pycache__' \
  -C "$PROJECT_ROOT" .

CODE_KEY="voicebot-${TS}.tar.gz"
echo "-- Uploading to s3://$BUCKET/$CODE_KEY"
aws s3 cp "$TARBALL" "s3://$BUCKET/$CODE_KEY" --region "$REGION"
rm -f "$TARBALL"

# Chime params. Two constraints to satisfy at once:
#   1. CFN REJECTS UsePreviousValue for a parameter that did NOT exist in the
#      prior stack — so on the FIRST update of this new template (current prod
#      has no Chime params) we must pass the template DEFAULT, not previous.
#   2. Once Chime IS configured, a plain code redeploy must PRESERVE it — so if
#      the param already exists on the stack we use UsePreviousValue.
# Resolution: env override ($2) always wins; else UsePreviousValue if the key is
# already on the stack; else the template default ($3). EXISTING_PARAMS is the
# stack's current parameter-key set (queried once below).
EXISTING_PARAMS=$(aws cloudformation describe-stacks --stack-name "$STACK_NAME" \
  --region "$REGION" --query 'Stacks[0].Parameters[*].ParameterKey' --output text 2>/dev/null || true)

chime_param() {  # $1=ParameterKey  $2=env value  $3=template default
  if [ -n "$2" ]; then
    echo "ParameterKey=$1,ParameterValue=$2"
  elif printf '%s\n' $EXISTING_PARAMS | grep -qx "$1"; then
    echo "ParameterKey=$1,UsePreviousValue=true"
  else
    echo "ParameterKey=$1,ParameterValue=$3"
  fi
}

echo "-- Updating stack (UsePreviousValue=true for NoEcho secrets + Chime params)"
aws cloudformation update-stack \
  --stack-name "$STACK_NAME" \
  --region "$REGION" \
  --template-body "file://cloudformation.yaml" \
  --capabilities CAPABILITY_IAM \
  --parameters \
    "ParameterKey=CodeBucket,ParameterValue=$BUCKET" \
    "ParameterKey=CodeKey,ParameterValue=$CODE_KEY" \
    "ParameterKey=MinimaxApiKey,UsePreviousValue=true" \
    "ParameterKey=SitePassword,UsePreviousValue=true" \
    "ParameterKey=AdminPassword,UsePreviousValue=true" \
    "ParameterKey=InstanceType,ParameterValue=$INSTANCE_TYPE" \
    "ParameterKey=LatestUbuntuAmi,UsePreviousValue=true" \
    "ParameterKey=UseElasticIp,UsePreviousValue=true" \
    "$(chime_param VoiceConnectorName "${VOICE_CONNECTOR_NAME:-}" '')" \
    "$(chime_param PhoneNumberE164 "${PHONE_NUMBER_E164:-}" '')" \
    "$(chime_param RetainVoiceConnectorOnDelete "${RETAIN_VC_ON_DELETE:-}" 'true')" \
    "$(chime_param ForceAssociatePhoneNumber "${FORCE_ASSOCIATE_NUMBER:-}" 'false')"

echo "-- Waiting for stack update to complete..."
aws cloudformation wait stack-update-complete --stack-name "$STACK_NAME" --region "$REGION"

echo "-- Stack outputs:"
aws cloudformation describe-stacks --stack-name "$STACK_NAME" --region "$REGION" \
  --query 'Stacks[0].Outputs[*].[OutputKey,OutputValue]' --output table
