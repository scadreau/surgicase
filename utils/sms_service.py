# Created: 2025-08-18 23:03:35
# Last Modified: 2025-08-20 08:38:53
# Author: Scott Cadreau

import boto3
import logging
import json
from typing import Optional, Dict, Any
from botocore.exceptions import ClientError
from datetime import datetime

# Twilio imports
try:
    from twilio.rest import Client as TwilioClient
    from twilio.base.exceptions import TwilioException
    TWILIO_AVAILABLE = True
except ImportError:
    TWILIO_AVAILABLE = False

# Configure logging
logger = logging.getLogger(__name__)

def _get_secret_value(secret_name: str, key: str, aws_region: str = "us-east-1") -> Optional[str]:
    """
    Retrieve a specific key from AWS Secrets Manager using centralized secrets manager
    
    Args:
        secret_name: Name of the secret in Secrets Manager
        key: Key within the secret to retrieve
        aws_region: AWS region where the secret is stored (kept for compatibility)
        
    Returns:
        The secret value or None if not found
        
    Raises:
        ClientError: If there's an error accessing the secret
    """
    try:
        from utils.secrets_manager import get_secret_value
        return get_secret_value(secret_name, key)
        
    except Exception as e:
        logger.error(f"Error retrieving secret {secret_name}, key {key}: {e}")
        raise

def is_sms_enabled(aws_region: str = "us-east-1") -> bool:
    """
    Check if SMS sending is enabled by checking the ENABLE_SMS setting in surgicase/main secret
    
    Args:
        aws_region: AWS region where the secret is stored
        
    Returns:
        True if SMS sending is enabled, False otherwise
        
    Raises:
        Exception: If there's an error accessing the secret (defaults to True for safety)
    """
    try:
        enable_sms_value = _get_secret_value("surgicase/main", "ENABLE_SMS", aws_region)
        
        if enable_sms_value is None:
            logger.warning("ENABLE_SMS key not found in surgicase/main secret, defaulting to enabled")
            return True
            
        # Convert string value to boolean
        if isinstance(enable_sms_value, str):
            enable_sms_value = enable_sms_value.lower()
            return enable_sms_value in ('true', '1', 'yes', 'on', 'enabled')
        elif isinstance(enable_sms_value, bool):
            return enable_sms_value
        else:
            logger.warning(f"ENABLE_SMS has unexpected type {type(enable_sms_value)}, defaulting to enabled")
            return True
            
    except Exception as e:
        logger.error(f"Error checking ENABLE_SMS setting: {str(e)}, defaulting to enabled")
        # Default to True for safety - we don't want to accidentally disable SMS due to config issues
        return True

def _get_default_admin_phone(aws_region: str = "us-east-1") -> str:
    """
    Get the default admin phone number from AWS Secrets Manager
    
    Args:
        aws_region: AWS region where the secret is stored
        
    Returns:
        The default admin phone number
        
    Raises:
        ValueError: If the secret cannot be retrieved or is empty
    """
    try:
        admin_phone = _get_secret_value("surgicase/main", "ADMIN_PHONE_NUMBER", aws_region)
        
        if not admin_phone:
            # Fallback to hardcoded admin phone number
            logger.warning("ADMIN_PHONE_NUMBER not found in secrets, using fallback")
            return "+14802997297"
            
        # Ensure phone number has proper format
        if not admin_phone.startswith('+'):
            if admin_phone.startswith('1'):
                admin_phone = '+' + admin_phone
            else:
                admin_phone = '+1' + admin_phone
                
        return admin_phone
        
    except Exception as e:
        logger.warning(f"Failed to retrieve admin phone from secrets: {str(e)}, using fallback")
        return "+14802997297"

