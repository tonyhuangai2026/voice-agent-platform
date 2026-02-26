import json
import boto3
import os
from decimal import Decimal
from datetime import datetime

dynamodb = boto3.resource('dynamodb', region_name=os.environ.get('DYNAMODB_REGION', 'us-east-1'))
call_records_table = dynamodb.Table(os.environ.get('CALL_RECORDS_TABLE', 'outbound-call-records'))
label_configs_table = dynamodb.Table(os.environ.get('LABEL_CONFIGS_TABLE', 'label-configs'))

bedrock_client = boto3.client('bedrock-runtime', region_name='us-west-2')


class DecimalEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, Decimal):
            return int(o) if o == int(o) else float(o)
        return super().default(o)


def handle_auto_label_call(call_sid, cors_headers):
    """
    POST /api/call-records/{call_sid}/auto-label
    Automatically label a call using Claude based on transcript
    """
    try:
        # 1. Get call record
        call_response = call_records_table.get_item(Key={'callSid': call_sid})
        if 'Item' not in call_response:
            return {
                'statusCode': 404,
                'headers': cors_headers,
                'body': json.dumps({'error': 'Call record not found'})
            }

        call_record = call_response['Item']
        project_id = call_record.get('project_id')
        transcript = call_record.get('transcript', [])

        if not transcript:
            return {
                'statusCode': 400,
                'headers': cors_headers,
                'body': json.dumps({'error': 'No transcript available for this call'})
            }

        # 2. Get active label configs for this project
        if project_id:
            label_response = label_configs_table.query(
                IndexName='project-index',
                KeyConditionExpression='project_id = :pid',
                FilterExpression='is_active = :active',
                ExpressionAttributeValues={
                    ':pid': project_id,
                    ':active': True
                }
            )
            label_configs = label_response.get('Items', [])
        else:
            return {
                'statusCode': 400,
                'headers': cors_headers,
                'body': json.dumps({'error': 'Call record has no project_id'})
            }

        if not label_configs:
            return {
                'statusCode': 400,
                'headers': cors_headers,
                'body': json.dumps({'error': 'No active label configurations found for this project'})
            }

        # 3. Format transcript for analysis
        conversation_text = format_transcript(transcript)

        # 4. Generate prompt dynamically based on label configs
        prompt = generate_label_prompt(conversation_text, label_configs)

        # 5. Call Claude for analysis
        labels = call_claude_for_labeling(prompt, label_configs)

        # 6. Save labels to call record
        call_records_table.update_item(
            Key={'callSid': call_sid},
            UpdateExpression='SET labels = :labels, updated_at = :updated_at, auto_labeled_at = :auto_labeled_at',
            ExpressionAttributeValues={
                ':labels': labels,
                ':updated_at': datetime.utcnow().isoformat(),
                ':auto_labeled_at': datetime.utcnow().isoformat()
            }
        )

        return {
            'statusCode': 200,
            'headers': cors_headers,
            'body': json.dumps({
                'message': 'Call automatically labeled',
                'callSid': call_sid,
                'labels': labels
            }, cls=DecimalEncoder)
        }

    except Exception as e:
        print(f"Error auto-labeling call: {str(e)}")
        import traceback
        traceback.print_exc()
        return {
            'statusCode': 500,
            'headers': cors_headers,
            'body': json.dumps({'error': str(e)})
        }


def format_transcript(transcript):
    """
    Format transcript array into readable conversation text
    """
    lines = []
    for entry in transcript:
        role = entry.get('role', 'unknown')
        text = entry.get('text', '')
        role_label = 'Customer' if role == 'user' else 'Assistant'
        lines.append(f"{role_label}: {text}")
    return '\n'.join(lines)


def generate_label_prompt(conversation_text, label_configs):
    """
    Dynamically generate prompt based on label configurations
    """
    prompt_parts = [
        "You are a professional call analysis assistant. Analyze the following conversation and assign labels based on the provided label configurations.\n",
        f"Conversation:\n{conversation_text}\n",
        "\nPlease analyze the conversation and assign values for the following labels:\n"
    ]

    # Add each label config to prompt
    for idx, config in enumerate(label_configs, 1):
        label_name = config['label_name']
        label_type = config['label_type']
        options = config['options']

        if label_type == 'single':
            prompt_parts.append(f"\n{idx}. {label_name} (select ONE):")
            for option in options:
                prompt_parts.append(f"   - {option}")
        else:  # multiple
            prompt_parts.append(f"\n{idx}. {label_name} (select ALL that apply):")
            for option in options:
                prompt_parts.append(f"   - {option}")

    prompt_parts.append("\n\nReturn your analysis in JSON format with the following structure:")
    prompt_parts.append('\n{')
    for config in label_configs:
        label_id = config['label_id']
        label_type = config['label_type']
        if label_type == 'single':
            prompt_parts.append(f'  "{label_id}": "selected_option",')
        else:
            prompt_parts.append(f'  "{label_id}": ["option1", "option2"],')
    prompt_parts.append('}')
    prompt_parts.append("\n\nOnly return valid JSON, no other text.")

    return ''.join(prompt_parts)


def call_claude_for_labeling(prompt, label_configs):
    """
    Call Claude Haiku for label prediction
    """
    try:
        response = bedrock_client.invoke_model(
            modelId='global.anthropic.claude-sonnet-4-6',
            contentType='application/json',
            accept='application/json',
            body=json.dumps({
                'anthropic_version': 'bedrock-2023-05-31',
                'max_tokens': 2000,
                'temperature': 0,
                'messages': [
                    {
                        'role': 'user',
                        'content': prompt
                    }
                ]
            })
        )

        response_body = json.loads(response['body'].read())
        assistant_message = response_body['content'][0]['text']

        print(f"Claude response: {assistant_message}")

        # Parse JSON from response
        # Try to extract JSON from response (may have markdown code blocks)
        import re
        json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', assistant_message, re.DOTALL)
        if json_match:
            json_str = json_match.group(1)
        else:
            # Try to find raw JSON
            json_match = re.search(r'\{.*\}', assistant_message, re.DOTALL)
            if json_match:
                json_str = json_match.group(0)
            else:
                json_str = assistant_message

        labels = json.loads(json_str)

        # Validate labels against configs
        validated_labels = {}
        for config in label_configs:
            label_id = config['label_id']
            if label_id in labels:
                value = labels[label_id]
                # Validate the value is in options
                if config['label_type'] == 'single':
                    if value in config['options']:
                        validated_labels[label_id] = value
                else:  # multiple
                    if isinstance(value, list):
                        validated_values = [v for v in value if v in config['options']]
                        if validated_values:
                            validated_labels[label_id] = validated_values

        return validated_labels

    except Exception as e:
        print(f"Error calling Claude for labeling: {str(e)}")
        import traceback
        traceback.print_exc()
        raise
