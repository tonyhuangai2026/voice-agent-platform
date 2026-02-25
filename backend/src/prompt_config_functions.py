"""
Prompt configuration management functions
"""
import json
import os
import uuid
from datetime import datetime
import boto3

dynamodb = boto3.resource('dynamodb', region_name='us-west-2')
prompts_table = dynamodb.Table(os.environ.get('PROMPTS_TABLE', 'outbound-prompts'))


def handle_create_prompt(event, cors_headers):
    """
    Create a new prompt configuration
    """
    try:
        body = json.loads(event.get('body', '{}'))

        required_fields = ['prompt_name', 'prompt_content']
        for field in required_fields:
            if not body.get(field):
                return {
                    'statusCode': 400,
                    'headers': cors_headers,
                    'body': json.dumps({'error': f'Missing required field: {field}'})
                }

        prompt_id = str(uuid.uuid4())

        prompt_item = {
            'prompt_id': prompt_id,
            'prompt_name': body['prompt_name'],
            'prompt_content': body['prompt_content'],
            'description': body.get('description', ''),
            'is_active': body.get('is_active', True),
            'created_at': datetime.utcnow().isoformat(),
            'updated_at': datetime.utcnow().isoformat()
        }

        prompts_table.put_item(Item=prompt_item)

        return {
            'statusCode': 200,
            'headers': cors_headers,
            'body': json.dumps(prompt_item)
        }

    except Exception as e:
        print(f"Error creating prompt: {str(e)}")
        return {
            'statusCode': 500,
            'headers': cors_headers,
            'body': json.dumps({'error': str(e)})
        }


def handle_list_prompts(event, cors_headers):
    """
    List all prompt configurations
    """
    try:
        query_params = event.get('queryStringParameters') or {}
        is_active = query_params.get('is_active')

        scan_kwargs = {}
        if is_active:
            scan_kwargs['FilterExpression'] = 'is_active = :active'
            scan_kwargs['ExpressionAttributeValues'] = {':active': is_active == 'true'}

        response = prompts_table.scan(**scan_kwargs)

        prompts = []
        for item in response['Items']:
            prompts.append({
                'prompt_id': item['prompt_id'],
                'prompt_name': item['prompt_name'],
                'prompt_content': item['prompt_content'],
                'description': item.get('description', ''),
                'is_active': item.get('is_active', True),
                'created_at': item.get('created_at'),
                'updated_at': item.get('updated_at')
            })

        # Sort by created_at descending
        prompts.sort(key=lambda x: x.get('created_at', ''), reverse=True)

        return {
            'statusCode': 200,
            'headers': cors_headers,
            'body': json.dumps({
                'prompts': prompts,
                'count': len(prompts)
            })
        }

    except Exception as e:
        print(f"Error listing prompts: {str(e)}")
        return {
            'statusCode': 500,
            'headers': cors_headers,
            'body': json.dumps({'error': str(e)})
        }


def handle_get_prompt(prompt_id, cors_headers):
    """
    Get single prompt details
    """
    try:
        response = prompts_table.get_item(Key={'prompt_id': prompt_id})

        if 'Item' not in response:
            return {
                'statusCode': 404,
                'headers': cors_headers,
                'body': json.dumps({'error': 'Prompt not found'})
            }

        item = response['Item']
        prompt = {
            'prompt_id': item['prompt_id'],
            'prompt_name': item['prompt_name'],
            'prompt_content': item['prompt_content'],
            'description': item.get('description', ''),
            'is_active': item.get('is_active', True),
            'created_at': item.get('created_at'),
            'updated_at': item.get('updated_at')
        }

        return {
            'statusCode': 200,
            'headers': cors_headers,
            'body': json.dumps(prompt)
        }

    except Exception as e:
        print(f"Error getting prompt: {str(e)}")
        return {
            'statusCode': 500,
            'headers': cors_headers,
            'body': json.dumps({'error': str(e)})
        }


def handle_update_prompt(prompt_id, event, cors_headers):
    """
    Update prompt configuration
    """
    try:
        body = json.loads(event.get('body', '{}'))

        update_expr = []
        expr_values = {}

        if 'prompt_name' in body:
            update_expr.append('prompt_name = :name')
            expr_values[':name'] = body['prompt_name']

        if 'prompt_content' in body:
            update_expr.append('prompt_content = :content')
            expr_values[':content'] = body['prompt_content']

        if 'description' in body:
            update_expr.append('description = :desc')
            expr_values[':desc'] = body['description']

        if 'is_active' in body:
            update_expr.append('is_active = :active')
            expr_values[':active'] = body['is_active']

        update_expr.append('updated_at = :updated')
        expr_values[':updated'] = datetime.utcnow().isoformat()

        if not update_expr:
            return {
                'statusCode': 400,
                'headers': cors_headers,
                'body': json.dumps({'error': 'No fields to update'})
            }

        response = prompts_table.update_item(
            Key={'prompt_id': prompt_id},
            UpdateExpression='SET ' + ', '.join(update_expr),
            ExpressionAttributeValues=expr_values,
            ReturnValues='ALL_NEW'
        )

        item = response['Attributes']
        prompt = {
            'prompt_id': item['prompt_id'],
            'prompt_name': item['prompt_name'],
            'prompt_content': item['prompt_content'],
            'description': item.get('description', ''),
            'is_active': item.get('is_active', True),
            'updated_at': item.get('updated_at')
        }

        return {
            'statusCode': 200,
            'headers': cors_headers,
            'body': json.dumps(prompt)
        }

    except Exception as e:
        print(f"Error updating prompt: {str(e)}")
        return {
            'statusCode': 500,
            'headers': cors_headers,
            'body': json.dumps({'error': str(e)})
        }


def handle_delete_prompt(prompt_id, cors_headers):
    """
    Delete prompt configuration
    """
    try:
        prompts_table.delete_item(Key={'prompt_id': prompt_id})

        return {
            'statusCode': 200,
            'headers': cors_headers,
            'body': json.dumps({'message': 'Prompt deleted successfully'})
        }

    except Exception as e:
        print(f"Error deleting prompt: {str(e)}")
        return {
            'statusCode': 500,
            'headers': cors_headers,
            'body': json.dumps({'error': str(e)})
        }


def get_prompt_config(prompt_id):
    """
    Helper function to get prompt config (used by other functions)
    """
    response = prompts_table.get_item(Key={'prompt_id': prompt_id})

    if 'Item' not in response:
        raise Exception(f'Prompt {prompt_id} not found')

    return response['Item']
