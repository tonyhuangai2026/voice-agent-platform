import json
import boto3
import os
from datetime import datetime, timedelta
from botocore.config import Config
import concurrent.futures
import traceback
import re
import uuid
import csv
from io import StringIO
from decimal import Decimal

# Import function modules
from customer_functions import (
    handle_import_customers, handle_list_customers, handle_get_customer,
    handle_update_customer, handle_delete_customer, handle_single_call, handle_batch_call
)
from flow_config_functions import (
    handle_create_flow, handle_list_flows, handle_get_flow,
    handle_update_flow, handle_delete_flow
)
from prompt_config_functions import (
    handle_create_prompt, handle_list_prompts, handle_get_prompt,
    handle_update_prompt, handle_delete_prompt
)
from call_records_functions import (
    handle_list_call_records, handle_delete_call_record,
    handle_update_call_labels, handle_get_call_record,
    handle_get_recording_url
)
from project_functions import (
    handle_create_project, handle_list_projects, handle_get_project,
    handle_update_project, handle_delete_project, handle_get_project_stats
)
from label_config_functions import (
    handle_list_labels, handle_get_label, handle_create_label,
    handle_update_label, handle_delete_label
)
from auto_label_functions import handle_auto_label_call
from call_logs_functions import handle_get_call_logs
from auth_functions import handle_register, handle_login, handle_verify, verify_auth_middleware

# Initialize AWS clients
DYNAMODB_REGION = os.environ.get('DYNAMODB_REGION', 'us-east-1')
CONNECT_REGION = os.environ.get('CONNECT_REGION', 'us-west-2')

s3_client = boto3.client('s3', config=Config(signature_version='s3v4'))
connect_client = boto3.client('connect', region_name=CONNECT_REGION)
bedrock_client = boto3.client('bedrock-runtime', region_name=CONNECT_REGION)
dynamodb = boto3.resource('dynamodb', region_name=DYNAMODB_REGION)
customers_table = dynamodb.Table(os.environ.get('CUSTOMERS_TABLE', 'outbound-customers'))

# Label definitions
INTENTION_TAGS = {
    'A': {'zh': '已还款', 'es': 'Haber pagado'},
    'B': {'zh': '承诺准时还款', 'es': 'Prometer pagar a tiempo'},
    'C': {'zh': '承诺晚点还款', 'es': 'Prometer pagar más tarde'},
    'D': {'zh': '未承诺还款', 'es': 'No ha prometido pagar'},
    'E': {'zh': '拒绝还款', 'es': 'Rechazar pagar'},
    'M': {'zh': '接通后为语音/留言信箱', 'es': 'Buzón de voz'},
    'F': {'zh': '未接通(占线/未接/拒接/关机/无法接通)', 'es': 'No conectada (ocupada/pérdida/rechazada/apagada/no se puede conectar)'},
    'G': {'zh': '未接通(用户欠费/线路故障/呼叫失败/改号)', 'es': 'No conectado (Cuenta atrasada/Fallo de línea/Llamada fallida/Cambio de número)'},
    'H': {'zh': '未接通(黑名单/已拦截/空号/停机)', 'es': 'No contestado (en lista negra/ha sido bloqueado/número inexistente/suspensión de línea)'}
}

PERSONALITY_TAGS = {
    'complaint': {'zh': '投诉', 'es': 'Queja'},
    'busy': {'zh': '忙', 'es': 'Ocupado'},
    'self': {'zh': '是本人', 'es': 'En persona'},
    'family_friend': {'zh': '家人朋友', 'es': 'Familiares y amigos'},
    'wrong_number': {'zh': '打错电话', 'es': 'Llamar al número incorrecto'},
    'pay_tomorrow': {'zh': '明天能还', 'es': 'Pagar mañana'},
    'no_money': {'zh': '没钱', 'es': 'No tener dinero'},
    'difficulty_paying': {'zh': '还款困难', 'es': 'Dificultades para pagar'},
    'borrower_deceased': {'zh': '借款人去世', 'es': 'El pretamista ha muerto'},
    'unexpected_change': {'zh': '遭遇变故', 'es': 'Sufrir un cambio inesperado'},
    'high_interest': {'zh': '利息太高', 'es': 'El interés es alto'},
    'pressured_willing': {'zh': '施压后-愿意还款', 'es': 'Presionado-voluntad de pagar'},
    'informed_willing': {'zh': '告知还款-愿意还款', 'es': 'Informado- voluntad de pagar'},
    'partial_payment': {'zh': '要求最低还款/部分还款', 'es': 'Pedir el pago mínimo / el pago parcial'},
    'request_reduction': {'zh': '要求减免', 'es': 'Pedir una rebaja'},
    'request_extension': {'zh': '要求展期', 'es': 'Pedir una prórroga'}
}

# Environment variables
UPLOAD_BUCKET = os.environ.get('UPLOAD_BUCKET', 'voice-agent-calls')
TRANSCRIPT_BUCKET = os.environ.get('TRANSCRIPT_BUCKET', 'amazon-connect-33e29c98c260')
TRANSCRIPT_PREFIX = os.environ.get('TRANSCRIPT_PREFIX', 'connect/tonyhh/ChatTranscripts/')
VOICE_ANALYSIS_PREFIX = os.environ.get('VOICE_ANALYSIS_PREFIX', 'Analysis/Voice/ivr/')
INSTANCE_ID = os.environ.get('INSTANCE_ID', 'a60dd182-7f8f-495b-945e-43420832f01c')

