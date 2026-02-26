import json
import boto3
import os
from decimal import Decimal

dynamodb = boto3.resource('dynamodb', region_name=os.environ.get('DYNAMODB_REGION', 'us-east-1'))
call_logs_table = dynamodb.Table(os.environ.get('CALL_LOGS_TABLE', 'call-logs'))


class DecimalEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, Decimal):
            return int(o) if o == int(o) else float(o)
        return super().default(o)


def handle_get_call_logs(call_sid, cors_headers):
    """
    GET /api/call-records/{call_sid}/logs
    Fetch logs from DynamoDB for a specific call
    """
    try:
        # Query logs for this callSid
        response = call_logs_table.query(
            KeyConditionExpression='callSid = :sid',
            ExpressionAttributeValues={':sid': call_sid},
            ScanIndexForward=True  # Sort by timestamp ascending
        )

        logs = response.get('Items', [])

        return {
            'statusCode': 200,
            'headers': cors_headers,
            'body': json.dumps({
                'callSid': call_sid,
                'logs': logs,
                'count': len(logs)
            }, cls=DecimalEncoder)
        }

    except Exception as e:
        print(f"Error fetching call logs: {str(e)}")
        import traceback
        traceback.print_exc()
        return {
            'statusCode': 500,
            'headers': cors_headers,
            'body': json.dumps({'error': str(e)})
        }