def log_sms_to_database(
    phone_number: str,
    message: str,
    message_id: Optional[str] = None,
    sms_type: Optional[str] = None,
    status: str = "sent",
    error_message: Optional[str] = None,
    aws_region: str = "us-east-1"
) -> bool:
    """
    Log SMS details to the sms_log database table
    
    Args:
        phone_number: Recipient phone number
        message: SMS message content
        message_id: AWS SNS Message ID (if successful)
        sms_type: Type of SMS being sent
        status: SMS status (sent, failed, disabled, etc.)
        error_message: Error details if failed
        aws_region: AWS region used
        
    Returns:
        True if logging successful, False otherwise
    """
    # Import here to avoid circular imports
    from core.database import get_db_connection, close_db_connection
    
    conn = None
    try:
        conn = get_db_connection()
        
        # Truncate message for preview (first 500 characters)
        message_preview = message[:500] if message else None
        
        with conn.cursor() as cursor:
            sql = """
                INSERT INTO sms_log (
                    message_id, phone_number, message_preview, sms_type, 
                    status, error_message, aws_region
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s
                )
            """
            
            cursor.execute(sql, (
                message_id, phone_number, message_preview, sms_type,
                status, error_message, aws_region
            ))
            
            conn.commit()
            logger.info(f"SMS logged to database: {phone_number}, message_id: {message_id}")
            return True
            
    except Exception as e:
        logger.error(f"Failed to log SMS to database: {str(e)}")
        if conn:
            try:
                conn.rollback()
            except:
                pass
        return False
        
    finally:
        if conn:
            close_db_connection(conn)

def _get_twilio_credentials(aws_region: str = "us-east-1") -> Dict[str, str]:
    """
    Get Twilio credentials from AWS Secrets Manager
    
    Args:
        aws_region: AWS region where the secret is stored
        
    Returns:
        Dictionary containing Twilio credentials
        
    Raises:
        ValueError: If credentials cannot be retrieved
    """
    try:
        from utils.secrets_manager import get_secret
        twilio_secrets = get_secret('surgicase/twilio_keys')
        
        # Check for required keys - handle both 'phone_number' and 'from_phone'
        required_keys = ['account_sid', 'auth_token']
        for key in required_keys:
            if key not in twilio_secrets:
                raise ValueError(f"Missing required Twilio credential: {key}")
        
        # Handle phone number - check for both possible key names
        if 'from_phone' in twilio_secrets:
            twilio_secrets['phone_number'] = twilio_secrets['from_phone']
        elif 'phone_number' not in twilio_secrets:
            raise ValueError("Missing Twilio phone number (expected 'from_phone' or 'phone_number' key)")
        
        return twilio_secrets
        
    except Exception as e:
        raise ValueError(f"Failed to retrieve Twilio credentials from AWS Secrets Manager: {str(e)}")

def send_sms_twilio(
    phone_number: str,
    message: str,
    sms_type: Optional[str] = None,
    aws_region: str = "us-east-1"
) -> Dict[str, Any]:
    """
    Send SMS using Twilio
    
    Args:
        phone_number: Phone number to send SMS to (E.164 format recommended)
        message: SMS message content
        sms_type: Type of SMS being sent (for logging purposes)
        aws_region: AWS region for secrets (default: us-east-1)
    
    Returns:
        Dict containing success status and message ID or error details
    """
    try:
        if not TWILIO_AVAILABLE:
            raise ImportError("Twilio library not installed. Run: pip install twilio")
        
        # Get Twilio credentials
        twilio_creds = _get_twilio_credentials(aws_region)
        
        # Initialize Twilio client
        client = TwilioClient(twilio_creds['account_sid'], twilio_creds['auth_token'])
        
        # Send SMS
        message_obj = client.messages.create(
            body=message,
            from_=twilio_creds['phone_number'],
            to=phone_number
        )
        
        message_id = message_obj.sid
        logger.info(f"SMS sent successfully via Twilio to {phone_number}. Message SID: {message_id}")
        
        # Log successful SMS to database
        log_sms_to_database(
            phone_number=phone_number,
            message=message,
            message_id=message_id,
            sms_type=sms_type,
            status="sent",
            aws_region=aws_region
        )
        
        return {
            "success": True,
            "message_id": message_id,
            "phone_number": phone_number,
            "provider": "twilio"
        }
        
    except TwilioException as e:
        error_msg = f"Twilio SMS error: {str(e)}"
        logger.error(error_msg)
        
        # Log failed SMS to database
        log_sms_to_database(
            phone_number=phone_number,
            message=message,
            sms_type=sms_type,
            status="failed",
            error_message=error_msg,
            aws_region=aws_region
        )
        
        return {
            "success": False,
            "error": error_msg,
            "provider": "twilio"
        }
    except Exception as e:
        error_msg = f"SMS sending failed: {str(e)}"
        logger.error(error_msg)
        
        # Log failed SMS to database
        log_sms_to_database(
            phone_number=phone_number,
            message=message,
            sms_type=sms_type,
            status="failed",
            error_message=error_msg,
            aws_region=aws_region
        )
        
        return {
            "success": False,
            "error": error_msg,
            "provider": "twilio"
        }