def search_contacts_paginated(limit, time_range, search_criteria=None):
    """
    Search contacts with pagination support. Amazon Connect limits MaxResults to 100,
    so we paginate with NextToken to fetch up to `limit` contacts.
    """
    all_contacts = []
    next_token = None

    while len(all_contacts) < limit:
        batch_size = min(limit - len(all_contacts), 100)
        params = {
            'InstanceId': INSTANCE_ID,
            'TimeRange': time_range,
            'MaxResults': batch_size
        }
        if search_criteria:
            params['SearchCriteria'] = search_criteria
        if next_token:
            params['NextToken'] = next_token

        response = connect_client.search_contacts(**params)
        contacts = response.get('Contacts', [])
        all_contacts.extend(contacts)

        next_token = response.get('NextToken')
        if not next_token or not contacts:
            break

    return all_contacts


def lambda_handler(event, context):
    """
    API Gateway Lambda handler for Voice Agent Platform
    """
    print(f"Received event: {json.dumps(event)}")

    # Handle API Gateway v2 (HTTP API) format
    http_method = event.get('httpMethod') or event.get('requestContext', {}).get('http', {}).get('method')
    path = event.get('path') or event.get('rawPath', '')

    # Add CORS headers to all responses
    cors_headers = {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token',
        'Access-Control-Allow-Methods': 'GET,POST,PUT,DELETE,OPTIONS'
    }

    # Handle CORS preflight
    if http_method == 'OPTIONS':
        return {
            'statusCode': 200,
            'headers': cors_headers,
            'body': ''
        }

    try:
        # Auth routes (no authentication required)
        if path == '/api/auth/register' and http_method == 'POST':
            return handle_register(event, cors_headers)
        elif path == '/api/auth/login' and http_method == 'POST':
            return handle_login(event, cors_headers)
        elif path == '/api/auth/verify' and http_method == 'GET':
            return handle_verify(event, cors_headers)

        # All other routes require authentication
        user_id = verify_auth_middleware(event)
        if not user_id:
            return {
                'statusCode': 401,
                'headers': cors_headers,
                'body': json.dumps({'error': 'Unauthorized. Please log in.'})
            }

        # Protected route handling
        if path == '/api/upload-url' and http_method == 'POST':
            return handle_upload_url(event, cors_headers)
        elif path == '/api/records' and http_method == 'GET':
            return handle_list_all_records(event, cors_headers)
        elif path == '/api/contacts' and http_method == 'GET':
            return handle_list_contacts(event, cors_headers)
        elif path.startswith('/api/contacts/') and http_method == 'GET':
            contact_id = path.split('/')[-1]
            return handle_get_contact(contact_id, cors_headers)
        elif path == '/api/transcripts' and http_method == 'GET':
            return handle_list_transcripts(event, cors_headers)
        elif path.startswith('/api/transcripts/') and http_method == 'GET':
            contact_id = path.split('/')[-1]
            return handle_get_transcript(contact_id, cors_headers)
        elif path.startswith('/api/analyze/') and http_method == 'POST':
            contact_id = path.split('/')[-1]
            return handle_analyze_conversation(contact_id, cors_headers)
        elif path.startswith('/api/analysis/') and http_method == 'GET':
            contact_id = path.split('/')[-1]
            return handle_get_analysis(contact_id, cors_headers)
        elif path == '/api/customers/import' and http_method == 'POST':
            return handle_import_customers(event, cors_headers)
        elif path == '/api/customers' and http_method == 'GET':
            return handle_list_customers(event, cors_headers)
        elif path.startswith('/api/customers/') and http_method == 'GET':
            customer_id = path.split('/')[-1]
            return handle_get_customer(customer_id, cors_headers)
        elif path.startswith('/api/customers/') and http_method == 'PUT':
            customer_id = path.split('/')[-1]
            return handle_update_customer(customer_id, event, cors_headers)
        elif path.startswith('/api/customers/') and http_method == 'DELETE':
            customer_id = path.split('/')[-1]
            return handle_delete_customer(customer_id, cors_headers)
        elif path.startswith('/api/call/') and http_method == 'POST':
            if path == '/api/call/batch':
                return handle_batch_call(event, cors_headers)
            else:
                customer_id = path.split('/')[-1]
                return handle_single_call(customer_id, event, cors_headers)
        elif path == '/api/flows' and http_method == 'GET':
            return handle_list_flows(event, cors_headers)
        elif path == '/api/flows' and http_method == 'POST':
            return handle_create_flow(event, cors_headers)
        elif path.startswith('/api/flows/') and http_method == 'GET':
            flow_id = path.split('/')[-1]
            return handle_get_flow(flow_id, cors_headers)
        elif path.startswith('/api/flows/') and http_method == 'PUT':
            flow_id = path.split('/')[-1]
            return handle_update_flow(flow_id, event, cors_headers)
        elif path.startswith('/api/flows/') and http_method == 'DELETE':
            flow_id = path.split('/')[-1]
            return handle_delete_flow(flow_id, cors_headers)
        elif path == '/api/call-records' and http_method == 'GET':
            return handle_list_call_records(event, cors_headers)
        elif path.startswith('/api/call-records/') and '/logs' in path and http_method == 'GET':
            call_sid = path.split('/')[3]
            return handle_get_call_logs(call_sid, cors_headers)
        elif path.startswith('/api/call-records/') and '/labels' in path and http_method == 'PUT':
            call_sid = path.split('/')[3]
            return handle_update_call_labels(call_sid, event, cors_headers)
        elif path.startswith('/api/call-records/') and '/auto-label' in path and http_method == 'POST':
            call_sid = path.split('/')[3]
            return handle_auto_label_call(call_sid, cors_headers)
        elif path.startswith('/api/call-records/') and '/recording' in path and http_method == 'GET':
            call_sid = path.split('/')[3]
            return handle_get_recording_url(call_sid, cors_headers)
        elif path.startswith('/api/call-records/') and http_method == 'GET':
            # Simple GET for call record details
            call_sid = path.split('/')[-1]
            return handle_get_call_record(call_sid, cors_headers)
        elif path.startswith('/api/call-records/') and http_method == 'DELETE':
            call_sid = path.split('/')[-1]
            return handle_delete_call_record(call_sid, cors_headers)
        elif path == '/api/projects' and http_method == 'GET':
            return handle_list_projects(event, cors_headers)
        elif path == '/api/projects' and http_method == 'POST':
            return handle_create_project(event, cors_headers)
        elif path.startswith('/api/projects/') and http_method == 'GET':
            parts = path.split('/')
            project_id = parts[3]
            if len(parts) > 4 and parts[4] == 'stats':
                return handle_get_project_stats(project_id, cors_headers)
            else:
                return handle_get_project(project_id, cors_headers)
        elif path.startswith('/api/projects/') and http_method == 'PUT':
            project_id = path.split('/')[-1]
            return handle_update_project(project_id, event, cors_headers)
        elif path.startswith('/api/projects/') and http_method == 'DELETE':
            project_id = path.split('/')[-1]
            return handle_delete_project(project_id, cors_headers)
        elif path == '/api/prompts' and http_method == 'GET':
            return handle_list_prompts(event, cors_headers)
        elif path == '/api/prompts' and http_method == 'POST':
            return handle_create_prompt(event, cors_headers)
        elif path.startswith('/api/prompts/') and http_method == 'GET':
            prompt_id = path.split('/')[-1]
            return handle_get_prompt(prompt_id, cors_headers)
        elif path.startswith('/api/prompts/') and http_method == 'PUT':
            prompt_id = path.split('/')[-1]
            return handle_update_prompt(prompt_id, event, cors_headers)
        elif path.startswith('/api/prompts/') and http_method == 'DELETE':
            prompt_id = path.split('/')[-1]
            return handle_delete_prompt(prompt_id, cors_headers)
        elif path == '/api/labels' and http_method == 'GET':
            return handle_list_labels(event, cors_headers)
        elif path == '/api/labels' and http_method == 'POST':
            return handle_create_label(event, cors_headers)
        elif path.startswith('/api/labels/') and http_method == 'GET':
            label_id = path.split('/')[-1]
            return handle_get_label(label_id, cors_headers)
        elif path.startswith('/api/labels/') and http_method == 'PUT':
            label_id = path.split('/')[-1]
            return handle_update_label(label_id, event, cors_headers)
        elif path.startswith('/api/labels/') and http_method == 'DELETE':
            label_id = path.split('/')[-1]
            return handle_delete_label(label_id, cors_headers)
        else:
            return {
                'statusCode': 404,
                'headers': cors_headers,
                'body': json.dumps({'error': 'Not found'})
            }
    except Exception as e:
        print(f"Error: {str(e)}")
        return {
            'statusCode': 500,
            'headers': cors_headers,
            'body': json.dumps({'error': str(e)})
        }


