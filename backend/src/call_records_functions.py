import json
import boto3
import os
from decimal import Decimal
from datetime import datetime
from botocore.config import Config

dynamodb = boto3.resource('dynamodb', region_name=os.environ.get('DYNAMODB_REGION', 'us-east-1'))
call_records_table = dynamodb.Table(os.environ.get('CALL_RECORDS_TABLE', 'outbound-call-records'))
s3_client = boto3.client('s3', config=Config(signature_version='s3v4'))
RECORDING_BUCKET = os.environ.get('RECORDING_BUCKET', '')


class DecimalEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, Decimal):
            return int(o) if o == int(o) else float(o)
        return super().default(o)


def handle_list_call_records(event, cors_headers):
    """
    GET /api/call-records?limit=20&status=active|completed
    Reads from DynamoDB outbound-call-records table.
    Uses GSI status-startTime-index when status filter provided.
    """
    try:
        query_params = event.get('queryStringParameters') or {}
        limit = int(query_params.get('limit', '20'))
        status_filter = query_params.get('status')
        project_id = query_params.get('project_id')

        if status_filter:
            # Use GSI for status-based query
            query_kwargs = {
                'IndexName': 'status-startTime-index',
                'KeyConditionExpression': '#s = :status',
                'ExpressionAttributeNames': {'#s': 'status'},
                'ExpressionAttributeValues': {':status': status_filter},
                'ScanIndexForward': False,
                'Limit': limit
            }
            # Add project filter if provided
            if project_id:
                query_kwargs['FilterExpression'] = 'project_id = :pid'
                query_kwargs['ExpressionAttributeValues'][':pid'] = project_id
            response = call_records_table.query(**query_kwargs)
        else:
            # Scan with limit when no filter
            scan_kwargs = {'Limit': limit}
            if project_id:
                scan_kwargs['FilterExpression'] = 'project_id = :pid'
                scan_kwargs['ExpressionAttributeValues'] = {':pid': project_id}
            response = call_records_table.scan(**scan_kwargs)

        records = response.get('Items', [])

        # Sort by startTime descending
        records.sort(key=lambda x: x.get('startTime', ''), reverse=True)

        return {
            'statusCode': 200,
            'headers': cors_headers,
            'body': json.dumps({
                'records': records[:limit],
                'count': len(records[:limit])
            }, cls=DecimalEncoder)
        }
    except Exception as e:
        print(f"Error listing call records: {str(e)}")
        return {
            'statusCode': 500,
            'headers': cors_headers,
            'body': json.dumps({'error': str(e)})
        }


def handle_delete_call_record(call_sid, cors_headers):
    """
    DELETE /api/call-records/{call_sid}
    Deletes a call record from DynamoDB
    """
    try:
        # Delete the record
        call_records_table.delete_item(
            Key={'callSid': call_sid}
        )

        return {
            'statusCode': 200,
            'headers': cors_headers,
            'body': json.dumps({
                'message': 'Call record deleted successfully',
                'callSid': call_sid
            })
        }
    except Exception as e:
        print(f"Error deleting call record: {str(e)}")
        return {
            'statusCode': 500,
            'headers': cors_headers,
            'body': json.dumps({'error': str(e)})
        }


def handle_update_call_labels(call_sid, event, cors_headers):
    """
    PUT /api/call-records/{call_sid}/labels
    Update labels for a call record
    Body: { "labels": { "label_id_1": "value", "label_id_2": ["value1", "value2"] } }
    """
    try:
        body = json.loads(event['body'])
        labels = body.get('labels', {})

        # Update the record
        call_records_table.update_item(
            Key={'callSid': call_sid},
            UpdateExpression='SET labels = :labels, updated_at = :updated_at',
            ExpressionAttributeValues={
                ':labels': labels,
                ':updated_at': datetime.utcnow().isoformat()
            }
        )

        return {
            'statusCode': 200,
            'headers': cors_headers,
            'body': json.dumps({
                'message': 'Labels updated successfully',
                'callSid': call_sid,
                'labels': labels
            }, cls=DecimalEncoder)
        }
    except Exception as e:
        print(f"Error updating call labels: {str(e)}")
        return {
            'statusCode': 500,
            'headers': cors_headers,
            'body': json.dumps({'error': str(e)})
        }


def handle_get_call_record(call_sid, cors_headers):
    """
    GET /api/call-records/{call_sid}
    Get a specific call record
    """
    try:
        response = call_records_table.get_item(Key={'callSid': call_sid})

        if 'Item' not in response:
            return {
                'statusCode': 404,
                'headers': cors_headers,
                'body': json.dumps({'error': 'Call record not found'})
            }

        return {
            'statusCode': 200,
            'headers': cors_headers,
            'body': json.dumps(response['Item'], cls=DecimalEncoder)
        }
    except Exception as e:
        print(f"Error getting call record: {str(e)}")
        return {
            'statusCode': 500,
            'headers': cors_headers,
            'body': json.dumps({'error': str(e)})
        }


def handle_get_recording_url(call_sid, cors_headers):
    """
    GET /api/call-records/{call_sid}/recording
    Generate a presigned URL for downloading the call recording WAV file.
    """
    try:
        if not RECORDING_BUCKET:
            return {
                'statusCode': 500,
                'headers': cors_headers,
                'body': json.dumps({'error': 'Recording bucket not configured'})
            }

        response = call_records_table.get_item(Key={'callSid': call_sid})

        if 'Item' not in response:
            return {
                'statusCode': 404,
                'headers': cors_headers,
                'body': json.dumps({'error': 'Call record not found'})
            }

        record = response['Item']
        s3_key = record.get('recordingS3Key')

        if not s3_key:
            return {
                'statusCode': 404,
                'headers': cors_headers,
                'body': json.dumps({'error': 'No recording available for this call'})
            }

        filename = f"{call_sid}.wav"
        expires_in = 900  # 15 minutes

        download_url = s3_client.generate_presigned_url(
            'get_object',
            Params={
                'Bucket': RECORDING_BUCKET,
                'Key': s3_key,
                'ResponseContentDisposition': f'attachment; filename="{filename}"',
            },
            ExpiresIn=expires_in,
        )

        return {
            'statusCode': 200,
            'headers': cors_headers,
            'body': json.dumps({
                'downloadUrl': download_url,
                'callSid': call_sid,
                'filename': filename,
                'expiresIn': expires_in,
            })
        }
    except Exception as e:
        print(f"Error generating recording URL for {call_sid}: {str(e)}")
        return {
            'statusCode': 500,
            'headers': cors_headers,
            'body': json.dumps({'error': str(e)})
        }
