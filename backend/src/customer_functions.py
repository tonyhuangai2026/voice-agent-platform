"""
Customer management and call functions for DynamoDB
"""
import json
import os
import uuid
import csv
from datetime import datetime
from io import StringIO
from decimal import Decimal
import boto3
from flow_config_functions import get_flow_config

DYNAMODB_REGION = os.environ.get('DYNAMODB_REGION', 'us-east-1')
CONNECT_REGION = os.environ.get('CONNECT_REGION', 'us-west-2')

dynamodb = boto3.resource('dynamodb', region_name=DYNAMODB_REGION)
customers_table = dynamodb.Table(os.environ.get('CUSTOMERS_TABLE', 'outbound-customers'))
call_records_table = dynamodb.Table(os.environ.get('CALL_RECORDS_TABLE', 'outbound-call-records'))
connect_client = boto3.client('connect', region_name=CONNECT_REGION)


def handle_import_customers(event, cors_headers):
    """
    Import customers from CSV data with deduplication
    """
    try:
        body = json.loads(event.get('body', '{}'))
        csv_content = body.get('csv_content', '')
        default_project_id = body.get('project_id')  # Project ID from request body

        if not csv_content:
            return {
                'statusCode': 400,
                'headers': cors_headers,
                'body': json.dumps({'error': 'No CSV content provided'})
            }

        # Parse CSV
        csv_reader = csv.DictReader(StringIO(csv_content))

        imported_count = 0
        skipped_count = 0
        updated_count = 0

        for row in csv_reader:
            customer_name = row.get('customer_name', '').strip()
            phone_number = row.get('phone_number', '').strip()
            email = row.get('email', '').strip()
            debt_amount = row.get('debt_amount', '0').strip()
            voice_id = row.get('voice_id', '').strip()
            prompt_id = row.get('prompt_id', '').strip()
            notes = row.get('notes', '').strip()
            project_id = row.get('project_id', '').strip() or default_project_id

            if not phone_number:
                skipped_count += 1
                continue

            # Check if customer exists (by phone number)
            existing = customers_table.query(
                IndexName='phone-index',
                KeyConditionExpression='phone_number = :phone',
                ExpressionAttributeValues={':phone': phone_number}
            )

            if existing['Items']:
                # Update existing customer
                customer_id = existing['Items'][0]['customer_id']
                update_expr = 'SET customer_name = :name, debt_amount = :debt, updated_at = :updated'
                expr_values = {
                    ':name': customer_name,
                    ':debt': Decimal(str(debt_amount)),
                    ':updated': datetime.utcnow().isoformat()
                }

                if email:
                    update_expr += ', email = :email'
                    expr_values[':email'] = email
                if voice_id:
                    update_expr += ', voice_id = :voice'
                    expr_values[':voice'] = voice_id
                if prompt_id:
                    update_expr += ', prompt_id = :prompt'
                    expr_values[':prompt'] = prompt_id
                if notes:
                    update_expr += ', notes = :notes'
                    expr_values[':notes'] = notes
                if project_id:
                    update_expr += ', project_id = :project'
                    expr_values[':project'] = project_id

                customers_table.update_item(
                    Key={'customer_id': customer_id},
                    UpdateExpression=update_expr,
                    ExpressionAttributeValues=expr_values
                )
                updated_count += 1
            else:
                # Create new customer
                customer_id = str(uuid.uuid4())
                item = {
                    'customer_id': customer_id,
                    'customer_name': customer_name,
                    'phone_number': phone_number,
                    'debt_amount': Decimal(str(debt_amount)),
                    'status': 'pending',
                    'call_count': 0,
                    'notes': notes if notes else '',
                    'created_at': datetime.utcnow().isoformat(),
                    'updated_at': datetime.utcnow().isoformat()
                }
                if email:
                    item['email'] = email
                if voice_id:
                    item['voice_id'] = voice_id
                if prompt_id:
                    item['prompt_id'] = prompt_id
                if project_id:
                    item['project_id'] = project_id

                customers_table.put_item(Item=item)
                imported_count += 1

        return {
            'statusCode': 200,
            'headers': cors_headers,
            'body': json.dumps({
                'imported': imported_count,
                'updated': updated_count,
                'skipped': skipped_count
            })
        }

    except Exception as e:
        print(f"Error importing customers: {str(e)}")
        return {
            'statusCode': 500,
            'headers': cors_headers,
            'body': json.dumps({'error': str(e)})
        }