def handle_upload_url(event, cors_headers):
    """
    Generate pre-signed URL for CSV upload
    """
    try:
        body = json.loads(event.get('body', '{}'))
        filename = body.get('filename', 'customer_list.csv')

        # Generate pre-signed URL for upload
        presigned_url = s3_client.generate_presigned_url(
            'put_object',
            Params={
                'Bucket': UPLOAD_BUCKET,
                'Key': filename,
                'ContentType': 'text/csv'
            },
            ExpiresIn=3600  # 1 hour
        )

        return {
            'statusCode': 200,
            'headers': cors_headers,
            'body': json.dumps({
                'uploadUrl': presigned_url,
                'filename': filename,
                'bucket': UPLOAD_BUCKET
            })
        }
    except Exception as e:
        print(f"Error generating upload URL: {str(e)}")
        return {
            'statusCode': 500,
            'headers': cors_headers,
            'body': json.dumps({'error': str(e)})
        }


def get_contact_detail(contact_id):
    """
    Get single contact detail - designed for concurrent execution
    """
    try:
        detail = connect_client.describe_contact(
            InstanceId=INSTANCE_ID,
            ContactId=contact_id
        ).get('Contact', {})

        customer_endpoint = detail.get('CustomerEndpoint', {})
        system_endpoint = detail.get('SystemEndpoint', {})
        attributes = detail.get('Attributes', {})

        return {
            'contactId': contact_id,
            'customerPhone': customer_endpoint.get('Address'),
            'systemPhone': system_endpoint.get('Address'),
            'customerName': attributes.get('CustomerName'),
            'debtAmount': attributes.get('DebtAmount'),
            'disconnectReason': detail.get('DisconnectReason')
        }
    except Exception as e:
        print(f"Error getting contact detail {contact_id}: {str(e)}")
        return {
            'contactId': contact_id,
            'customerPhone': None,
            'systemPhone': None,
            'customerName': None,
            'debtAmount': None,
            'disconnectReason': None
        }


