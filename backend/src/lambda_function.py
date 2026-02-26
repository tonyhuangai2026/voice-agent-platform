import json
import boto3
import csv
import os
from io import StringIO

# Initialize AWS clients
s3_client = boto3.client('s3')
connect = boto3.client('connect')

# Environment variables configuration
CONTACT_FLOW_ID = os.environ.get('CONTACT_FLOW_ID', 'ccd673d3-3d38-4235-9818-e1b65c1d7225') 
INSTANCE_ID = os.environ.get('INSTANCE_ID', 'a60dd182-7f8f-495b-945e-43420832f01c')
QUEUE_ID = os.environ.get('QUEUE_ID', '1eced15c-4c63-42d7-8faf-13c4cf28455a')


def lambda_handler(event, context):
    """
    Lambda function entry point, handles S3 upload events
    """
    try:
        contact_ids = []
        
        # Parse S3 event
        for record in event['Records']:
            bucket_name = record['s3']['bucket']['name']
            object_key = record['s3']['object']['key']
            
            print(f"Processing file: s3://{bucket_name}/{object_key}")
            
            # Read customer list from S3 CSV file
            customers = read_customer_list_from_s3(bucket_name, object_key)
            
            if not customers:
                print("No valid customer data found")
                continue
            
            # Start outbound voice contact for each customer
            for customer in customers:
                phone_number = customer.get('phone_number', '').strip()
                customer_name = customer.get('customer_name', '')
                debt_amount = customer.get('debt_amount', '0')
                
                if not phone_number:
                    print(f"Skipping customer {customer_name}: no phone number")
                    continue
                
                try:
                    response = connect.start_outbound_voice_contact(
                        DestinationPhoneNumber=phone_number,
                        ContactFlowId=CONTACT_FLOW_ID,
                        InstanceId=INSTANCE_ID,
                        QueueId=QUEUE_ID,
                        Attributes={
                            'CustomerName': customer_name,
                            'DebtAmount': debt_amount
                        }
                    )
                    
                    contact_id = response.get('ContactId')
                    contact_ids.append(contact_id)
                    print(f"Call initiated for {customer_name} ({phone_number}): ContactId={contact_id}")
                    
                except Exception as call_error:
                    print(f"Failed to initiate call for {customer_name} ({phone_number}): {str(call_error)}")
                    continue
            
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'Successfully processed S3 event',
                'totalCalls': len(contact_ids),
                'contactIds': contact_ids
            })
        }
        
    except Exception as e:
        print(f"Error: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({
                'message': 'Error processing request',
                'error': str(e)
            })
        }


def read_customer_list_from_s3(bucket_name, object_key):
    """
    Read customer list CSV file from S3
    """
    try:
        # Download file
        response = s3_client.get_object(Bucket=bucket_name, Key=object_key)
        content = response['Body'].read().decode('utf-8')
        
        # Parse CSV
        csv_reader = csv.DictReader(StringIO(content))
        customers = []
        
        for row in csv_reader:
            customer = {
                'customer_name': row.get('customer_name', ''),
                'phone_number': row.get('phone_number', ''),
                'debt_amount': row.get('debt_amount', '0')
            }
            customers.append(customer)
        
        print(f"Successfully read {len(customers)} customer records")
        return customers
        
    except Exception as e:
        print(f"Failed to read S3 file: {str(e)}")
        raise e