def handle_list_customers(event, cors_headers):
    """
    List customers with filtering
    """
    try:
        query_params = event.get('queryStringParameters') or {}
        status_filter = query_params.get('status')
        project_id = query_params.get('project_id')
        limit = int(query_params.get('limit', '100'))

        # Scan table
        scan_kwargs = {'Limit': limit}
        filter_expressions = []
        expr_values = {}

        if status_filter:
            filter_expressions.append('status = :status')
            expr_values[':status'] = status_filter

        if project_id:
            filter_expressions.append('project_id = :project_id')
            expr_values[':project_id'] = project_id

        if filter_expressions:
            scan_kwargs['FilterExpression'] = ' AND '.join(filter_expressions)
            scan_kwargs['ExpressionAttributeValues'] = expr_values

        response = customers_table.scan(**scan_kwargs)

        # Convert Decimal to float for JSON serialization
        items = []
        for item in response['Items']:
            item_dict = {
                'customer_id': item['customer_id'],
                'project_id': item.get('project_id', ''),
                'customer_name': item.get('customer_name', ''),
                'phone_number': item.get('phone_number', ''),
                'email': item.get('email', ''),
                'debt_amount': float(item.get('debt_amount', 0)),
                'status': item.get('status', 'pending'),
                'call_count': int(item.get('call_count', 0)),
                'last_call_time': item.get('last_call_time'),
                'notes': item.get('notes', ''),
                'voice_id': item.get('voice_id', ''),
                'prompt_id': item.get('prompt_id', ''),
                'created_at': item.get('created_at'),
                'updated_at': item.get('updated_at')
            }

            # Fetch latest call record labels for this customer
            try:
                phone_number = item.get('phone_number', '')
                if phone_number:
                    # Query call records for this customer's phone number
                    # Note: Don't use Limit in scan - it limits before filtering/sorting
                    call_response = call_records_table.scan(
                        FilterExpression='customerPhone = :phone',
                        ExpressionAttributeValues={':phone': phone_number}
                    )

                    # Get the most recent call with labels
                    call_items = call_response.get('Items', [])
                    if call_items:
                        # Sort by startTime descending to get the most recent
                        call_items.sort(key=lambda x: x.get('startTime', ''), reverse=True)
                        latest_call = call_items[0]
                        item_dict['latest_call_labels'] = latest_call.get('labels', {})
                    else:
                        item_dict['latest_call_labels'] = {}
                else:
                    item_dict['latest_call_labels'] = {}
            except Exception as e:
                print(f"Error fetching call labels for customer {item['customer_id']}: {str(e)}")
                item_dict['latest_call_labels'] = {}

            items.append(item_dict)

        # Sort by created_at descending
        items.sort(key=lambda x: x.get('created_at', ''), reverse=True)

        return {
            'statusCode': 200,
            'headers': cors_headers,
            'body': json.dumps({
                'customers': items,
                'count': len(items)
            })
        }

    except Exception as e:
        print(f"Error listing customers: {str(e)}")
        return {
            'statusCode': 500,
            'headers': cors_headers,
            'body': json.dumps({'error': str(e)})
        }


def handle_get_customer(customer_id, cors_headers):
    """
    Get single customer details
    """
    try:
        response = customers_table.get_item(Key={'customer_id': customer_id})

        if 'Item' not in response:
            return {
                'statusCode': 404,
                'headers': cors_headers,
                'body': json.dumps({'error': 'Customer not found'})
            }

        item = response['Item']
        customer = {
            'customer_id': item['customer_id'],
            'customer_name': item.get('customer_name', ''),
            'phone_number': item.get('phone_number', ''),
            'debt_amount': float(item.get('debt_amount', 0)),
            'status': item.get('status', 'pending'),
            'call_count': int(item.get('call_count', 0)),
            'last_call_time': item.get('last_call_time'),
            'notes': item.get('notes', ''),
            'voice_id': item.get('voice_id', ''),
            'system_prompt': item.get('system_prompt', ''),
            'created_at': item.get('created_at'),
            'updated_at': item.get('updated_at')
        }

        return {
            'statusCode': 200,
            'headers': cors_headers,
            'body': json.dumps(customer)
        }

    except Exception as e:
        print(f"Error getting customer: {str(e)}")
        return {
            'statusCode': 500,
            'headers': cors_headers,
            'body': json.dumps({'error': str(e)})
        }