def check_transcript_exists(contact_id, channel=None, initiation_timestamp=None):
    """
    Check if transcript exists for a contact.
    CHAT transcripts always exist (Connect stores them automatically).
    VOICE transcripts are checked via Analysis/Voice/ivr/YYYY/MM/DD/ S3 prefix.
    """
    try:
        if channel == 'CHAT':
            return contact_id, True

        # Check Voice analysis with date-based prefix
        voice_key = _find_voice_transcript_key(contact_id, initiation_timestamp)
        if voice_key:
            return contact_id, True

        return contact_id, False
    except Exception as e:
        print(f"Error checking transcript for {contact_id}: {str(e)}")
        return contact_id, False


def handle_list_all_records(event, cors_headers):
    """
    List all records - OPTIMIZED with concurrent processing
    """
    try:
        query_params = event.get('queryStringParameters') or {}
        limit = int(query_params.get('limit', '20'))  # Changed default to 20
        days = int(query_params.get('days', '7'))

        # Step 1: Search contacts from Connect (fast)
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(days=days)

        try:
            time_range = {
                'Type': 'INITIATION_TIMESTAMP',
                'StartTime': start_time,
                'EndTime': end_time
            }
            contacts = search_contacts_paginated(limit, time_range)

            if not contacts:
                return {
                    'statusCode': 200,
                    'headers': cors_headers,
                    'body': json.dumps({'records': [], 'count': 0})
                }

            contact_ids = [c.get('Id') for c in contacts]

            # Step 2: Concurrent fetch contact details (10 workers)
            contact_details = {}
            with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
                results = executor.map(get_contact_detail, contact_ids)
                for detail in results:
                    contact_details[detail['contactId']] = detail

            # Step 3: Concurrent check transcripts (20 workers)
            # Build channel map and timestamp map from search results
            channel_map = {c.get('Id'): c.get('Channel') for c in contacts}
            timestamp_map = {c.get('Id'): c.get('InitiationTimestamp') for c in contacts}
            transcript_status = {}
            with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
                futures = {
                    executor.submit(check_transcript_exists, cid, channel_map.get(cid), timestamp_map.get(cid)): cid
                    for cid in contact_ids
                }
                for future in concurrent.futures.as_completed(futures):
                    contact_id, has_transcript = future.result()
                    transcript_status[contact_id] = has_transcript

            # Step 4: Merge results
            records = []
            for contact in contacts:
                contact_id = contact.get('Id')
                detail = contact_details.get(contact_id, {})

                records.append({
                    'contactId': contact_id,
                    'channel': contact.get('Channel'),
                    'initiationMethod': contact.get('InitiationMethod'),
                    'timestamp': contact.get('InitiationTimestamp').isoformat() if contact.get('InitiationTimestamp') else None,
                    'customerPhone': detail.get('customerPhone'),
                    'systemPhone': detail.get('systemPhone'),
                    'customerName': detail.get('customerName'),
                    'debtAmount': detail.get('debtAmount'),
                    'disconnectReason': detail.get('disconnectReason'),
                    'hasTranscript': transcript_status.get(contact_id, False)
                })

            # Sort by timestamp descending
            records.sort(key=lambda x: x.get('timestamp') or '', reverse=True)

            return {
                'statusCode': 200,
                'headers': cors_headers,
                'body': json.dumps({
                    'records': records[:limit],
                    'count': len(records[:limit])
                })
            }

        except Exception as e:
            print(f"Error searching contacts: {str(e)}")
            traceback.print_exc()
            return {
                'statusCode': 500,
                'headers': cors_headers,
                'body': json.dumps({'error': str(e)})
            }

    except Exception as e:
        print(f"Error listing all records: {str(e)}")
        traceback.print_exc()
        return {
            'statusCode': 500,
            'headers': cors_headers,
            'body': json.dumps({'error': str(e)})
        }


