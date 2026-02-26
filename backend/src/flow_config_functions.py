"""
Flow configuration management functions
"""
import json
import os
import uuid
from datetime import datetime
from decimal import Decimal
import boto3

DYNAMODB_REGION = os.environ.get('DYNAMODB_REGION', 'us-east-1')

dynamodb = boto3.resource('dynamodb', region_name=DYNAMODB_REGION)
flows_table = dynamodb.Table(os.environ.get('FLOWS_TABLE', 'outbound-flow-configs'))


def handle_create_flow(event, cors_headers):
    """
    Create a new flow configuration
    """
    try:
        body = json.loads(event.get('body', '{}'))

        required_fields = ['flow_name', 'instance_id', 'contact_flow_id', 'queue_id']
        for field in required_fields:
            if not body.get(field):
                return {
                    'statusCode': 400,
                    'headers': cors_headers,
                    'body': json.dumps({'error': f'Missing required field: {field}'})
                }

        flow_id = str(uuid.uuid4())

        flow_item = {
            'flow_id': flow_id,
            'flow_name': body['flow_name'],
            'instance_id': body['instance_id'],
            'contact_flow_id': body['contact_flow_id'],
            'queue_id': body['queue_id'],
            'description': body.get('description', ''),
            'is_active': body.get('is_active', True),
            'created_at': datetime.utcnow().isoformat(),
            'updated_at': datetime.utcnow().isoformat()
        }

        # Add project_id if provided
        if body.get('project_id'):
            flow_item['project_id'] = body['project_id']

        flows_table.put_item(Item=flow_item)

        return {
            'statusCode': 200,
            'headers': cors_headers,
            'body': json.dumps(flow_item)
        }

    except Exception as e:
        print(f"Error creating flow: {str(e)}")
        return {
            'statusCode': 500,
            'headers': cors_headers,
            'body': json.dumps({'error': str(e)})
        }


def handle_list_flows(event, cors_headers):
    """
    List all flow configurations
    """
    try:
        query_params = event.get('queryStringParameters') or {}
        is_active = query_params.get('is_active')
        project_id = query_params.get('project_id')

        scan_kwargs = {}
        filter_expressions = []
        expr_values = {}

        if is_active:
            filter_expressions.append('is_active = :active')
            expr_values[':active'] = is_active == 'true'

        if project_id:
            filter_expressions.append('project_id = :project_id')
            expr_values[':project_id'] = project_id

        if filter_expressions:
            scan_kwargs['FilterExpression'] = ' AND '.join(filter_expressions)
            scan_kwargs['ExpressionAttributeValues'] = expr_values

        response = flows_table.scan(**scan_kwargs)

        flows = []
        for item in response['Items']:
            flows.append({
                'flow_id': item['flow_id'],
                'project_id': item.get('project_id', ''),
                'flow_name': item['flow_name'],
                'instance_id': item['instance_id'],
                'contact_flow_id': item['contact_flow_id'],
                'queue_id': item['queue_id'],
                'description': item.get('description', ''),
                'is_active': item.get('is_active', True),
                'created_at': item.get('created_at'),
                'updated_at': item.get('updated_at')
            })

        # Sort by created_at descending
        flows.sort(key=lambda x: x.get('created_at', ''), reverse=True)

        return {
            'statusCode': 200,
            'headers': cors_headers,
            'body': json.dumps({
                'flows': flows,
                'count': len(flows)
            })
        }

    except Exception as e:
        print(f"Error listing flows: {str(e)}")
        return {
            'statusCode': 500,
            'headers': cors_headers,
            'body': json.dumps({'error': str(e)})
        }


def handle_get_flow(flow_id, cors_headers):
    """
    Get single flow configuration
    """
    try:
        response = flows_table.get_item(Key={'flow_id': flow_id})

        if 'Item' not in response:
            return {
                'statusCode': 404,
                'headers': cors_headers,
                'body': json.dumps({'error': 'Flow not found'})
            }

        item = response['Item']
        flow = {
            'flow_id': item['flow_id'],
            'project_id': item.get('project_id', ''),
            'flow_name': item['flow_name'],
            'instance_id': item['instance_id'],
            'contact_flow_id': item['contact_flow_id'],
            'queue_id': item['queue_id'],
            'description': item.get('description', ''),
            'is_active': item.get('is_active', True),
            'created_at': item.get('created_at'),
            'updated_at': item.get('updated_at')
        }

        return {
            'statusCode': 200,
            'headers': cors_headers,
            'body': json.dumps(flow)
        }

    except Exception as e:
        print(f"Error getting flow: {str(e)}")
        return {
            'statusCode': 500,
            'headers': cors_headers,
            'body': json.dumps({'error': str(e)})
        }