def send_sms(
    phone_number: str,
    message: str,
    aws_region: str = "us-east-1",
    sms_type: Optional[str] = None,
    provider: str = "twilio"
) -> Dict[str, Any]:
    """
    Send an SMS using Twilio (default) or AWS SNS
    
    Args:
        phone_number: Phone number to send SMS to (E.164 format recommended)
        message: SMS message content
        aws_region: AWS region for secrets/SNS service (default: us-east-1)
        sms_type: Type of SMS being sent (for logging purposes)
        provider: SMS provider to use ("twilio" or "sns", default: "twilio")
    
    Returns:
        Dict containing success status and message ID or error details
        
    Raises:
        ValueError: If required parameters are missing or invalid
    """
    
    try:
        # Check if SMS sending is enabled before proceeding
        if not is_sms_enabled(aws_region):
            logger.info("SMS sending is disabled via ENABLE_SMS setting. SMS will not be sent.")
            
            # Log the SMS as "disabled" in the database for tracking
            log_sms_to_database(
                phone_number=phone_number,
                message=message,
                sms_type=sms_type,
                status="disabled",
                error_message="SMS sending disabled via ENABLE_SMS setting",
                aws_region=aws_region
            )
            
            return {
                "success": False,
                "error": "SMS sending is disabled via ENABLE_SMS setting",
                "disabled": True,
                "phone_number": phone_number
            }
        
        # Validate required parameters
        if not phone_number:
            raise ValueError("phone_number is required")
        if not message:
            raise ValueError("message is required")
        
        # Use Twilio by default (more reliable than SNS)
        if provider.lower() == "twilio":
            return send_sms_twilio(phone_number, message, sms_type, aws_region)
        else:
            # Fallback to SNS
            return send_sms_sns(phone_number, message, sms_type, aws_region)
        
    except Exception as e:
        error_msg = f"SMS sending failed: {str(e)}"
        logger.error(error_msg)
        
        # Log failed SMS to database
        log_sms_to_database(
            phone_number=phone_number,
            message=message,
            sms_type=sms_type,
            status="failed",
            error_message=error_msg,
            aws_region=aws_region
        )
        
        return {
            "success": False,
            "error": error_msg
        }