def handle_list_contacts(event, cors_headers):
    """
    List contacts from Amazon Connect with phone numbers and customer info
    """
    try:
        query_params = event.get('queryStringParameters') or {}
        limit = int(query_params.get('limit', '50'))
        channel = query_params.get('channel', 'VOICE')  # VOICE or CHAT
        days = int(query_params.get('days', '7'))  # Default last 7 days

        # Calculate time range
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(days=days)

        # Search contacts with pagination
        time_range = {
            'Type': 'INITIATION_TIMESTAMP',
            'StartTime': start_time,
            'EndTime': end_time
        }
        raw_contacts = search_contacts_paginated(limit, time_range)

        contacts = []
        for contact in raw_contacts:
            contact_id = contact.get('Id')

            # Get detailed contact info
            try:
                detail = connect_client.describe_contact(
                    InstanceId=INSTANCE_ID,
                    ContactId=contact_id
                ).get('Contact', {})

                customer_endpoint = detail.get('CustomerEndpoint', {})
                system_endpoint = detail.get('SystemEndpoint', {})
                attributes = detail.get('Attributes', {})

                contacts.append({
                    'contactId': contact_id,
                    'channel': contact.get('Channel'),
                    'initiationMethod': contact.get('InitiationMethod'),
                    'initiationTimestamp': contact.get('InitiationTimestamp').isoformat() if contact.get('InitiationTimestamp') else None,
                    'disconnectTimestamp': contact.get('DisconnectTimestamp').isoformat() if contact.get('DisconnectTimestamp') else None,
                    'customerPhone': customer_endpoint.get('Address'),
                    'systemPhone': system_endpoint.get('Address'),
                    'customerName': attributes.get('CustomerName'),
                    'debtAmount': attributes.get('DebtAmount'),
                    'disconnectReason': detail.get('DisconnectReason')
                })
            except Exception as e:
                print(f"Error getting contact detail {contact_id}: {str(e)}")
                contacts.append({
                    'contactId': contact_id,
                    'channel': contact.get('Channel'),
                    'initiationMethod': contact.get('InitiationMethod'),
                    'initiationTimestamp': contact.get('InitiationTimestamp').isoformat() if contact.get('InitiationTimestamp') else None,
                })

        # Filter by channel if specified
        if channel:
            contacts = [c for c in contacts if c.get('channel') == channel]

        return {
            'statusCode': 200,
            'headers': cors_headers,
            'body': json.dumps({
                'contacts': contacts[:limit],
                'count': len(contacts[:limit])
            })
        }
    except Exception as e:
        print(f"Error listing contacts: {str(e)}")
        return {
            'statusCode': 500,
            'headers': cors_headers,
            'body': json.dumps({'error': str(e)})
        }


def handle_get_contact(contact_id, cors_headers):
    """
    Get detailed contact information including phone numbers
    """
    try:
        detail = connect_client.describe_contact(
            InstanceId=INSTANCE_ID,
            ContactId=contact_id
        ).get('Contact', {})

        customer_endpoint = detail.get('CustomerEndpoint', {})
        system_endpoint = detail.get('SystemEndpoint', {})
        attributes = detail.get('Attributes', {})

        return {
            'statusCode': 200,
            'headers': cors_headers,
            'body': json.dumps({
                'contactId': contact_id,
                'channel': detail.get('Channel'),
                'initiationMethod': detail.get('InitiationMethod'),
                'customerPhone': customer_endpoint.get('Address'),
                'systemPhone': system_endpoint.get('Address'),
                'customerName': attributes.get('CustomerName'),
                'debtAmount': attributes.get('DebtAmount'),
                'disconnectReason': detail.get('DisconnectReason'),
                'initiationTimestamp': detail.get('InitiationTimestamp').isoformat() if detail.get('InitiationTimestamp') else None,
                'disconnectTimestamp': detail.get('DisconnectTimestamp').isoformat() if detail.get('DisconnectTimestamp') else None,
            })
        }
    except Exception as e:
        print(f"Error getting contact: {str(e)}")
        return {
            'statusCode': 500,
            'headers': cors_headers,
            'body': json.dumps({'error': str(e)})
        }


def handle_list_transcripts(event, cors_headers):
    """
    List chat transcripts using Connect search_contacts API with concurrent detail fetching.
    """
    try:
        query_params = event.get('queryStringParameters') or {}
        limit = int(query_params.get('limit', '50'))
        days = int(query_params.get('days', '7'))

        # Calculate time range
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(days=days)

        # Search contacts via Connect API with pagination
        time_range = {
            'Type': 'INITIATION_TIMESTAMP',
            'StartTime': start_time,
            'EndTime': end_time
        }

        # Try to filter by CHAT channel via SearchCriteria
        try:
            contacts = search_contacts_paginated(limit, time_range, search_criteria={'Channels': ['CHAT']})
        except Exception as e:
            # Fallback: fetch all contacts and filter client-side
            print(f"Channel filter not supported, falling back to client filter: {str(e)}")
            all_contacts = search_contacts_paginated(limit, time_range)
            contacts = [c for c in all_contacts if c.get('Channel') == 'CHAT']

        if not contacts:
            return {
                'statusCode': 200,
                'headers': cors_headers,
                'body': json.dumps({'transcripts': [], 'count': 0})
            }

        contact_ids = [c.get('Id') for c in contacts]

        # Concurrent fetch contact details
        contact_details = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            results = executor.map(get_contact_detail, contact_ids)
            for detail in results:
                contact_details[detail['contactId']] = detail

        # Build transcript list
        transcripts = []
        for contact in contacts:
            contact_id = contact.get('Id')
            detail = contact_details.get(contact_id, {})

            transcripts.append({
                'contactId': contact_id,
                'timestamp': contact.get('InitiationTimestamp').isoformat() if contact.get('InitiationTimestamp') else None,
                'channel': contact.get('Channel'),
                'initiationMethod': contact.get('InitiationMethod'),
                'customerPhone': detail.get('customerPhone'),
                'systemPhone': detail.get('systemPhone'),
                'customerName': detail.get('customerName'),
                'debtAmount': detail.get('debtAmount'),
                'disconnectReason': detail.get('disconnectReason')
            })

        # Sort by timestamp descending (newest first)
        transcripts.sort(key=lambda x: x.get('timestamp') or '', reverse=True)

        return {
            'statusCode': 200,
            'headers': cors_headers,
            'body': json.dumps({
                'transcripts': transcripts[:limit],
                'count': len(transcripts[:limit])
            })
        }
    except Exception as e:
        print(f"Error listing transcripts: {str(e)}")
        traceback.print_exc()
        return {
            'statusCode': 500,
            'headers': cors_headers,
            'body': json.dumps({'error': str(e)})
        }