def handle_update_customer(customer_id, event, cors_headers):
    """
    Update customer information
    """
    try:
        body = json.loads(event.get('body', '{}'))

        update_expr = []
        expr_values = {}
        expr_names = {}

        if 'customer_name' in body:
            update_expr.append('#name = :name')
            expr_values[':name'] = body['customer_name']
            expr_names['#name'] = 'customer_name'

        if 'phone_number' in body:
            update_expr.append('phone_number = :phone')
            expr_values[':phone'] = body['phone_number']

        if 'debt_amount' in body:
            update_expr.append('debt_amount = :debt')
            expr_values[':debt'] = Decimal(str(body['debt_amount']))

        if 'email' in body:
            update_expr.append('email = :email')
            expr_values[':email'] = body['email']

        if 'notes' in body:
            update_expr.append('notes = :notes')
            expr_values[':notes'] = body['notes']

        if 'status' in body:
            update_expr.append('#status = :status')
            expr_values[':status'] = body['status']
            expr_names['#status'] = 'status'

        if 'voice_id' in body:
            update_expr.append('voice_id = :voice')
            expr_values[':voice'] = body['voice_id']

        if 'prompt_id' in body:
            update_expr.append('prompt_id = :prompt')
            expr_values[':prompt'] = body['prompt_id']

        update_expr.append('updated_at = :updated')
        expr_values[':updated'] = datetime.utcnow().isoformat()

        if not update_expr:
            return {
                'statusCode': 400,
                'headers': cors_headers,
                'body': json.dumps({'error': 'No fields to update'})
            }

        update_kwargs = {
            'Key': {'customer_id': customer_id},
            'UpdateExpression': 'SET ' + ', '.join(update_expr),
            'ExpressionAttributeValues': expr_values,
            'ReturnValues': 'ALL_NEW'
        }

        if expr_names:
            update_kwargs['ExpressionAttributeNames'] = expr_names

        response = customers_table.update_item(**update_kwargs)

        item = response['Attributes']
        customer = {
            'customer_id': item['customer_id'],
            'customer_name': item.get('customer_name', ''),
            'phone_number': item.get('phone_number', ''),
            'debt_amount': float(item.get('debt_amount', 0)),
            'status': item.get('status', 'pending'),
            'call_count': int(item.get('call_count', 0)),
            'last_call_time': item.get('last_call_time'),
            'notes': item.get('notes', ''),
            'voice_id': item.get('voice_id', ''),
            'system_prompt': item.get('system_prompt', ''),
            'updated_at': item.get('updated_at')
        }

        return {
            'statusCode': 200,
            'headers': cors_headers,
            'body': json.dumps(customer)
        }

    except Exception as e:
        print(f"Error updating customer: {str(e)}")
        return {
            'statusCode': 500,
            'headers': cors_headers,
            'body': json.dumps({'error': str(e)})
        }


def handle_delete_customer(customer_id, cors_headers):
    """
    Delete customer
    """
    try:
        customers_table.delete_item(Key={'customer_id': customer_id})

        return {
            'statusCode': 200,
            'headers': cors_headers,
            'body': json.dumps({'message': 'Customer deleted'})
        }

    except Exception as e:
        print(f"Error deleting customer: {str(e)}")
        return {
            'statusCode': 500,
            'headers': cors_headers,
            'body': json.dumps({'error': str(e)})
        }


def handle_single_call(customer_id, event, cors_headers):
    """
    Make a single outbound call to customer with specified flow
    """
    try:
        # Get flow_id from request body
        body = json.loads(event.get('body', '{}'))
        flow_id = body.get('flow_id')

        if not flow_id:
            return {
                'statusCode': 400,
                'headers': cors_headers,
                'body': json.dumps({'error': 'flow_id is required'})
            }

        # Get flow configuration
        try:
            flow_config = get_flow_config(flow_id)
        except Exception as e:
            return {
                'statusCode': 400,
                'headers': cors_headers,
                'body': json.dumps({'error': f'Invalid flow: {str(e)}'})
            }

        # Get customer details
        response = customers_table.get_item(Key={'customer_id': customer_id})

        if 'Item' not in response:
            return {
                'statusCode': 404,
                'headers': cors_headers,
                'body': json.dumps({'error': 'Customer not found'})
            }

        customer = response['Item']
        phone_number = customer.get('phone_number', '')
        customer_name = customer.get('customer_name', '')
        debt_amount = str(customer.get('debt_amount', 0))

        if not phone_number:
            return {
                'statusCode': 400,
                'headers': cors_headers,
                'body': json.dumps({'error': 'Customer has no phone number'})
            }

        # Update status to calling
        customers_table.update_item(
            Key={'customer_id': customer_id},
            UpdateExpression='SET #status = :status',
            ExpressionAttributeNames={'#status': 'status'},
            ExpressionAttributeValues={':status': 'calling'}
        )

        # Initiate call with flow configuration
        try:
            call_response = connect_client.start_outbound_voice_contact(
                DestinationPhoneNumber=phone_number,
                ContactFlowId=flow_config['contact_flow_id'],
                InstanceId=flow_config['instance_id'],
                QueueId=flow_config['queue_id'],
                Attributes={
                    'CustomerName': customer_name,
                    'DebtAmount': debt_amount,
                    'CustomerId': customer_id
                }
            )

            contact_id = call_response.get('ContactId')

            # Update customer with call info
            customers_table.update_item(
                Key={'customer_id': customer_id},
                UpdateExpression='SET #status = :status, call_count = call_count + :inc, last_call_time = :time, last_contact_id = :contact_id',
                ExpressionAttributeNames={'#status': 'status'},
                ExpressionAttributeValues={
                    ':status': 'called',
                    ':inc': 1,
                    ':time': datetime.utcnow().isoformat(),
                    ':contact_id': contact_id
                }
            )

            return {
                'statusCode': 200,
                'headers': cors_headers,
                'body': json.dumps({
                    'message': 'Call initiated',
                    'contact_id': contact_id,
                    'customer_id': customer_id
                })
            }

        except Exception as call_error:
            # Update status to failed
            customers_table.update_item(
                Key={'customer_id': customer_id},
                UpdateExpression='SET #status = :status',
                ExpressionAttributeNames={'#status': 'status'},
                ExpressionAttributeValues={':status': 'failed'}
            )

            raise call_error

    except Exception as e:
        print(f"Error making call: {str(e)}")
        return {
            'statusCode': 500,
            'headers': cors_headers,
            'body': json.dumps({'error': str(e)})
        }


