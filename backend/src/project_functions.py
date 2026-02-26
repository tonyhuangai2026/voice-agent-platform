import json
import boto3
import os
import uuid
from datetime import datetime
from decimal import Decimal

dynamodb = boto3.resource('dynamodb', region_name=os.environ.get('DYNAMODB_REGION', 'us-east-1'))
projects_table = dynamodb.Table(os.environ.get('PROJECTS_TABLE', 'outbound-projects'))


class DecimalEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, Decimal):
            return int(o) if o == int(o) else float(o)
        return super().default(o)


def handle_create_project(event, cors_headers):
    """
    POST /api/projects
    Create a new project
    """
    try:
        body = json.loads(event.get('body', '{}'))

        # Required fields
        project_name = body.get('project_name')
        project_type = body.get('project_type', 'other')
        description = body.get('description', '')

        if not project_name:
            return {
                'statusCode': 400,
                'headers': cors_headers,
                'body': json.dumps({'error': 'project_name is required'})
            }

        # Generate project ID
        project_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()

        # Build project item
        project = {
            'project_id': project_id,
            'project_name': project_name,
            'project_type': project_type,
            'description': description,
            'status': body.get('status', 'active'),
            'default_prompt_id': body.get('default_prompt_id'),
            'default_flow_id': body.get('default_flow_id'),
            'settings': body.get('settings', {}),
            'created_at': now,
            'updated_at': now
        }

        projects_table.put_item(Item=project)

        return {
            'statusCode': 201,
            'headers': cors_headers,
            'body': json.dumps({
                'message': 'Project created successfully',
                'project': project
            }, cls=DecimalEncoder)
        }
    except Exception as e:
        print(f"Error creating project: {str(e)}")
        return {
            'statusCode': 500,
            'headers': cors_headers,
            'body': json.dumps({'error': str(e)})
        }


def handle_list_projects(event, cors_headers):
    """
    GET /api/projects?status=active
    List all projects with optional status filter
    """
    try:
        query_params = event.get('queryStringParameters') or {}
        status_filter = query_params.get('status')

        if status_filter:
            # Use GSI for status-based query
            response = projects_table.query(
                IndexName='status-createdAt-index',
                KeyConditionExpression='#s = :status',
                ExpressionAttributeNames={'#s': 'status'},
                ExpressionAttributeValues={':status': status_filter},
                ScanIndexForward=False  # Most recent first
            )
        else:
            # Scan all projects
            response = projects_table.scan()

        projects = response.get('Items', [])

        # Sort by created_at descending
        projects.sort(key=lambda x: x.get('created_at', ''), reverse=True)

        return {
            'statusCode': 200,
            'headers': cors_headers,
            'body': json.dumps({
                'projects': projects,
                'count': len(projects)
            }, cls=DecimalEncoder)
        }
    except Exception as e:
        print(f"Error listing projects: {str(e)}")
        return {
            'statusCode': 500,
            'headers': cors_headers,
            'body': json.dumps({'error': str(e)})
        }


def handle_get_project(project_id, cors_headers):
    """
    GET /api/projects/{project_id}
    Get a single project by ID
    """
    try:
        response = projects_table.get_item(
            Key={'project_id': project_id}
        )

        project = response.get('Item')

        if not project:
            return {
                'statusCode': 404,
                'headers': cors_headers,
                'body': json.dumps({'error': 'Project not found'})
            }

        return {
            'statusCode': 200,
            'headers': cors_headers,
            'body': json.dumps(project, cls=DecimalEncoder)
        }
    except Exception as e:
        print(f"Error getting project: {str(e)}")
        return {
            'statusCode': 500,
            'headers': cors_headers,
            'body': json.dumps({'error': str(e)})
        }