def _find_chat_transcript_key(contact_id, initiation_timestamp):
    """
    Find chat transcript S3 key using precise date-based prefix.
    Falls back to previous day for UTC midnight boundary cases.
    """
    if not initiation_timestamp:
        return None

    # Try the initiation date and the previous day (UTC midnight boundary)
    dates_to_try = [initiation_timestamp]
    prev_day = initiation_timestamp - timedelta(days=1)
    dates_to_try.append(prev_day)

    for dt in dates_to_try:
        prefix = f"{TRANSCRIPT_PREFIX}{dt.year}/{dt.month:02d}/{dt.day:02d}/{contact_id}"
        response = s3_client.list_objects_v2(
            Bucket=TRANSCRIPT_BUCKET,
            Prefix=prefix,
            MaxKeys=1
        )
        contents = response.get('Contents', [])
        if contents:
            return contents[0]['Key']

    return None


def _find_voice_transcript_key(contact_id, initiation_timestamp):
    """
    Find voice analysis transcript S3 key using date-based prefix.
    Path pattern: Analysis/Voice/ivr/YYYY/MM/DD/{contactId}_analysis_*.json
    Falls back to previous day for UTC midnight boundary cases.
    """
    if not initiation_timestamp:
        return None

    dates_to_try = [initiation_timestamp]
    prev_day = initiation_timestamp - timedelta(days=1)
    dates_to_try.append(prev_day)

    for dt in dates_to_try:
        prefix = f"{VOICE_ANALYSIS_PREFIX}{dt.year}/{dt.month:02d}/{dt.day:02d}/{contact_id}"
        response = s3_client.list_objects_v2(
            Bucket=TRANSCRIPT_BUCKET,
            Prefix=prefix,
            MaxKeys=1
        )
        contents = response.get('Contents', [])
        if contents:
            return contents[0]['Key']

    return None


def handle_get_transcript(contact_id, cors_headers):
    """
    Get transcript by contact ID - searches both Chat transcripts and Voice analysis
    """
    try:
        # First get contact details for phone numbers and initiation timestamp
        contact_info = {}
        channel = None
        initiation_timestamp = None
        try:
            detail = connect_client.describe_contact(
                InstanceId=INSTANCE_ID,
                ContactId=contact_id
            ).get('Contact', {})

            customer_endpoint = detail.get('CustomerEndpoint', {})
            system_endpoint = detail.get('SystemEndpoint', {})
            attributes = detail.get('Attributes', {})
            channel = detail.get('Channel')
            initiation_timestamp = detail.get('InitiationTimestamp')

            contact_info = {
                'customerPhone': customer_endpoint.get('Address'),
                'systemPhone': system_endpoint.get('Address'),
                'customerName': attributes.get('CustomerName'),
                'debtAmount': attributes.get('DebtAmount'),
                'channel': channel,
                'initiationMethod': detail.get('InitiationMethod'),
                'disconnectReason': detail.get('DisconnectReason')
            }
        except Exception as e:
            print(f"Could not get contact details: {str(e)}")

        messages = []
        transcript_found = False

        # Search for Chat transcript using precise date-based prefix
        chat_key = _find_chat_transcript_key(contact_id, initiation_timestamp)
        if chat_key:
            response = s3_client.get_object(Bucket=TRANSCRIPT_BUCKET, Key=chat_key)
            content = response['Body'].read().decode('utf-8')
            transcript_data = json.loads(content)

            for item in transcript_data.get('Transcript', []):
                if item.get('Type') == 'MESSAGE':
                    messages.append({
                        'id': item.get('Id'),
                        'content': item.get('Content', ''),
                        'timestamp': item.get('AbsoluteTime'),
                        'role': item.get('ParticipantRole'),
                        'displayName': item.get('DisplayName'),
                        'participantId': item.get('ParticipantId')
                    })
            transcript_found = True

        # If no Chat transcript, search for Voice analysis with date-based prefix
        if not transcript_found:
            voice_key = _find_voice_transcript_key(contact_id, initiation_timestamp)
            if voice_key:
                voice_response = s3_client.get_object(Bucket=TRANSCRIPT_BUCKET, Key=voice_key)
                content = voice_response['Body'].read().decode('utf-8')
                voice_data = json.loads(content)

                for item in voice_data.get('Transcript', []):
                    participant_id = item.get('ParticipantId', '')
                    role = 'CUSTOMER' if participant_id == 'CUSTOMER' else 'SYSTEM'
                    messages.append({
                        'id': item.get('Id'),
                        'content': item.get('Content', ''),
                        'timestamp': None,
                        'offsetMs': item.get('BeginOffsetMillis'),
                        'role': role,
                        'displayName': 'Customer' if role == 'CUSTOMER' else 'Bot',
                        'participantId': participant_id,
                        'sentiment': item.get('Sentiment')
                    })
                transcript_found = True

        # Sort voice messages by offset if present
        if messages and messages[0].get('offsetMs') is not None:
            messages.sort(key=lambda x: x.get('offsetMs', 0))

        return {
            'statusCode': 200,
            'headers': cors_headers,
            'body': json.dumps({
                'contactId': contact_id,
                'messages': messages,
                'hasTranscript': transcript_found,
                **contact_info
            })
        }
    except Exception as e:
        print(f"Error getting transcript: {str(e)}")
        return {
            'statusCode': 500,
            'headers': cors_headers,
            'body': json.dumps({'error': str(e)})
        }


