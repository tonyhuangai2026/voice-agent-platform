import json
import boto3
import os
import hashlib
import hmac
import base64
from datetime import datetime, timedelta
import uuid

dynamodb = boto3.resource('dynamodb', region_name=os.environ.get('DYNAMODB_REGION', 'us-east-1'))
users_table = dynamodb.Table(os.environ.get('USERS_TABLE', 'outbound-users'))

# JWT secret from environment variable (MUST be set in production)
JWT_SECRET = os.environ.get('JWT_SECRET', '')
if not JWT_SECRET:
    raise ValueError('JWT_SECRET environment variable must be set')

# Invite code from environment variable (MUST be set for registration to work)
INVITE_CODE = os.environ.get('INVITE_CODE', '')
if not INVITE_CODE:
    print('WARNING: INVITE_CODE not set - user registration will not work')


def hash_password(password: str) -> str:
    """Hash password using SHA256"""
    return hashlib.sha256(password.encode()).hexdigest()


def verify_password(password: str, hashed: str) -> bool:
    """Verify password against hash"""
    return hash_password(password) == hashed


def create_jwt_token(user_id: str, email: str) -> str:
    """Create a simple JWT-like token"""
    expiry = datetime.utcnow() + timedelta(days=7)
    payload = {
        'user_id': user_id,
        'email': email,
        'exp': expiry.isoformat()
    }
    payload_json = json.dumps(payload, separators=(',', ':'))

    # Create signature
    signature = hmac.new(
        JWT_SECRET.encode(),
        payload_json.encode(),
        hashlib.sha256
    ).hexdigest()

    # Combine payload and signature
    token = base64.b64encode(payload_json.encode()).decode() + '.' + signature
    return token


def verify_jwt_token(token: str) -> dict:
    """Verify and decode JWT token"""
    try:
        parts = token.split('.')
        if len(parts) != 2:
            return None

        payload_b64, signature = parts
        payload_json = base64.b64decode(payload_b64).decode()

        # Verify signature
        expected_signature = hmac.new(
            JWT_SECRET.encode(),
            payload_json.encode(),
            hashlib.sha256
        ).hexdigest()

        if signature != expected_signature:
            return None

        payload = json.loads(payload_json)

        # Check expiry
        expiry = datetime.fromisoformat(payload['exp'])
        if datetime.utcnow() > expiry:
            return None

        return payload
    except Exception as e:
        print(f"Token verification error: {str(e)}")
        return None


def handle_register(event, cors_headers):
    """
    POST /api/auth/register
    Register new user with invite code
    """
    try:
        body = json.loads(event.get('body', '{}'))
        email = body.get('email', '').strip().lower()
        password = body.get('password', '')
        invite_code = body.get('invite_code', '').strip()
        name = body.get('name', '').strip()

        # Validation
        if not email or not password or not invite_code or not name:
            return {
                'statusCode': 400,
                'headers': cors_headers,
                'body': json.dumps({'error': 'Email, password, name, and invite code are required'})
            }

        if '@' not in email:
            return {
                'statusCode': 400,
                'headers': cors_headers,
                'body': json.dumps({'error': 'Invalid email format'})
            }

        if len(password) < 6:
            return {
                'statusCode': 400,
                'headers': cors_headers,
                'body': json.dumps({'error': 'Password must be at least 6 characters'})
            }

        # Verify invite code
        if invite_code != INVITE_CODE:
            return {
                'statusCode': 403,
                'headers': cors_headers,
                'body': json.dumps({'error': 'Invalid invite code'})
            }

        # Check if user already exists
        try:
            response = users_table.get_item(Key={'email': email})
            if 'Item' in response:
                return {
                    'statusCode': 409,
                    'headers': cors_headers,
                    'body': json.dumps({'error': 'User already exists'})
                }
        except Exception as e:
            print(f"Error checking existing user: {str(e)}")

        # Create user
        user_id = str(uuid.uuid4())
        hashed_password = hash_password(password)

        users_table.put_item(Item={
            'email': email,
            'user_id': user_id,
            'name': name,
            'password': hashed_password,
            'created_at': datetime.utcnow().isoformat(),
            'last_login': None
        })

        # Generate token
        token = create_jwt_token(user_id, email)

        return {
            'statusCode': 201,
            'headers': cors_headers,
            'body': json.dumps({
                'message': 'User registered successfully',
                'token': token,
                'user': {
                    'user_id': user_id,
                    'email': email,
                    'name': name
                }
            })
        }

    except Exception as e:
        print(f"Registration error: {str(e)}")
        import traceback
        traceback.print_exc()
        return {
            'statusCode': 500,
            'headers': cors_headers,
            'body': json.dumps({'error': f'Registration failed: {str(e)}'})
        }