def handle_batch_call(event, cors_headers):
    """
    Make batch outbound calls with specified flow
    """
    try:
        body = json.loads(event.get('body', '{}'))
        customer_ids = body.get('customer_ids', [])
        flow_id = body.get('flow_id')

        if not customer_ids:
            return {
                'statusCode': 400,
                'headers': cors_headers,
                'body': json.dumps({'error': 'No customer IDs provided'})
            }

        if not flow_id:
            return {
                'statusCode': 400,
                'headers': cors_headers,
                'body': json.dumps({'error': 'flow_id is required'})
            }

        # Get flow configuration
        try:
            flow_config = get_flow_config(flow_id)
        except Exception as e:
            return {
                'statusCode': 400,
                'headers': cors_headers,
                'body': json.dumps({'error': f'Invalid flow: {str(e)}'})
            }

        results = {
            'success': [],
            'failed': []
        }

        for customer_id in customer_ids:
            try:
                # Get customer
                response = customers_table.get_item(Key={'customer_id': customer_id})

                if 'Item' not in response:
                    results['failed'].append({
                        'customer_id': customer_id,
                        'error': 'Customer not found'
                    })
                    continue

                customer = response['Item']
                phone_number = customer.get('phone_number', '')
                customer_name = customer.get('customer_name', '')
                debt_amount = str(customer.get('debt_amount', 0))

                if not phone_number:
                    results['failed'].append({
                        'customer_id': customer_id,
                        'error': 'No phone number'
                    })
                    continue

                # Update status
                customers_table.update_item(
                    Key={'customer_id': customer_id},
                    UpdateExpression='SET #status = :status',
                    ExpressionAttributeNames={'#status': 'status'},
                    ExpressionAttributeValues={':status': 'calling'}
                )

                # Initiate call with flow configuration
                call_response = connect_client.start_outbound_voice_contact(
                    DestinationPhoneNumber=phone_number,
                    ContactFlowId=flow_config['contact_flow_id'],
                    InstanceId=flow_config['instance_id'],
                    QueueId=flow_config['queue_id'],
                    Attributes={
                        'CustomerName': customer_name,
                        'DebtAmount': debt_amount,
                        'CustomerId': customer_id
                    }
                )

                contact_id = call_response.get('ContactId')

                # Update customer
                customers_table.update_item(
                    Key={'customer_id': customer_id},
                    UpdateExpression='SET #status = :status, call_count = call_count + :inc, last_call_time = :time, last_contact_id = :contact_id',
                    ExpressionAttributeNames={'#status': 'status'},
                    ExpressionAttributeValues={
                        ':status': 'called',
                        ':inc': 1,
                        ':time': datetime.utcnow().isoformat(),
                        ':contact_id': contact_id
                    }
                )

                results['success'].append({
                    'customer_id': customer_id,
                    'contact_id': contact_id
                })

            except Exception as call_error:
                # Update status to failed
                try:
                    customers_table.update_item(
                        Key={'customer_id': customer_id},
                        UpdateExpression='SET #status = :status',
                        ExpressionAttributeNames={'#status': 'status'},
                        ExpressionAttributeValues={':status': 'failed'}
                    )
                except:
                    pass

                results['failed'].append({
                    'customer_id': customer_id,
                    'error': str(call_error)
                })

        return {
            'statusCode': 200,
            'headers': cors_headers,
            'body': json.dumps({
                'success_count': len(results['success']),
                'failed_count': len(results['failed']),
                'results': results
            })
        }

    except Exception as e:
        print(f"Error in batch call: {str(e)}")
        return {
            'statusCode': 500,
            'headers': cors_headers,
            'body': json.dumps({'error': str(e)})
        }