def handle_analyze_conversation(contact_id, cors_headers):
    """
    Analyze conversation using Claude model and generate tags
    """
    try:
        # First get the transcript
        transcript_result = get_transcript_messages(contact_id)

        if not transcript_result['found']:
            return {
                'statusCode': 404,
                'headers': cors_headers,
                'body': json.dumps({'error': 'Transcript not found for this contact'})
            }

        messages = transcript_result['messages']

        # If no messages, might be unanswered call
        if not messages:
            # Check disconnect reason to determine tag
            disconnect_reason = transcript_result.get('disconnectReason', '')
            analysis_result = determine_unanswered_tag(disconnect_reason)
        else:
            # Format conversation for analysis
            conversation_text = format_conversation_for_analysis(messages)

            # Call Claude model for analysis
            analysis_result = call_claude_for_analysis(conversation_text)

        # Save analysis result to S3
        save_analysis_result(contact_id, analysis_result)

        return {
            'statusCode': 200,
            'headers': cors_headers,
            'body': json.dumps({
                'contactId': contact_id,
                'analysis': analysis_result,
                'analyzedAt': datetime.utcnow().isoformat()
            })
        }
    except Exception as e:
        print(f"Error analyzing conversation: {str(e)}")
        return {
            'statusCode': 500,
            'headers': cors_headers,
            'body': json.dumps({'error': str(e)})
        }


def handle_get_analysis(contact_id, cors_headers):
    """
    Get existing analysis result for a contact
    """
    try:
        key = f"Analysis/Labels/{contact_id}_labels.json"

        try:
            response = s3_client.get_object(Bucket=TRANSCRIPT_BUCKET, Key=key)
            content = response['Body'].read().decode('utf-8')
            analysis_data = json.loads(content)

            return {
                'statusCode': 200,
                'headers': cors_headers,
                'body': json.dumps({
                    'contactId': contact_id,
                    'analysis': analysis_data,
                    'exists': True
                })
            }
        except s3_client.exceptions.NoSuchKey:
            return {
                'statusCode': 200,
                'headers': cors_headers,
                'body': json.dumps({
                    'contactId': contact_id,
                    'exists': False
                })
            }
    except Exception as e:
        print(f"Error getting analysis: {str(e)}")
        return {
            'statusCode': 500,
            'headers': cors_headers,
            'body': json.dumps({'error': str(e)})
        }


def get_transcript_messages(contact_id):
    """
    Get transcript messages for a contact using precise S3 prefix lookup.
    """
    messages = []
    found = False
    disconnect_reason = None
    initiation_timestamp = None

    # Get contact details first
    try:
        detail = connect_client.describe_contact(
            InstanceId=INSTANCE_ID,
            ContactId=contact_id
        ).get('Contact', {})
        disconnect_reason = detail.get('DisconnectReason')
        initiation_timestamp = detail.get('InitiationTimestamp')
    except:
        pass

    # Search for Chat transcript using precise date-based prefix
    chat_key = _find_chat_transcript_key(contact_id, initiation_timestamp)
    if chat_key:
        response = s3_client.get_object(Bucket=TRANSCRIPT_BUCKET, Key=chat_key)
        content = response['Body'].read().decode('utf-8')
        transcript_data = json.loads(content)

        for item in transcript_data.get('Transcript', []):
            if item.get('Type') == 'MESSAGE':
                messages.append({
                    'role': item.get('ParticipantRole'),
                    'content': item.get('Content', '')
                })
        found = True

    # If no Chat transcript, search for Voice analysis with date-based prefix
    if not found:
        voice_key = _find_voice_transcript_key(contact_id, initiation_timestamp)
        if voice_key:
            voice_response = s3_client.get_object(Bucket=TRANSCRIPT_BUCKET, Key=voice_key)
            content = voice_response['Body'].read().decode('utf-8')
            voice_data = json.loads(content)

            for item in voice_data.get('Transcript', []):
                participant_id = item.get('ParticipantId', '')
                role = 'CUSTOMER' if participant_id == 'CUSTOMER' else 'AGENT'
                messages.append({
                    'role': role,
                    'content': item.get('Content', '')
                })
            found = True

    return {
        'found': found,
        'messages': messages,
        'disconnectReason': disconnect_reason
    }


def format_conversation_for_analysis(messages):
    """
    Format conversation messages for Claude analysis
    """
    lines = []
    for msg in messages:
        role = msg.get('role', 'UNKNOWN')
        content = msg.get('content', '')
        if role in ['CUSTOMER', 'CONTACT']:
            lines.append(f"客户: {content}")
        else:
            lines.append(f"催收员: {content}")
    return '\n'.join(lines)