def send_sms_sns(
    phone_number: str,
    message: str,
    sms_type: Optional[str] = None,
    aws_region: str = "us-east-1"
) -> Dict[str, Any]:
    """
    Send an SMS using AWS Simple Notification Service (SNS)
    
    Args:
        phone_number: Phone number to send SMS to (E.164 format recommended)
        message: SMS message content
        sms_type: Type of SMS being sent (for logging purposes)
        aws_region: AWS region for SNS service (default: us-east-1)
    
    Returns:
        Dict containing success status and message ID or error details
    """
    try:
        # Initialize SNS client
        sns_client = boto3.client('sns', region_name=aws_region)
        
        # Send SMS
        response = sns_client.publish(
            PhoneNumber=phone_number,
            Message=message,
            MessageAttributes={
                'AWS.SNS.SMS.SMSType': {
                    'DataType': 'String',
                    'StringValue': 'Transactional'
                }
            }
        )
        
        message_id = response['MessageId']
        logger.info(f"SMS sent successfully via SNS to {phone_number}. Message ID: {message_id}")
        
        # Log successful SMS to database
        log_sms_to_database(
            phone_number=phone_number,
            message=message,
            message_id=message_id,
            sms_type=sms_type,
            status="sent",
            aws_region=aws_region
        )
        
        return {
            "success": True,
            "message_id": message_id,
            "phone_number": phone_number,
            "provider": "sns"
        }
        
    except ClientError as e:
        error_msg = f"AWS SNS error: {e.response['Error']['Message']}"
        logger.error(error_msg)
        
        # Log failed SMS to database
        log_sms_to_database(
            phone_number=phone_number,
            message=message,
            sms_type=sms_type,
            status="failed",
            error_message=error_msg,
            aws_region=aws_region
        )
        
        return {
            "success": False,
            "error": error_msg,
            "error_code": e.response['Error']['Code'],
            "provider": "sns"
        }
    except Exception as e:
        error_msg = f"SMS sending failed: {str(e)}"
        logger.error(error_msg)
        
        # Log failed SMS to database
        log_sms_to_database(
            phone_number=phone_number,
            message=message,
            sms_type=sms_type,
            status="failed",
            error_message=error_msg,
            aws_region=aws_region
        )
        
        return {
            "success": False,
            "error": error_msg,
            "provider": "sns"
        }

def get_sms_templates(aws_region: str = "us-east-1") -> Dict[str, Any]:
    """
    Fetch SMS templates from AWS Secrets Manager
    
    Args:
        aws_region: AWS region where the secret is stored
        
    Returns:
        Dictionary containing SMS templates
        
    Raises:
        Exception: If templates cannot be retrieved
    """
    try:
        from utils.secrets_manager import get_secret
        templates = get_secret('surgicase/sms_templates')
        logger.info("Successfully retrieved SMS templates from AWS Secrets Manager")
        return templates
    except Exception as e:
        logger.error(f"Error fetching SMS templates from Secrets Manager: {str(e)}")
        raise

def update_sms_templates(templates: Dict[str, Any], aws_region: str = "us-east-1") -> bool:
    """
    Update SMS templates in AWS Secrets Manager
    
    Args:
        templates: Dictionary containing SMS templates to save
        aws_region: AWS region where the secret is stored
        
    Returns:
        True if successful, False otherwise
        
    Raises:
        Exception: If templates cannot be updated
    """
    try:
        # Note: Update operations still need direct boto3 client as centralized secrets manager is read-only
        client = boto3.client('secretsmanager', region_name=aws_region)
        response = client.update_secret(
            SecretId='surgicase/sms_templates',
            SecretString=json.dumps(templates, indent=2)
        )
        # Clear cache for this secret after update
        from utils.secrets_manager import clear_secrets_cache
        clear_secrets_cache('surgicase/sms_templates')
        logger.info("Successfully updated SMS templates in AWS Secrets Manager")
        return True
    except Exception as e:
        logger.error(f"Error updating SMS templates in Secrets Manager: {str(e)}")
        raise

def format_sms_template(template: str, variables: Dict[str, str]) -> str:
    """
    Format SMS template with provided variables
    
    Args:
        template: SMS template string with {variable} placeholders
        variables: Dictionary of variable names and values
        
    Returns:
        Formatted SMS string
        
    Raises:
        KeyError: If required variable is missing
        Exception: If formatting fails
    """
    try:
        return template.format(**variables)
    except KeyError as e:
        logger.error(f"Missing variable in SMS template: {str(e)}")
        raise
    except Exception as e:
        logger.error(f"Error formatting SMS template: {str(e)}")
        raise

