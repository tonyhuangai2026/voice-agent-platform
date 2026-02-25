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
    handle_list_call_records, handle_get_call_record,
    handle_get_ecs_status, handle_get_active_calls_summary
)

# Initialize AWS clients
s3_client = boto3.client('s3', config=Config(signature_version='s3v4'))
connect_client = boto3.client('connect', region_name='us-west-2')
bedrock_client = boto3.client('bedrock-runtime', region_name='us-west-2')
dynamodb = boto3.resource('dynamodb', region_name='us-west-2')
customers_table = dynamodb.Table(os.environ.get('CUSTOMERS_TABLE', 'outbound-customers'))

# Label definitions
OUTCOME_TAGS = {
    'A': {'label': 'Already paid'},
    'B': {'label': 'Promised to pay on time'},
    'C': {'label': 'Promised to pay later'},
    'D': {'label': 'No commitment to pay'},
    'E': {'label': 'Refused to pay'},
    'M': {'label': 'Voicemail / answering machine'},
    'F': {'label': 'Not connected (busy/missed/rejected/off/unreachable)'},
    'G': {'label': 'Not connected (overdue account/line fault/call failed/number changed)'},
    'H': {'label': 'Not connected (blacklisted/blocked/invalid number/suspended)'}
}

BEHAVIOR_TAGS = {
    'complaint': {'label': 'Complaint'},
    'busy': {'label': 'Busy'},
    'self': {'label': 'Confirmed identity'},
    'family_friend': {'label': 'Family or friend'},
    'wrong_number': {'label': 'Wrong number'},
    'pay_tomorrow': {'label': 'Can pay tomorrow'},
    'no_money': {'label': 'No money'},
    'difficulty_paying': {'label': 'Difficulty paying'},
    'borrower_deceased': {'label': 'Borrower deceased'},
    'unexpected_change': {'label': 'Unexpected change in circumstances'},
    'high_interest': {'label': 'High interest complaint'},
    'pressured_willing': {'label': 'Willing to pay after pressure'},
    'informed_willing': {'label': 'Willing to pay after informed'},
    'partial_payment': {'label': 'Requesting minimum/partial payment'},
    'request_reduction': {'label': 'Requesting reduction'},
    'request_extension': {'label': 'Requesting extension'}
}

# Environment variables
INSTANCE_ID = os.environ.get('INSTANCE_ID', '')
VOICE_ANALYSIS_PREFIX = os.environ.get('VOICE_ANALYSIS_PREFIX', 'Analysis/Voice/ivr/')


def _resolve_connect_storage():
    """
    Resolve TRANSCRIPT_BUCKET and TRANSCRIPT_PREFIX from Connect Instance
    Storage Config API. Falls back to environment variables if the API call fails.
    """
    bucket = os.environ.get('TRANSCRIPT_BUCKET')
    prefix = os.environ.get('TRANSCRIPT_PREFIX')

    if bucket and prefix:
        return bucket, prefix

    try:
        resp = connect_client.list_instance_storage_configs(
            InstanceId=INSTANCE_ID,
            ResourceType='CHAT_TRANSCRIPTS'
        )
        configs = resp.get('StorageConfigs', [])
        if configs:
            s3_config = configs[0].get('S3Config', {})
            bucket = bucket or s3_config.get('BucketName')
            prefix = prefix or (s3_config.get('BucketPrefix', '') + '/')
            print(f"Resolved from Connect API: bucket={bucket}, prefix={prefix}")
    except Exception as e:
        print(f"Failed to resolve storage config from Connect API: {e}")

    return bucket or 'outbound-transcripts', prefix or 'connect/default/ChatTranscripts/'


