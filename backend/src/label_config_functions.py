import json
import boto3
import os
import uuid
from datetime import datetime
from decimal import Decimal

dynamodb = boto3.resource('dynamodb', region_name=os.environ.get('DYNAMODB_REGION', 'us-east-1'))
label_configs_table = dynamodb.Table(os.environ.get('LABEL_CONFIGS_TABLE', 'label-configs'))


class DecimalEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, Decimal):
            return int(o) if o == int(o) else float(o)
        return super().default(o)


def handle_list_labels(event, cors_headers):
    """
    GET /api/labels?project_id=xxx&is_active=true
    List all label configurations
    """
    try:
        query_params = event.get('queryStringParameters') or {}
        project_id = query_params.get('project_id')
        is_active = query_params.get('is_active')

        if project_id:
            # Query by project_id using GSI
            query_kwargs = {
                'IndexName': 'project-index',
                'KeyConditionExpression': 'project_id = :pid',
                'ExpressionAttributeValues': {':pid': project_id}
            }

            if is_active is not None:
                is_active_bool = is_active.lower() == 'true'
                query_kwargs['FilterExpression'] = 'is_active = :active'
                query_kwargs['ExpressionAttributeValues'][':active'] = is_active_bool

            response = label_configs_table.query(**query_kwargs)
            items = response.get('Items', [])
        else:
            # Scan all
            scan_kwargs = {}
            if is_active is not None:
                is_active_bool = is_active.lower() == 'true'
                scan_kwargs['FilterExpression'] = 'is_active = :active'
                scan_kwargs['ExpressionAttributeValues'] = {':active': is_active_bool}

            response = label_configs_table.scan(**scan_kwargs)
            items = response.get('Items', [])

        # Sort by created_at descending
        items.sort(key=lambda x: x.get('created_at', ''), reverse=True)

        return {
            'statusCode': 200,
            'headers': cors_headers,
            'body': json.dumps({
                'labels': items,
                'count': len(items)
            }, cls=DecimalEncoder)
        }
    except Exception as e:
        print(f"Error listing labels: {str(e)}")
        return {
            'statusCode': 500,
            'headers': cors_headers,
            'body': json.dumps({'error': str(e)})
        }


def handle_get_label(label_id, cors_headers):
    """
    GET /api/labels/{label_id}
    Get a specific label configuration
    """
    try:
        response = label_configs_table.get_item(Key={'label_id': label_id})

        if 'Item' not in response:
            return {
                'statusCode': 404,
                'headers': cors_headers,
                'body': json.dumps({'error': 'Label not found'})
            }

        return {
            'statusCode': 200,
            'headers': cors_headers,
            'body': json.dumps(response['Item'], cls=DecimalEncoder)
        }
    except Exception as e:
        print(f"Error getting label: {str(e)}")
        return {
            'statusCode': 500,
            'headers': cors_headers,
            'body': json.dumps({'error': str(e)})
        }


def handle_create_label(event, cors_headers):
    """
    POST /api/labels
    Create a new label configuration
    """
    try:
        body = json.loads(event['body'])

        # Validate required fields
        required_fields = ['project_id', 'label_name', 'label_type', 'options']
        for field in required_fields:
            if field not in body:
                return {
                    'statusCode': 400,
                    'headers': cors_headers,
                    'body': json.dumps({'error': f'Missing required field: {field}'})
                }

        # Validate label_type
        if body['label_type'] not in ['single', 'multiple']:
            return {
                'statusCode': 400,
                'headers': cors_headers,
                'body': json.dumps({'error': 'label_type must be "single" or "multiple"'})
            }

        # Validate options is a list
        if not isinstance(body['options'], list) or len(body['options']) == 0:
            return {
                'statusCode': 400,
                'headers': cors_headers,
                'body': json.dumps({'error': 'options must be a non-empty list'})
            }

        label_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()

        label_config = {
            'label_id': label_id,
            'project_id': body['project_id'],
            'label_name': body['label_name'],
            'label_type': body['label_type'],
            'options': body['options'],
            'description': body.get('description', ''),
            'is_active': body.get('is_active', True),
            'created_at': now,
            'updated_at': now,
        }

        label_configs_table.put_item(Item=label_config)

        return {
            'statusCode': 201,
            'headers': cors_headers,
            'body': json.dumps({
                'message': 'Label created successfully',
                'label': label_config
            }, cls=DecimalEncoder)
        }
    except Exception as e:
        print(f"Error creating label: {str(e)}")
        return {
            'statusCode': 500,
            'headers': cors_headers,
            'body': json.dumps({'error': str(e)})
        }


def handle_update_label(label_id, event, cors_headers):
    """
    PUT /api/labels/{label_id}
    Update an existing label configuration
    """
    try:
        body = json.loads(event['body'])

        # Check if label exists
        response = label_configs_table.get_item(Key={'label_id': label_id})
        if 'Item' not in response:
            return {
                'statusCode': 404,
                'headers': cors_headers,
                'body': json.dumps({'error': 'Label not found'})
            }

        # Build update expression
        update_expr = "SET updated_at = :updated_at"
        expr_values = {':updated_at': datetime.utcnow().isoformat()}
        expr_names = {}

        allowed_fields = ['label_name', 'label_type', 'options', 'description', 'is_active']
        for field in allowed_fields:
            if field in body:
                # Validate label_type if provided
                if field == 'label_type' and body[field] not in ['single', 'multiple']:
                    return {
                        'statusCode': 400,
                        'headers': cors_headers,
                        'body': json.dumps({'error': 'label_type must be "single" or "multiple"'})
                    }

                # Validate options if provided
                if field == 'options' and (not isinstance(body[field], list) or len(body[field]) == 0):
                    return {
                        'statusCode': 400,
                        'headers': cors_headers,
                        'body': json.dumps({'error': 'options must be a non-empty list'})
                    }

                update_expr += f", #{field} = :{field}"
                expr_names[f'#{field}'] = field
                expr_values[f':{field}'] = body[field]

        label_configs_table.update_item(
            Key={'label_id': label_id},
            UpdateExpression=update_expr,
            ExpressionAttributeNames=expr_names,
            ExpressionAttributeValues=expr_values
        )

        # Fetch updated item
        updated_response = label_configs_table.get_item(Key={'label_id': label_id})

        return {
            'statusCode': 200,
            'headers': cors_headers,
            'body': json.dumps({
                'message': 'Label updated successfully',
                'label': updated_response['Item']
            }, cls=DecimalEncoder)
        }
    except Exception as e:
        print(f"Error updating label: {str(e)}")
        return {
            'statusCode': 500,
            'headers': cors_headers,
            'body': json.dumps({'error': str(e)})
        }


def handle_delete_label(label_id, cors_headers):
    """
    DELETE /api/labels/{label_id}
    Delete a label configuration
    """
    try:
        label_configs_table.delete_item(Key={'label_id': label_id})

        return {
            'statusCode': 200,
            'headers': cors_headers,
            'body': json.dumps({
                'message': 'Label deleted successfully',
                'label_id': label_id
            })
        }
    except Exception as e:
        print(f"Error deleting label: {str(e)}")
        return {
            'statusCode': 500,
            'headers': cors_headers,
            'body': json.dumps({'error': str(e)})
        }