def handle_login(event, cors_headers):
    """
    POST /api/auth/login
    User login
    """
    try:
        body = json.loads(event.get('body', '{}'))
        email = body.get('email', '').strip().lower()
        password = body.get('password', '')

        if not email or not password:
            return {
                'statusCode': 400,
                'headers': cors_headers,
                'body': json.dumps({'error': 'Email and password are required'})
            }

        # Get user from database
        response = users_table.get_item(Key={'email': email})

        if 'Item' not in response:
            return {
                'statusCode': 401,
                'headers': cors_headers,
                'body': json.dumps({'error': 'Invalid email or password'})
            }

        user = response['Item']

        # Verify password
        if not verify_password(password, user['password']):
            return {
                'statusCode': 401,
                'headers': cors_headers,
                'body': json.dumps({'error': 'Invalid email or password'})
            }

        # Update last login
        users_table.update_item(
            Key={'email': email},
            UpdateExpression='SET last_login = :time',
            ExpressionAttributeValues={':time': datetime.utcnow().isoformat()}
        )

        # Generate token
        token = create_jwt_token(user['user_id'], email)

        return {
            'statusCode': 200,
            'headers': cors_headers,
            'body': json.dumps({
                'message': 'Login successful',
                'token': token,
                'user': {
                    'user_id': user['user_id'],
                    'email': user['email'],
                    'name': user.get('name', '')
                }
            })
        }

    except Exception as e:
        print(f"Login error: {str(e)}")
        import traceback
        traceback.print_exc()
        return {
            'statusCode': 500,
            'headers': cors_headers,
            'body': json.dumps({'error': f'Login failed: {str(e)}'})
        }


def handle_verify(event, cors_headers):
    """
    GET /api/auth/verify
    Verify JWT token
    """
    try:
        # Get token from Authorization header
        headers = event.get('headers', {})
        auth_header = headers.get('Authorization') or headers.get('authorization')

        if not auth_header:
            return {
                'statusCode': 401,
                'headers': cors_headers,
                'body': json.dumps({'error': 'No authorization token provided'})
            }

        # Extract token (format: "Bearer <token>")
        token = auth_header.replace('Bearer ', '').strip()

        # Verify token
        payload = verify_jwt_token(token)

        if not payload:
            return {
                'statusCode': 401,
                'headers': cors_headers,
                'body': json.dumps({'error': 'Invalid or expired token'})
            }

        # Get user details
        response = users_table.get_item(Key={'email': payload['email']})

        if 'Item' not in response:
            return {
                'statusCode': 401,
                'headers': cors_headers,
                'body': json.dumps({'error': 'User not found'})
            }

        user = response['Item']

        return {
            'statusCode': 200,
            'headers': cors_headers,
            'body': json.dumps({
                'valid': True,
                'user': {
                    'user_id': user['user_id'],
                    'email': user['email'],
                    'name': user.get('name', '')
                }
            })
        }

    except Exception as e:
        print(f"Verification error: {str(e)}")
        import traceback
        traceback.print_exc()
        return {
            'statusCode': 500,
            'headers': cors_headers,
            'body': json.dumps({'error': f'Verification failed: {str(e)}'})
        }


def verify_auth_middleware(event):
    """
    Middleware to verify authentication for protected routes
    Returns user_id if authenticated, None otherwise
    """
    try:
        headers = event.get('headers', {})
        auth_header = headers.get('Authorization') or headers.get('authorization')

        if not auth_header:
            return None

        token = auth_header.replace('Bearer ', '').strip()
        payload = verify_jwt_token(token)

        if not payload:
            return None

        return payload.get('user_id')

    except Exception as e:
        print(f"Auth middleware error: {str(e)}")
        return None