def send_new_user_signup_notification(
    user_email: str,
    first_name: str,
    last_name: str,
    signup_timestamp: str,
    aws_region: str = "us-east-1"
) -> Dict[str, Any]:
    """
    Send SMS notification to admin about new user signup
    
    Args:
        user_email: New user's email address
        first_name: New user's first name
        last_name: New user's last name
        signup_timestamp: Timestamp when user signed up
        aws_region: AWS region for services
        
    Returns:
        Dictionary with SMS sending results
    """
    try:
        # Get SMS templates
        templates = get_sms_templates(aws_region)
        
        # Check if new user signup template exists
        if 'new_user_signup' not in templates['sms_templates']:
            logger.error("New user signup SMS template not found in AWS Secrets Manager")
            raise ValueError("New user signup SMS template not configured in AWS Secrets")
        
        signup_template = templates['sms_templates']['new_user_signup']
        
        # Get admin phone number
        admin_phone = _get_default_admin_phone(aws_region)
        
        # Prepare template variables
        template_variables = {
            "user_email": user_email,
            "user_first": first_name or "Unknown",
            "user_last": last_name or "Unknown",
            "timestamp": signup_timestamp
        }
        
        # Format SMS content
        message = format_sms_template(signup_template['message'], template_variables)
        
        # Send SMS
        result = send_sms(
            phone_number=admin_phone,
            message=message,
            aws_region=aws_region,
            sms_type="new_user_signup"
        )
        
        if result.get('success'):
            logger.info(f"Successfully sent new user signup SMS notification for {user_email}")
            return {
                "success": True,
                "message": f"New user signup SMS notification sent for {user_email}",
                "message_id": result.get('message_id'),
                "phone_number": admin_phone
            }
        else:
            logger.error(f"Failed to send new user signup SMS notification for {user_email}: {result.get('error', 'Unknown error')}")
            return {
                "success": False,
                "message": f"Failed to send SMS notification for {user_email}: {result.get('error', 'Unknown error')}",
                "phone_number": admin_phone
            }
        
    except Exception as e:
        error_msg = f"Error sending new user signup SMS notification for {user_email}: {str(e)}"
        logger.error(error_msg)
        return {
            "success": False,
            "message": error_msg,
            "phone_number": admin_phone if 'admin_phone' in locals() else "unknown"
        }

def verify_sns_configuration(aws_region: str = "us-east-1") -> Dict[str, Any]:
    """
    Verify that SNS is properly configured and return configuration details
    
    Args:
        aws_region: AWS region to check SNS configuration
        
    Returns:
        Dict containing configuration status and details
    """
    try:
        sns_client = boto3.client('sns', region_name=aws_region)
        
        # Get SMS attributes
        try:
            sms_attributes = sns_client.get_sms_attributes()
            sms_config = sms_attributes.get('attributes', {})
        except Exception as e:
            sms_config = {"error": f"Could not retrieve SMS attributes: {str(e)}"}
        
        # Test admin phone number retrieval
        try:
            admin_phone = _get_default_admin_phone(aws_region)
            secrets_status = {"success": True, "admin_phone_number": admin_phone}
        except Exception as e:
            secrets_status = {"success": False, "error": str(e)}
        
        return {
            "success": True,
            "region": aws_region,
            "sms_attributes": sms_config,
            "secrets_manager": secrets_status
        }
        
    except ClientError as e:
        return {
            "success": False,
            "error": f"SNS configuration error: {e.response['Error']['Message']}",
            "error_code": e.response['Error']['Code']
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Configuration check failed: {str(e)}"
        }

def test_secrets_configuration(aws_region: str = "us-east-1") -> Dict[str, Any]:
    """
    Test the AWS Secrets Manager configuration for SMS service
    
    Args:
        aws_region: AWS region where the secret is stored
        
    Returns:
        Dict containing test results and configuration details
    """
    try:
        # Test secret retrieval
        admin_phone = _get_default_admin_phone(aws_region)
        
        return {
            "success": True,
            "secret_name": "surgicase/main",
            "key_name": "ADMIN_PHONE_NUMBER",
            "admin_phone": admin_phone,
            "region": aws_region,
            "message": "Secrets Manager configuration is working correctly"
        }
        
    except Exception as e:
        return {
            "success": False,
            "secret_name": "surgicase/main",
            "key_name": "ADMIN_PHONE_NUMBER",
            "region": aws_region,
            "error": str(e),
            "message": "Failed to retrieve configuration from Secrets Manager"
        }