def handle_update_project(project_id, event, cors_headers):
    """
    PUT /api/projects/{project_id}
    Update an existing project
    """
    try:
        body = json.loads(event.get('body', '{}'))

        # Build update expression
        update_expr = "SET updated_at = :updated_at"
        expr_values = {
            ':updated_at': datetime.utcnow().isoformat()
        }
        expr_names = {}

        # Update fields
        if 'project_name' in body:
            update_expr += ", project_name = :project_name"
            expr_values[':project_name'] = body['project_name']

        if 'project_type' in body:
            update_expr += ", project_type = :project_type"
            expr_values[':project_type'] = body['project_type']

        if 'description' in body:
            update_expr += ", description = :description"
            expr_values[':description'] = body['description']

        if 'status' in body:
            update_expr += ", #status = :status"
            expr_values[':status'] = body['status']
            expr_names['#status'] = 'status'

        if 'default_prompt_id' in body:
            update_expr += ", default_prompt_id = :default_prompt_id"
            expr_values[':default_prompt_id'] = body['default_prompt_id']

        if 'default_flow_id' in body:
            update_expr += ", default_flow_id = :default_flow_id"
            expr_values[':default_flow_id'] = body['default_flow_id']

        if 'settings' in body:
            update_expr += ", settings = :settings"
            expr_values[':settings'] = body['settings']

        update_kwargs = {
            'Key': {'project_id': project_id},
            'UpdateExpression': update_expr,
            'ExpressionAttributeValues': expr_values,
            'ReturnValues': 'ALL_NEW'
        }

        if expr_names:
            update_kwargs['ExpressionAttributeNames'] = expr_names

        response = projects_table.update_item(**update_kwargs)

        return {
            'statusCode': 200,
            'headers': cors_headers,
            'body': json.dumps({
                'message': 'Project updated successfully',
                'project': response['Attributes']
            }, cls=DecimalEncoder)
        }
    except Exception as e:
        print(f"Error updating project: {str(e)}")
        return {
            'statusCode': 500,
            'headers': cors_headers,
            'body': json.dumps({'error': str(e)})
        }


def handle_delete_project(project_id, cors_headers):
    """
    DELETE /api/projects/{project_id}
    Delete (archive) a project - soft delete by setting status to 'archived'
    """
    try:
        response = projects_table.update_item(
            Key={'project_id': project_id},
            UpdateExpression='SET #status = :status, updated_at = :updated_at',
            ExpressionAttributeNames={'#status': 'status'},
            ExpressionAttributeValues={
                ':status': 'archived',
                ':updated_at': datetime.utcnow().isoformat()
            },
            ReturnValues='ALL_NEW'
        )

        return {
            'statusCode': 200,
            'headers': cors_headers,
            'body': json.dumps({
                'message': 'Project archived successfully',
                'project': response['Attributes']
            }, cls=DecimalEncoder)
        }
    except Exception as e:
        print(f"Error deleting project: {str(e)}")
        return {
            'statusCode': 500,
            'headers': cors_headers,
            'body': json.dumps({'error': str(e)})
        }


def handle_get_project_stats(project_id, cors_headers):
    """
    GET /api/projects/{project_id}/stats
    Get statistics for a project
    """
    try:
        # Query customers table for this project
        customers_table = dynamodb.Table(os.environ.get('CUSTOMERS_TABLE', 'outbound-customers'))
        customers_response = customers_table.scan(
            FilterExpression='project_id = :pid',
            ExpressionAttributeValues={':pid': project_id}
        )
        customer_items = customers_response.get('Items', [])
        total_customers = len(customer_items)

        # Calculate total calls from customers
        total_calls = sum(int(item.get('call_count', 0)) for item in customer_items)

        # Query call records for this project
        call_records_table = dynamodb.Table(os.environ.get('CALL_RECORDS_TABLE', 'outbound-call-records'))

        # Get active calls
        active_calls_response = call_records_table.scan(
            FilterExpression='#s = :status AND project_id = :pid',
            ExpressionAttributeNames={'#s': 'status'},
            ExpressionAttributeValues={':status': 'active', ':pid': project_id}
        )
        active_calls = len(active_calls_response.get('Items', []))

        # Calculate success rate
        completed_calls_response = call_records_table.scan(
            FilterExpression='project_id = :pid',
            ExpressionAttributeValues={':pid': project_id},
            Limit=100
        )
        completed_items = completed_calls_response.get('Items', [])
        success_count = sum(1 for item in completed_items if item.get('status') == 'completed')
        success_rate = (success_count / len(completed_items) * 100) if completed_items else 0.0

        stats = {
            'project_id': project_id,
            'total_customers': total_customers,
            'total_calls': total_calls,
            'active_calls': active_calls,
            'success_rate': round(success_rate, 1),
            'avg_call_duration': 0  # TODO: calculate from call records
        }

        return {
            'statusCode': 200,
            'headers': cors_headers,
            'body': json.dumps(stats, cls=DecimalEncoder)
        }
    except Exception as e:
        print(f"Error getting project stats: {str(e)}")
        return {
            'statusCode': 500,
            'headers': cors_headers,
            'body': json.dumps({'error': str(e)})
        }