TRANSCRIPT_BUCKET, TRANSCRIPT_PREFIX = _resolve_connect_storage()

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
    API Gateway Lambda handler for outbound management platform
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
        # Route handling
        if path == '/api/records' and http_method == 'GET':
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
        elif path == '/api/monitor/ecs-status' and http_method == 'GET':
            return handle_get_ecs_status(cors_headers)
        elif path == '/api/monitor/active-calls' and http_method == 'GET':
            return handle_get_active_calls_summary(cors_headers)
        elif path == '/api/call-records' and http_method == 'GET':
            return handle_list_call_records(event, cors_headers)
        elif path.startswith('/api/call-records/') and http_method == 'GET':
            call_sid = path.split('/')[-1]
            return handle_get_call_record(call_sid, cors_headers)
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
        limit = int(query_params.get('limit', '20'))
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
        channel = query_params.get('channel', 'VOICE')
        days = int(query_params.get('days', '7'))

        end_time = datetime.utcnow()
        start_time = end_time - timedelta(days=days)

        time_range = {
            'Type': 'INITIATION_TIMESTAMP',
            'StartTime': start_time,
            'EndTime': end_time
        }
        raw_contacts = search_contacts_paginated(limit, time_range)

        contacts = []
        for contact in raw_contacts:
            contact_id = contact.get('Id')

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

        end_time = datetime.utcnow()
        start_time = end_time - timedelta(days=days)

        time_range = {
            'Type': 'INITIATION_TIMESTAMP',
            'StartTime': start_time,
            'EndTime': end_time
        }

        try:
            contacts = search_contacts_paginated(limit, time_range, search_criteria={'Channels': ['CHAT']})
        except Exception as e:
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

        contact_details = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            results = executor.map(get_contact_detail, contact_ids)
            for detail in results:
                contact_details[detail['contactId']] = detail

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
        transcript_result = get_transcript_messages(contact_id)

        if not transcript_result['found']:
            return {
                'statusCode': 404,
                'headers': cors_headers,
                'body': json.dumps({'error': 'Transcript not found for this contact'})
            }

        messages = transcript_result['messages']

        if not messages:
            disconnect_reason = transcript_result.get('disconnectReason', '')
            analysis_result = determine_unanswered_tag(disconnect_reason)
        else:
            conversation_text = format_conversation_for_analysis(messages)
            analysis_result = call_claude_for_analysis(conversation_text)

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

    try:
        detail = connect_client.describe_contact(
            InstanceId=INSTANCE_ID,
            ContactId=contact_id
        ).get('Contact', {})
        disconnect_reason = detail.get('DisconnectReason')
        initiation_timestamp = detail.get('InitiationTimestamp')
    except:
        pass

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
            lines.append(f"Customer: {content}")
        else:
            lines.append(f"Agent: {content}")
    return '\n'.join(lines)


def determine_unanswered_tag(disconnect_reason):
    """
    Determine tag for unanswered calls based on disconnect reason
    """
    disconnect_reason = disconnect_reason or ''

    if 'BUSY' in disconnect_reason or 'NO_ANSWER' in disconnect_reason or 'REJECTED' in disconnect_reason:
        outcome_code = 'F'
    elif 'INVALID_NUMBER' in disconnect_reason or 'UNROUTABLE_NUMBER' in disconnect_reason:
        outcome_code = 'H'
    elif 'SERVICE_QUOTA_EXCEEDED' in disconnect_reason or 'TELECOM' in disconnect_reason:
        outcome_code = 'G'
    else:
        outcome_code = 'F'

    return {
        'outcomeTag': {
            'code': outcome_code,
            'label': OUTCOME_TAGS[outcome_code]['label']
        },
        'behaviorTags': []
    }


def call_claude_for_analysis(conversation_text):
    """
    Call Claude model to analyze conversation
    """
    prompt = f"""You are a professional outbound call conversation analyst. Analyze the following conversation and output the analysis result.

Conversation:
{conversation_text}

Based on the conversation content, select:

1. Outcome tag (select only one):
- A: Already paid
- B: Promised to pay on time
- C: Promised to pay later
- D: No commitment to pay
- E: Refused to pay
- M: Voicemail / answering machine

2. Behavior tags (select all that apply):
- complaint: Complaint
- busy: Busy
- self: Confirmed identity
- family_friend: Family or friend
- wrong_number: Wrong number
- pay_tomorrow: Can pay tomorrow
- no_money: No money
- difficulty_paying: Difficulty paying
- borrower_deceased: Borrower deceased
- unexpected_change: Unexpected change in circumstances
- high_interest: High interest complaint
- pressured_willing: Willing to pay after pressure
- informed_willing: Willing to pay after informed
- partial_payment: Requesting minimum/partial payment
- request_reduction: Requesting reduction
- request_extension: Requesting extension

Return the result in XML format as follows:
<analysis>
  <outcome_code>B</outcome_code>
  <behavior_codes>
    <code>self</code>
    <code>pay_tomorrow</code>
  </behavior_codes>
</analysis>

Return only the XML, nothing else."""

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

        outcome_match = re.search(r'<outcome_code>([A-HM])</outcome_code>', result_text)
        outcome_code = outcome_match.group(1) if outcome_match else 'D'

        behavior_codes = []
        behavior_matches = re.findall(r'<code>(\w+)</code>', result_text)
        if behavior_matches:
            behavior_codes = behavior_matches

        analysis_result = {
            'outcomeTag': {
                'code': outcome_code,
                'label': OUTCOME_TAGS.get(outcome_code, {}).get('label', 'Unknown')
            },
            'behaviorTags': []
        }

        for code in behavior_codes:
            if code in BEHAVIOR_TAGS:
                analysis_result['behaviorTags'].append({
                    'code': code,
                    'label': BEHAVIOR_TAGS[code]['label']
                })

        return analysis_result

    except Exception as e:
        print(f"Error calling Claude: {str(e)}")
        return {
            'outcomeTag': {
                'code': 'D',
                'label': OUTCOME_TAGS['D']['label']
            },
            'behaviorTags': [],
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