def handle_update_flow(flow_id, event, cors_headers):
    """
    Update flow configuration
    """
    try:
        body = json.loads(event.get('body', '{}'))

        update_expr = []
        expr_values = {}
        expr_names = {}

        if 'flow_name' in body:
            update_expr.append('flow_name = :name')
            expr_values[':name'] = body['flow_name']

        if 'instance_id' in body:
            update_expr.append('instance_id = :instance')
            expr_values[':instance'] = body['instance_id']

        if 'contact_flow_id' in body:
            update_expr.append('contact_flow_id = :flow')
            expr_values[':flow'] = body['contact_flow_id']

        if 'queue_id' in body:
            update_expr.append('queue_id = :queue')
            expr_values[':queue'] = body['queue_id']

        if 'description' in body:
            update_expr.append('description = :desc')
            expr_values[':desc'] = body['description']

        if 'is_active' in body:
            update_expr.append('is_active = :active')
            expr_values[':active'] = body['is_active']

        if 'project_id' in body:
            update_expr.append('project_id = :project')
            expr_values[':project'] = body['project_id']

        update_expr.append('updated_at = :updated')
        expr_values[':updated'] = datetime.utcnow().isoformat()

        if len(update_expr) == 1:  # Only updated_at
            return {
                'statusCode': 400,
                'headers': cors_headers,
                'body': json.dumps({'error': 'No fields to update'})
            }

        update_kwargs = {
            'Key': {'flow_id': flow_id},
            'UpdateExpression': 'SET ' + ', '.join(update_expr),
            'ExpressionAttributeValues': expr_values,
            'ReturnValues': 'ALL_NEW'
        }

        if expr_names:
            update_kwargs['ExpressionAttributeNames'] = expr_names

        response = flows_table.update_item(**update_kwargs)

        item = response['Attributes']
        flow = {
            'flow_id': item['flow_id'],
            'project_id': item.get('project_id', ''),
            'flow_name': item['flow_name'],
            'instance_id': item['instance_id'],
            'contact_flow_id': item['contact_flow_id'],
            'queue_id': item['queue_id'],
            'description': item.get('description', ''),
            'is_active': item.get('is_active', True),
            'updated_at': item.get('updated_at')
        }

        return {
            'statusCode': 200,
            'headers': cors_headers,
            'body': json.dumps(flow)
        }

    except Exception as e:
        print(f"Error updating flow: {str(e)}")
        return {
            'statusCode': 500,
            'headers': cors_headers,
            'body': json.dumps({'error': str(e)})
        }


def handle_delete_flow(flow_id, cors_headers):
    """
    Delete flow configuration
    """
    try:
        flows_table.delete_item(Key={'flow_id': flow_id})

        return {
            'statusCode': 200,
            'headers': cors_headers,
            'body': json.dumps({'message': 'Flow deleted'})
        }

    except Exception as e:
        print(f"Error deleting flow: {str(e)}")
        return {
            'statusCode': 500,
            'headers': cors_headers,
            'body': json.dumps({'error': str(e)})
        }


def get_flow_config(flow_id):
    """
    Helper function to get flow configuration for making calls
    """
    try:
        response = flows_table.get_item(Key={'flow_id': flow_id})

        if 'Item' not in response:
            raise ValueError(f"Flow not found: {flow_id}")

        item = response['Item']

        if not item.get('is_active', True):
            raise ValueError(f"Flow is inactive: {flow_id}")

        return {
            'instance_id': item['instance_id'],
            'contact_flow_id': item['contact_flow_id'],
            'queue_id': item['queue_id']
        }

    except Exception as e:
        print(f"Error getting flow config: {str(e)}")
        raise e