def determine_unanswered_tag(disconnect_reason):
    """
    Determine tag for unanswered calls based on disconnect reason
    """
    disconnect_reason = disconnect_reason or ''

    # Map disconnect reasons to intention tags
    if 'BUSY' in disconnect_reason or 'NO_ANSWER' in disconnect_reason or 'REJECTED' in disconnect_reason:
        intention_code = 'F'
    elif 'INVALID_NUMBER' in disconnect_reason or 'UNROUTABLE_NUMBER' in disconnect_reason:
        intention_code = 'H'
    elif 'SERVICE_QUOTA_EXCEEDED' in disconnect_reason or 'TELECOM' in disconnect_reason:
        intention_code = 'G'
    else:
        intention_code = 'F'  # Default to F for unknown unanswered reasons

    return {
        'intentionTag': {
            'code': intention_code,
            'label_zh': INTENTION_TAGS[intention_code]['zh'],
            'label_es': INTENTION_TAGS[intention_code]['es']
        },
        'personalityTags': []
    }


def call_claude_for_analysis(conversation_text):
    """
    Call Claude model to analyze conversation
    """
    prompt = f"""你是一个专业的催收对话分析助手。请分析以下催收对话，并输出分析结果。

对话内容：
{conversation_text}

请根据对话内容，选择：

1. 意向标签（只选择一个）：
- A: 已还款
- B: 承诺准时还款
- C: 承诺晚点还款
- D: 未承诺还款
- E: 拒绝还款
- M: 接通后为语音/留言信箱

2. 个性标签（可多选，只选择适用的）：
- complaint: 投诉
- busy: 忙
- self: 是本人
- family_friend: 家人朋友
- wrong_number: 打错电话
- pay_tomorrow: 明天能还
- no_money: 没钱
- difficulty_paying: 还款困难
- borrower_deceased: 借款人去世
- unexpected_change: 遭遇变故
- high_interest: 利息太高
- pressured_willing: 施压后-愿意还款
- informed_willing: 告知还款-愿意还款
- partial_payment: 要求最低还款/部分还款
- request_reduction: 要求减免
- request_extension: 要求展期

请以XML格式返回结果，格式如下：
<analysis>
  <intention_code>B</intention_code>
  <personality_codes>
    <code>self</code>
    <code>pay_tomorrow</code>
  </personality_codes>
</analysis>

只返回XML，不要其他内容。"""

    try:
        response = bedrock_client.invoke_model(
            modelId='global.anthropic.claude-sonnet-4-5-20250929-v1:0',
            contentType='application/json',
            accept='application/json',
            body=json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 1024,
                "messages": [
                    {"role": "user", "content": prompt}
                ]
            })
        )

        response_body = json.loads(response['body'].read().decode('utf-8'))
        result_text = response_body.get('content', [{}])[0].get('text', '{}')

        print(f"Claude response text: {result_text}")

        # Extract intention code using regex
        intention_match = re.search(r'<intention_code>([A-HM])</intention_code>', result_text)
        intention_code = intention_match.group(1) if intention_match else 'D'

        # Extract personality codes using regex
        personality_codes = []
        personality_matches = re.findall(r'<code>(\w+)</code>', result_text)
        if personality_matches:
            personality_codes = personality_matches

        # Build formatted result
        analysis_result = {
            'intentionTag': {
                'code': intention_code,
                'label_zh': INTENTION_TAGS.get(intention_code, {}).get('zh', '未知'),
                'label_es': INTENTION_TAGS.get(intention_code, {}).get('es', 'Unknown')
            },
            'personalityTags': []
        }

        for code in personality_codes:
            if code in PERSONALITY_TAGS:
                analysis_result['personalityTags'].append({
                    'code': code,
                    'label_zh': PERSONALITY_TAGS[code]['zh'],
                    'label_es': PERSONALITY_TAGS[code]['es']
                })

        return analysis_result

    except Exception as e:
        print(f"Error calling Claude: {str(e)}")
        # Return default result on error
        return {
            'intentionTag': {
                'code': 'D',
                'label_zh': INTENTION_TAGS['D']['zh'],
                'label_es': INTENTION_TAGS['D']['es']
            },
            'personalityTags': [],
            'error': str(e)
        }


def save_analysis_result(contact_id, analysis_result):
    """
    Save analysis result to S3
    """
    key = f"Analysis/Labels/{contact_id}_labels.json"

    data = {
        'contactId': contact_id,
        'analyzedAt': datetime.utcnow().isoformat(),
        **analysis_result
    }

    s3_client.put_object(
        Bucket=TRANSCRIPT_BUCKET,
        Key=key,
        Body=json.dumps(data, ensure_ascii=False),
        ContentType='application/json'
    )

# Import customer management functions
from customer_functions import (
    handle_import_customers,
    handle_list_customers,
    handle_get_customer,
    handle_update_customer,
    handle_delete_customer,
    handle_single_call,
    handle_batch_call
)

# Import flow configuration functions
from flow_config_functions import (
    handle_create_flow,
    handle_list_flows,
    handle_get_flow,
    handle_update_flow,
    handle_delete_flow
)
