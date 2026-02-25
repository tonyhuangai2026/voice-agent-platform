import json
import os
import boto3
from datetime import datetime, timedelta
from decimal import Decimal

CALL_RECORDS_TABLE = os.environ.get('CALL_RECORDS_TABLE', 'outbound-call-records')
ECS_CLUSTER_NAME = os.environ.get('ECS_CLUSTER_NAME', 'voice-agent-cluster')
ECS_SERVICE_NAME = os.environ.get('ECS_SERVICE_NAME', 'voice-agent-service')

dynamodb = boto3.resource('dynamodb', region_name='us-west-2')
call_records_table = dynamodb.Table(CALL_RECORDS_TABLE)
ecs_client = boto3.client('ecs', region_name='us-west-2')


class DecimalEncoder(json.JSONEncoder):
    """JSON encoder that handles Decimal types from DynamoDB."""
    def default(self, obj):
        if isinstance(obj, Decimal):
            if obj % 1 == 0:
                return int(obj)
            return float(obj)
        return super().default(obj)


def _json_dumps(obj):
    return json.dumps(obj, cls=DecimalEncoder)


def handle_list_call_records(event, cors_headers):
    """List call records from DynamoDB (supports filtering by status and days)."""
    try:
        query_params = event.get('queryStringParameters') or {}
        status = query_params.get('status')
        limit = int(query_params.get('limit', '50'))
        days = int(query_params.get('days', '7'))

        if status:
            # Use GSI to query by status
            cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
            response = call_records_table.query(
                IndexName='status-startTime-index',
                KeyConditionExpression='#st = :status AND startTime >= :cutoff',
                ExpressionAttributeNames={'#st': 'status'},
                ExpressionAttributeValues={
                    ':status': status,
                    ':cutoff': cutoff,
                },
                ScanIndexForward=False,
                Limit=limit,
            )
        else:
            # Scan with time filter
            cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
            response = call_records_table.scan(
                FilterExpression='startTime >= :cutoff',
                ExpressionAttributeValues={':cutoff': cutoff},
                Limit=min(limit * 3, 300),  # Over-fetch because scan filters client-side
            )

        records = response.get('Items', [])

        # Sort by startTime descending
        records.sort(key=lambda r: r.get('startTime', ''), reverse=True)
        records = records[:limit]

        # Strip full transcript from list view for performance
        for record in records:
            transcript = record.get('transcript', [])
            record['transcriptCount'] = len(transcript)
            record.pop('transcript', None)

        return {
            'statusCode': 200,
            'headers': cors_headers,
            'body': _json_dumps({'records': records, 'count': len(records)}),
        }
    except Exception as e:
        print(f"Error listing call records: {e}")
        return {
            'statusCode': 500,
            'headers': cors_headers,
            'body': json.dumps({'error': str(e)}),
        }


def handle_get_call_record(call_sid, cors_headers):
    """Get a single call record with full transcript."""
    try:
        response = call_records_table.get_item(Key={'callSid': call_sid})
        item = response.get('Item')

        if not item:
            return {
                'statusCode': 404,
                'headers': cors_headers,
                'body': json.dumps({'error': 'Call record not found'}),
            }

        return {
            'statusCode': 200,
            'headers': cors_headers,
            'body': _json_dumps(item),
        }
    except Exception as e:
        print(f"Error getting call record {call_sid}: {e}")
        return {
            'statusCode': 500,
            'headers': cors_headers,
            'body': json.dumps({'error': str(e)}),
        }


def handle_get_ecs_status(cors_headers):
    """Query ECS service status (running/desired/pending task counts)."""
    try:
        response = ecs_client.describe_services(
            cluster=ECS_CLUSTER_NAME,
            services=[ECS_SERVICE_NAME],
        )
        services = response.get('services', [])

        if not services:
            return {
                'statusCode': 200,
                'headers': cors_headers,
                'body': json.dumps({
                    'clusterName': ECS_CLUSTER_NAME,
                    'serviceName': ECS_SERVICE_NAME,
                    'runningCount': 0,
                    'desiredCount': 0,
                    'pendingCount': 0,
                }),
            }

        svc = services[0]
        return {
            'statusCode': 200,
            'headers': cors_headers,
            'body': json.dumps({
                'clusterName': ECS_CLUSTER_NAME,
                'serviceName': ECS_SERVICE_NAME,
                'runningCount': svc.get('runningCount', 0),
                'desiredCount': svc.get('desiredCount', 0),
                'pendingCount': svc.get('pendingCount', 0),
            }),
        }
    except Exception as e:
        print(f"Error getting ECS status: {e}")
        return {
            'statusCode': 500,
            'headers': cors_headers,
            'body': json.dumps({'error': str(e)}),
        }


def handle_get_active_calls_summary(cors_headers):
    """Query all active calls from DynamoDB GSI."""
    try:
        response = call_records_table.query(
            IndexName='status-startTime-index',
            KeyConditionExpression='#st = :active',
            ExpressionAttributeNames={'#st': 'status'},
            ExpressionAttributeValues={':active': 'active'},
            ScanIndexForward=False,
        )

        items = response.get('Items', [])

        active_calls = []
        for item in items:
            active_calls.append({
                'callSid': item.get('callSid'),
                'streamSid': item.get('streamSid'),
                'customerPhone': item.get('customerPhone'),
                'customerName': item.get('customerName'),
                'voiceId': item.get('voiceId'),
                'startTime': item.get('startTime'),
                'turnCount': item.get('turnCount', 0),
                'instanceId': item.get('instanceId'),
            })

        return {
            'statusCode': 200,
            'headers': cors_headers,
            'body': _json_dumps({
                'activeCalls': active_calls,
                'totalActive': len(active_calls),
            }),
        }
    except Exception as e:
        print(f"Error getting active calls summary: {e}")
        return {
            'statusCode': 500,
            'headers': cors_headers,
            'body': json.dumps({'error': str(e)}),
        }
