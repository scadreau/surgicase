# Created: 2025-07-30 14:30:30
# Last Modified: 2025-08-26 20:16:49
# Author: Scott Cadreau

import boto3
import logging
import json
from typing import List, Optional, Union, Dict, Any
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
import os
import pymysql.cursors
from botocore.exceptions import ClientError
from utils.timezone_utils import format_datetime_for_user
from datetime import datetime

# Configure logging
logger = logging.getLogger(__name__)

class EmailAttachment:
    """Class to represent an email attachment"""
    def __init__(self, filename: str, content: bytes, content_type: str = "application/octet-stream"):
        self.filename = filename
        self.content = content
        self.content_type = content_type

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

def is_email_enabled(aws_region: str = "us-east-1") -> bool:
    """
    Check if email sending is enabled by checking the ENABLE_EMAIL setting in surgicase/main secret
    
    Args:
        aws_region: AWS region where the secret is stored
        
    Returns:
        True if email sending is enabled, False otherwise
        
    Raises:
        Exception: If there's an error accessing the secret (defaults to True for safety)
    """
    try:
        enable_email_value = _get_secret_value("surgicase/main", "ENABLE_EMAIL", aws_region)
        
        if enable_email_value is None:
            logger.warning("ENABLE_EMAIL key not found in surgicase/main secret, defaulting to enabled")
            return True
            
        # Convert string value to boolean
        if isinstance(enable_email_value, str):
            enable_email_value = enable_email_value.lower()
            return enable_email_value in ('true', '1', 'yes', 'on', 'enabled')
        elif isinstance(enable_email_value, bool):
            return enable_email_value
        else:
            logger.warning(f"ENABLE_EMAIL has unexpected type {type(enable_email_value)}, defaulting to enabled")
            return True
            
    except Exception as e:
        logger.error(f"Error checking ENABLE_EMAIL setting: {str(e)}, defaulting to enabled")
        # Default to True for safety - we don't want to accidentally disable emails due to config issues
        return True

def _get_default_from_address(aws_region: str = "us-east-1") -> str:
    """
    Get the default SES from email address from AWS Secrets Manager
    
    Args:
        aws_region: AWS region where the secret is stored
        
    Returns:
        The default from email address
        
    Raises:
        ValueError: If the secret cannot be retrieved or is empty
    """
    try:
        from_address = _get_secret_value("surgicase/ses_keys", "ses_default_from_email", aws_region)
        
        if not from_address:
            raise ValueError("ses_default_from_email key not found in surgicase/ses_keys secret or is empty")
            
        return from_address
        
    except Exception as e:
        raise ValueError(f"Failed to retrieve default from address from AWS Secrets Manager: {str(e)}")

def log_email_to_database(
    to_addresses: List[str],
    subject: str,
    body: str,
    from_address: str,
    message_id: Optional[str] = None,
    cc_addresses: Optional[List[str]] = None,
    bcc_addresses: Optional[List[str]] = None,
    attachments: Optional[List[EmailAttachment]] = None,
    email_type: Optional[str] = None,
    report_type: Optional[str] = None,
    status: str = "sent",
    error_message: Optional[str] = None,
    aws_region: str = "us-east-1"
) -> bool:
    """
    Log email details to the email_log database table
    
    Args:
        to_addresses: List of recipient email addresses
        subject: Email subject
        body: Email body content
        from_address: Sender email address
        message_id: AWS SES Message ID (if successful)
        cc_addresses: CC recipients
        bcc_addresses: BCC recipients
        attachments: List of email attachments
        email_type: Type of email being sent
        report_type: Type of report if applicable
        status: Email status (sent, failed, etc.)
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
        
        # Prepare attachment info
        attachments_count = len(attachments) if attachments else 0
        attachment_filenames = None
        if attachments:
            attachment_filenames = ', '.join([att.filename for att in attachments])
        
        # Truncate body for preview (first 500 characters)
        body_preview = body[:500] if body else None
        
        # Convert address lists to comma-separated strings
        to_address_primary = to_addresses[0] if to_addresses else ""
        cc_addresses_str = ', '.join(cc_addresses) if cc_addresses else None
        bcc_addresses_str = ', '.join(bcc_addresses) if bcc_addresses else None
        
        with conn.cursor() as cursor:
            sql = """
                INSERT INTO email_log (
                    message_id, to_address, cc_addresses, bcc_addresses, 
                    from_address, subject, body_preview, attachments_count,
                    attachment_filenames, email_type, report_type, status,
                    error_message, aws_region
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                )
            """
            
            cursor.execute(sql, (
                message_id, to_address_primary, cc_addresses_str, bcc_addresses_str,
                from_address, subject, body_preview, attachments_count,
                attachment_filenames, email_type, report_type, status,
                error_message, aws_region
            ))
            
            conn.commit()
            
            # Log additional recipients if there are multiple TO addresses
            if len(to_addresses) > 1:
                for additional_to in to_addresses[1:]:
                    cursor.execute(sql, (
                        message_id, additional_to, cc_addresses_str, bcc_addresses_str,
                        from_address, subject, body_preview, attachments_count,
                        attachment_filenames, email_type, report_type, status,
                        error_message, aws_region
                    ))
                conn.commit()
            
            logger.info(f"Email logged to database: {len(to_addresses)} recipients, message_id: {message_id}")
            return True
            
    except Exception as e:
        logger.error(f"Failed to log email to database: {str(e)}")
        if conn:
            try:
                conn.rollback()
            except:
                pass
        return False
        
    finally:
        if conn:
            close_db_connection(conn)

def send_email(
    to_addresses: Union[str, List[str]],
    subject: str,
    body: str,
    from_address: Optional[str] = None,
    attachments: Optional[List[EmailAttachment]] = None,
    cc_addresses: Optional[Union[str, List[str]]] = None,
    bcc_addresses: Optional[Union[str, List[str]]] = None,
    body_html: Optional[str] = None,
    aws_region: str = "us-east-1",
    email_type: Optional[str] = None,
    report_type: Optional[str] = None
) -> Dict[str, Any]:
    """
    Send an email using AWS Simple Email Service (SES)
    
    Args:
        to_addresses: Email address(es) to send to. Can be a string or list of strings
        subject: Email subject line
        body: Plain text email body
        from_address: Sender email address. If None, retrieves from AWS Secrets Manager (surgicase/ses_keys)
        attachments: List of EmailAttachment objects to attach to the email
        cc_addresses: Email address(es) to CC. Can be a string or list of strings
        bcc_addresses: Email address(es) to BCC. Can be a string or list of strings
        body_html: HTML version of the email body (optional)
        aws_region: AWS region for SES service (default: us-east-1)
        email_type: Type of email being sent (for logging purposes)
        report_type: Type of report if applicable (for logging purposes)
    
    Returns:
        Dict containing success status and message ID or error details
        
    Raises:
        ValueError: If required parameters are missing or invalid
        ClientError: If AWS SES service returns an error
    """
    
    try:
        # Check if email sending is enabled before proceeding
        if not is_email_enabled(aws_region):
            logger.info("Email sending is disabled via ENABLE_EMAIL setting. Email will not be sent.")
            
            # Normalize email addresses to lists for logging
            if isinstance(to_addresses, str):
                to_addresses_list = [to_addresses]
            else:
                to_addresses_list = to_addresses
            if isinstance(cc_addresses, str):
                cc_addresses_list = [cc_addresses]
            else:
                cc_addresses_list = cc_addresses
            if isinstance(bcc_addresses, str):
                bcc_addresses_list = [bcc_addresses]
            else:
                bcc_addresses_list = bcc_addresses
            
            # Log the email as "disabled" in the database for tracking
            log_email_to_database(
                to_addresses=to_addresses_list,
                subject=subject,
                body=body,
                from_address=from_address or "system@disabled",
                cc_addresses=cc_addresses_list,
                bcc_addresses=bcc_addresses_list,
                attachments=attachments,
                email_type=email_type,
                report_type=report_type,
                status="disabled",
                error_message="Email sending disabled via ENABLE_EMAIL setting",
                aws_region=aws_region
            )
            
            return {
                "success": False,
                "error": "Email sending is disabled via ENABLE_EMAIL setting",
                "disabled": True,
                "to_addresses": to_addresses_list
            }
        
        # Validate required parameters
        if not to_addresses:
            raise ValueError("to_addresses is required")
        if not subject:
            raise ValueError("subject is required")
        if not body and not body_html:
            raise ValueError("Either body or body_html is required")
        
        # Normalize email addresses to lists
        if isinstance(to_addresses, str):
            to_addresses = [to_addresses]
        if isinstance(cc_addresses, str):
            cc_addresses = [cc_addresses]
        if isinstance(bcc_addresses, str):
            bcc_addresses = [bcc_addresses]
            
        # Get from address from AWS Secrets Manager if not provided
        if not from_address:
            from_address = _get_default_from_address(aws_region)
        
        # Initialize SES client
        ses_client = boto3.client('ses', region_name=aws_region)
        
        # If no attachments and no HTML, use simple send_email
        if not attachments and not body_html:
            result = _send_simple_email(
                ses_client, to_addresses, subject, body, from_address,
                cc_addresses, bcc_addresses
            )
            
            # Log successful email to database
            if result.get("success"):
                log_email_to_database(
                    to_addresses=to_addresses,
                    subject=subject,
                    body=body,
                    from_address=from_address,
                    message_id=result.get("message_id"),
                    cc_addresses=cc_addresses,
                    bcc_addresses=bcc_addresses,
                    attachments=attachments,
                    email_type=email_type,
                    report_type=report_type,
                    status="sent",
                    aws_region=aws_region
                )
            
            return result
        
        # For attachments or HTML, use send_raw_email
        result = _send_raw_email(
            ses_client, to_addresses, subject, body, from_address,
            attachments, cc_addresses, bcc_addresses, body_html
        )
        
        # Log successful email to database
        if result.get("success"):
            log_email_to_database(
                to_addresses=to_addresses,
                subject=subject,
                body=body,
                from_address=from_address,
                message_id=result.get("message_id"),
                cc_addresses=cc_addresses,
                bcc_addresses=bcc_addresses,
                attachments=attachments,
                email_type=email_type,
                report_type=report_type,
                status="sent",
                aws_region=aws_region
            )
        
        return result
        
    except ClientError as e:
        error_msg = f"AWS SES error: {e.response['Error']['Message']}"
        logger.error(error_msg)
        
        # Log failed email to database
        log_email_to_database(
            to_addresses=to_addresses,
            subject=subject,
            body=body,
            from_address=from_address or "unknown",
            cc_addresses=cc_addresses,
            bcc_addresses=bcc_addresses,
            attachments=attachments,
            email_type=email_type,
            report_type=report_type,
            status="failed",
            error_message=error_msg,
            aws_region=aws_region
        )
        
        return {
            "success": False,
            "error": error_msg,
            "error_code": e.response['Error']['Code']
        }
    except Exception as e:
        error_msg = f"Email sending failed: {str(e)}"
        logger.error(error_msg)
        
        # Log failed email to database
        log_email_to_database(
            to_addresses=to_addresses,
            subject=subject,
            body=body,
            from_address=from_address or "unknown",
            cc_addresses=cc_addresses,
            bcc_addresses=bcc_addresses,
            attachments=attachments,
            email_type=email_type,
            report_type=report_type,
            status="failed",
            error_message=error_msg,
            aws_region=aws_region
        )
        
        return {
            "success": False,
            "error": error_msg
        }

def _send_simple_email(
    ses_client, to_addresses: List[str], subject: str, body: str,
    from_address: str, cc_addresses: Optional[List[str]] = None,
    bcc_addresses: Optional[List[str]] = None
) -> Dict[str, Any]:
    """Send a simple text email without attachments"""
    
    destination = {'ToAddresses': to_addresses}
    if cc_addresses:
        destination['CcAddresses'] = cc_addresses
    if bcc_addresses:
        destination['BccAddresses'] = bcc_addresses
    
    response = ses_client.send_email(
        Source=from_address,
        Destination=destination,
        Message={
            'Subject': {'Data': subject, 'Charset': 'UTF-8'},
            'Body': {'Text': {'Data': body, 'Charset': 'UTF-8'}}
        }
    )
    
    logger.info(f"Email sent successfully. Message ID: {response['MessageId']}")
    return {
        "success": True,
        "message_id": response['MessageId'],
        "to_addresses": to_addresses
    }

def _send_raw_email(
    ses_client, to_addresses: List[str], subject: str, body: str,
    from_address: str, attachments: Optional[List[EmailAttachment]] = None,
    cc_addresses: Optional[List[str]] = None, bcc_addresses: Optional[List[str]] = None,
    body_html: Optional[str] = None
) -> Dict[str, Any]:
    """Send an email with attachments and/or HTML using raw email format"""
    
    # Create message container
    msg = MIMEMultipart('mixed')
    msg['Subject'] = subject
    msg['From'] = from_address
    msg['To'] = ', '.join(to_addresses)
    
    if cc_addresses:
        msg['Cc'] = ', '.join(cc_addresses)
    
    # Create message body container
    if body_html:
        # Create multipart/alternative for text and HTML
        msg_body = MIMEMultipart('alternative')
        
        # Add plain text part
        text_part = MIMEText(body, 'plain', 'utf-8')
        msg_body.attach(text_part)
        
        # Add HTML part
        html_part = MIMEText(body_html, 'html', 'utf-8')
        msg_body.attach(html_part)
        
        msg.attach(msg_body)
    else:
        # Just plain text
        text_part = MIMEText(body, 'plain', 'utf-8')
        msg.attach(text_part)
    
    # Add attachments
    if attachments:
        for attachment in attachments:
            part = MIMEBase('application', 'octet-stream')
            part.set_payload(attachment.content)
            encoders.encode_base64(part)
            part.add_header(
                'Content-Disposition',
                f'attachment; filename= {attachment.filename}'
            )
            msg.attach(part)
    
    # Prepare destination list
    destinations = to_addresses.copy()
    if cc_addresses:
        destinations.extend(cc_addresses)
    if bcc_addresses:
        destinations.extend(bcc_addresses)
    
    # Send the email
    response = ses_client.send_raw_email(
        Source=from_address,
        Destinations=destinations,
        RawMessage={'Data': msg.as_string()}
    )
    
    logger.info(f"Email with attachments sent successfully. Message ID: {response['MessageId']}")
    return {
        "success": True,
        "message_id": response['MessageId'],
        "to_addresses": to_addresses,
        "attachments_count": len(attachments) if attachments else 0
    }

def create_attachment_from_file(file_path: str, filename: Optional[str] = None) -> EmailAttachment:
    """
    Create an EmailAttachment from a file path
    
    Args:
        file_path: Path to the file to attach
        filename: Optional filename to use in the email. If None, uses the original filename
        
    Returns:
        EmailAttachment object
        
    Raises:
        FileNotFoundError: If the file doesn't exist
        IOError: If there's an error reading the file
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")
    
    if filename is None:
        filename = os.path.basename(file_path)
    
    try:
        with open(file_path, 'rb') as f:
            content = f.read()
        
        # Determine content type based on file extension
        content_type = _get_content_type(filename)
        
        return EmailAttachment(filename, content, content_type)
        
    except Exception as e:
        raise IOError(f"Error reading file {file_path}: {str(e)}")

def create_attachment_from_data(filename: str, data: bytes, content_type: str = "application/octet-stream") -> EmailAttachment:
    """
    Create an EmailAttachment from raw data
    
    Args:
        filename: Name to use for the attachment
        data: Raw bytes data for the attachment
        content_type: MIME content type for the attachment
        
    Returns:
        EmailAttachment object
    """
    return EmailAttachment(filename, data, content_type)

def _get_content_type(filename: str) -> str:
    """Get appropriate MIME content type based on file extension"""
    extension = os.path.splitext(filename)[1].lower()
    
    content_types = {
        '.pdf': 'application/pdf',
        '.csv': 'text/csv',
        '.iif': 'application/octet-stream',
        '.txt': 'text/plain',
        '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        '.xls': 'application/vnd.ms-excel',
        '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        '.doc': 'application/msword',
        '.zip': 'application/zip',
        '.json': 'application/json',
        '.xml': 'application/xml',
        '.png': 'image/png',
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg',
        '.gif': 'image/gif'
    }
    
    return content_types.get(extension, 'application/octet-stream')

def verify_ses_configuration(aws_region: str = "us-east-1") -> Dict[str, Any]:
    """
    Verify that SES is properly configured and return configuration details
    
    Args:
        aws_region: AWS region to check SES configuration
        
    Returns:
        Dict containing configuration status and details
    """
    try:
        ses_client = boto3.client('ses', region_name=aws_region)
        
        # Get sending quota
        quota_response = ses_client.get_send_quota()
        
        # Get verified identities
        identities_response = ses_client.list_verified_email_addresses()
        
        # Test default from address retrieval
        try:
            default_from = _get_default_from_address(aws_region)
            secrets_status = {"success": True, "default_from_email": default_from}
        except Exception as e:
            secrets_status = {"success": False, "error": str(e)}
        
        return {
            "success": True,
            "region": aws_region,
            "daily_sending_quota": quota_response['Max24HourSend'],
            "emails_sent_today": quota_response['SentLast24Hours'],
            "send_rate_limit": quota_response['MaxSendRate'],
            "verified_email_addresses": identities_response['VerifiedEmailAddresses'],
            "secrets_manager": secrets_status
        }
        
    except ClientError as e:
        return {
            "success": False,
            "error": f"SES configuration error: {e.response['Error']['Message']}",
            "error_code": e.response['Error']['Code']
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Configuration check failed: {str(e)}"
        }

def test_secrets_configuration(aws_region: str = "us-east-1") -> Dict[str, Any]:
    """
    Test the AWS Secrets Manager configuration for email service
    
    Args:
        aws_region: AWS region where the secret is stored
        
    Returns:
        Dict containing test results and configuration details
    """
    try:
        # Test secret retrieval
        from_address = _get_default_from_address(aws_region)
        
        return {
            "success": True,
            "secret_name": "surgicase/ses_keys",
            "key_name": "ses_default_from_email",
            "from_address": from_address,
            "region": aws_region,
            "message": "Secrets Manager configuration is working correctly"
        }
        
    except Exception as e:
        return {
            "success": False,
            "secret_name": "surgicase/ses_keys",
            "key_name": "ses_default_from_email",
            "region": aws_region,
            "error": str(e),
            "message": "Failed to retrieve configuration from Secrets Manager"
        }

# ========================================
# Email Verification Functions
# ========================================

def verify_email_address(email_address: str, aws_region: str = "us-east-1") -> Dict[str, Any]:
    """
    Send verification email to add a new email address to SES
    
    Args:
        email_address: Email address to verify
        aws_region: AWS region for SES
        
    Returns:
        Dictionary with verification status
    """
    try:
        ses_client = boto3.client('ses', region_name=aws_region)
        
        # Check if already verified
        verified = ses_client.list_verified_email_addresses()
        if email_address in verified['VerifiedEmailAddresses']:
            return {
                "success": True,
                "already_verified": True,
                "message": f"Email {email_address} is already verified"
            }
        
        # Send verification email
        response = ses_client.verify_email_identity(EmailAddress=email_address)
        
        logger.info(f"Verification email sent to {email_address}")
        
        return {
            "success": True,
            "already_verified": False,
            "message": f"Verification email sent to {email_address}. Check inbox and click verification link.",
            "request_id": response['ResponseMetadata']['RequestId']
        }
        
    except ClientError as e:
        error_code = e.response['Error']['Code']
        error_message = e.response['Error']['Message']
        logger.error(f"Error verifying email {email_address}: {error_code} - {error_message}")
        
        return {
            "success": False,
            "error_code": error_code,
            "message": f"Failed to send verification email: {error_message}"
        }
    except Exception as e:
        error_msg = f"Unexpected error verifying email {email_address}: {str(e)}"
        logger.error(error_msg)
        return {
            "success": False,
            "message": error_msg
        }

def check_email_verification_status(email_address: str, aws_region: str = "us-east-1") -> Dict[str, Any]:
    """
    Check if an email address is verified in SES
    
    Args:
        email_address: Email address to check
        aws_region: AWS region for SES
        
    Returns:
        Dictionary with verification status
    """
    try:
        ses_client = boto3.client('ses', region_name=aws_region)
        
        # Get list of verified email addresses
        verified = ses_client.list_verified_email_addresses()
        is_verified = email_address in verified['VerifiedEmailAddresses']
        
        return {
            "success": True,
            "email_address": email_address,
            "is_verified": is_verified,
            "all_verified_emails": verified['VerifiedEmailAddresses']
        }
        
    except Exception as e:
        error_msg = f"Error checking verification status for {email_address}: {str(e)}"
        logger.error(error_msg)
        return {
            "success": False,
            "message": error_msg
        }

def auto_verify_recipients_for_report(report_name: str, email_type: str = "on_demand", aws_region: str = "us-east-1") -> Dict[str, Any]:
    """
    Automatically send verification emails to any unverified recipients for a report
    
    Args:
        report_name: Name of the report (e.g., 'provider_payment_report')
        email_type: Type of email - 'weekly' or 'on_demand' (default: 'on_demand')
        aws_region: AWS region for SES
        
    Returns:
        Dictionary with verification results
    """
    try:
        # Get recipients for the report
        recipients = get_report_email_recipients(report_name, email_type)
        
        if not recipients:
            return {
                "success": True,
                "message": f"No recipients configured for {report_name}_{email_type}",
                "results": []
            }
        
        # Check and verify each recipient
        results = []
        verification_sent_count = 0
        
        for recipient in recipients:
            email = recipient['email_address']
            result = verify_email_address(email, aws_region)
            result['recipient_name'] = f"{recipient.get('first_name', '')} {recipient.get('last_name', '')}".strip()
            results.append(result)
            
            if result['success'] and not result.get('already_verified', False):
                verification_sent_count += 1
        
        return {
            "success": True,
            "message": f"Verification process completed. {verification_sent_count} verification emails sent.",
            "total_recipients": len(recipients),
            "verification_emails_sent": verification_sent_count,
            "results": results
        }
        
    except Exception as e:
        error_msg = f"Error auto-verifying recipients for {report_name}_{email_type}: {str(e)}"
        logger.error(error_msg)
        return {
            "success": False,
            "message": error_msg,
            "results": []
        }

# ========================================
# Provider Payment Report Email Functions
# ========================================

def get_email_templates(aws_region: str = "us-east-1") -> Dict[str, Any]:
    """
    Fetch email templates from AWS Secrets Manager
    
    Args:
        aws_region: AWS region where the secret is stored
        
    Returns:
        Dictionary containing email templates
        
    Raises:
        Exception: If templates cannot be retrieved
    """
    try:
        from utils.secrets_manager import get_secret
        templates = get_secret('surgicase/email_templates')
        logger.info("Successfully retrieved email templates from AWS Secrets Manager")
        return templates
    except Exception as e:
        logger.error(f"Error fetching email templates from Secrets Manager: {str(e)}")
        raise

def update_email_templates(templates: Dict[str, Any], aws_region: str = "us-east-1") -> bool:
    """
    Update email templates in AWS Secrets Manager
    
    Args:
        templates: Dictionary containing email templates to save
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
            SecretId='surgicase/email_templates',
            SecretString=json.dumps(templates, indent=2)
        )
        # Clear cache for this secret after update
        from utils.secrets_manager import clear_secrets_cache
        clear_secrets_cache('surgicase/email_templates')
        logger.info("Successfully updated email templates in AWS Secrets Manager")
        return True
    except Exception as e:
        logger.error(f"Error updating email templates in Secrets Manager: {str(e)}")
        raise



def get_report_email_recipients(report_name: str, email_type: str = "on_demand") -> List[Dict[str, str]]:
    """
    Query the report_email_list table for recipients of a specific report
    
    Args:
        report_name: The base name of the report (e.g., 'provider_payment_report')
        email_type: The type of email - 'weekly' or 'on_demand' (default: 'on_demand')
        
    Returns:
        List of dictionaries containing email_address, first_name, last_name
        
    Raises:
        Exception: If database query fails
    """
    # Import here to avoid circular imports
    from core.database import get_db_connection, close_db_connection
    
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            # Create the full report name with suffix based on email_type
            full_report_name = f"{report_name}_{email_type}"
            
            sql = """
                SELECT email_address, first_name, last_name 
                FROM report_email_list 
                WHERE report_name = %s
            """
            cursor.execute(sql, (full_report_name,))
            recipients = cursor.fetchall()
            logger.info(f"Found {len(recipients)} recipients for report: {full_report_name}")
            return recipients
    except Exception as e:
        logger.error(f"Error fetching email recipients for {report_name}_{email_type}: {str(e)}")
        raise
    finally:
        if conn:
            close_db_connection(conn)

def format_email_template(template: str, variables: Dict[str, str]) -> str:
    """
    Format email template with provided variables
    
    Args:
        template: Email template string with {variable} placeholders
        variables: Dictionary of variable names and values
        
    Returns:
        Formatted email string
        
    Raises:
        KeyError: If required variable is missing
        Exception: If formatting fails
    """
    try:
        return template.format(**variables)
    except KeyError as e:
        logger.error(f"Missing variable in email template: {str(e)}")
        raise
    except Exception as e:
        logger.error(f"Error formatting email template: {str(e)}")
        raise

def send_provider_payment_report_emails(
    report_path: str,
    report_filename: str,
    report_data: Dict[str, Any],
    email_type: str = "on_demand",
    aws_region: str = "us-east-1"
) -> Dict[str, Any]:
    """
    Send provider payment report to all configured recipients
    
    Args:
        report_path: Local path to the PDF report
        report_filename: Name of the PDF file
        report_data: Dictionary containing report metadata for email variables
        email_type: Type of email template to use ("weekly" or "on_demand")
        aws_region: AWS region for services
        
    Returns:
        Dictionary with overall results and individual email statuses
    """
    try:
        # Get email templates
        templates = get_email_templates(aws_region)
        template_config = templates['email_templates']['provider_payment_report'][email_type]
        
        # Get recipients based on email type
        recipients = get_report_email_recipients('provider_payment_report', email_type)
        
        if not recipients:
            logger.warning(f"No recipients found for provider_payment_report_{email_type}")
            return {
                "success": True,
                "message": f"No recipients configured for provider_payment_report_{email_type}",
                "emails_sent": 0,
                "total_recipients": 0,
                "results": []
            }
        
        # Prepare template variables
        template_variables = {
            "creation_date": report_data.get('creation_date', ''),
            "report_date": report_data.get('report_date', ''),
            "total_providers": str(report_data.get('total_providers', '')),
            "total_cases": str(report_data.get('total_cases', '')),
            "total_amount": str(report_data.get('total_amount', '')),
            "filename": report_filename,
            "password": report_data.get('password', '') or 'Not password protected'
        }
        
        # Create attachment
        attachment = create_attachment_from_file(report_path, report_filename)
        
        results = []
        successful_sends = 0
        
        # Send email to each recipient
        for recipient in recipients:
            try:
                # Add recipient-specific variables
                email_variables = template_variables.copy()
                email_variables['first_name'] = recipient.get('first_name', 'Valued Partner')
                email_variables['last_name'] = recipient.get('last_name', '')
                
                # Convert creation_date to recipient's timezone if it's available
                if 'creation_date_utc' in report_data:
                    email_variables['creation_date'] = format_datetime_for_user(
                        report_data['creation_date_utc'],
                        email_address=recipient['email_address'],
                        format_string='%B %d, %Y'
                    )
                
                # Format email content
                subject = format_email_template(template_config['subject'], email_variables)
                body = format_email_template(template_config['body'], email_variables)
                
                # Send email using existing send_email function with display name
                result = send_email(
                    to_addresses=recipient['email_address'],
                    subject=subject,
                    body=body,
                    attachments=[attachment],
                    from_address="SurgiCase Automation <noreply@metoraymedical.com>",
                    aws_region=aws_region,
                    email_type="provider_payment_report",
                    report_type=f"provider_payment_report_{email_type}"
                )
                
                # Format result for consistency
                formatted_result = {
                    "success": result.get('success', False),
                    "recipient": recipient['email_address'],
                    "message": result.get('message', ''),
                    "message_id": result.get('message_id')
                }
                
                results.append(formatted_result)
                
                if formatted_result['success']:
                    successful_sends += 1
                    logger.info(f"Successfully sent email to {recipient['email_address']}")
                else:
                    logger.error(f"Failed to send email to {recipient['email_address']}: {formatted_result['message']}")
                    
            except Exception as e:
                error_result = {
                    "success": False,
                    "recipient": recipient['email_address'],
                    "message": f"Error processing email for {recipient['email_address']}: {str(e)}",
                    "message_id": None
                }
                results.append(error_result)
                logger.error(error_result['message'])
        
        success_message = f"Email sending completed. {successful_sends}/{len(recipients)} emails sent successfully"
        logger.info(success_message)
        
        return {
            "success": True,
            "message": success_message,
            "emails_sent": successful_sends,
            "total_recipients": len(recipients),
            "results": results
        }
        
    except Exception as e:
        error_msg = f"Error sending provider payment report emails: {str(e)}"
        logger.error(error_msg)
        return {
            "success": False,
            "message": error_msg,
            "emails_sent": 0,
            "total_recipients": 0,
            "results": []
        }

def send_individual_provider_payment_report_email(
    provider_email: str,
    provider_info: dict,
    report_path: str,
    report_filename: str,
    email_data: dict,
    email_type: str = "weekly",
    aws_region: str = "us-east-1"
) -> Dict[str, Any]:
    """
    Send individual provider payment report to a specific provider
    
    Args:
        provider_email: Provider's email address
        provider_info: Provider information dictionary
        report_path: Local path to the password-protected PDF report
        report_filename: Name of the PDF file
        email_data: Dictionary containing email template variables
        email_type: Type of email template to use ("weekly" or "on_demand")
        aws_region: AWS region for services
        
    Returns:
        Dictionary with email sending results
    """
    try:
        # Get email templates
        templates = get_email_templates(aws_region)
        
        # Check if individual template exists in AWS secrets
        if 'individual_provider_payment_report' not in templates['email_templates']:
            logger.error(
                "Individual provider payment report email templates not found in AWS Secrets Manager. "
                "Please add templates manually to 'surgicase/email_templates' secret under the key "
                "'individual_provider_payment_report' with 'weekly' and 'on_demand' sub-keys."
            )
            raise ValueError("Individual provider payment report email templates not configured in AWS Secrets")
        
        # Get the individual template from AWS secrets using new structure
        individual_template = templates['email_templates']['individual_provider_payment_report'][email_type]
        
        # Prepare template variables
        template_variables = {
            "provider_name": email_data.get('provider_name', 'Valued Provider'),
            "npi": email_data.get('npi', ''),
            "creation_date": email_data.get('creation_date', ''),
            "filename": email_data.get('filename', ''),
            "password": email_data.get('password', ''),
            "total_amount": email_data.get('total_amount', ''),
            "case_count": email_data.get('case_count', ''),
            "first_name": provider_info.get('first_name', 'Valued'),
            "last_name": provider_info.get('last_name', 'Provider')
        }
        
        # Format email content
        subject = format_email_template(individual_template['subject'], template_variables)
        body = format_email_template(individual_template['body'], template_variables)
        
        # Create attachment
        attachment = create_attachment_from_file(report_path, report_filename)
        
        # Send email using existing send_email function
        result = send_email(
            to_addresses=provider_email,
            subject=subject,
            body=body,
            attachments=[attachment],
            from_address="SurgiCase Reports <noreply@metoraymedical.com>",
            aws_region=aws_region,
            email_type="individual_provider_payment_report",
            report_type=f"individual_provider_payment_report_{email_type}"
        )
        
        if result.get('success'):
            logger.info(f"Successfully sent individual provider report to {provider_email}")
            return {
                "success": True,
                "message": f"Individual provider report sent to {provider_email}",
                "message_id": result.get('message_id'),
                "recipient": provider_email
            }
        else:
            logger.error(f"Failed to send individual provider report to {provider_email}: {result.get('error', 'Unknown error')}")
            return {
                "success": False,
                "message": f"Failed to send email to {provider_email}: {result.get('error', 'Unknown error')}",
                "recipient": provider_email
            }
        
    except Exception as e:
        error_msg = f"Error sending individual provider payment report to {provider_email}: {str(e)}"
        logger.error(error_msg)
        return {
            "success": False,
            "message": error_msg,
            "recipient": provider_email
        }



def send_provider_payment_summary_report_emails(
    report_path: str,
    report_filename: str,
    report_data: Dict[str, Any],
    email_type: str = "on_demand",
    aws_region: str = "us-east-1"
) -> Dict[str, Any]:
    """
    Send provider payment summary report to all configured recipients
    
    Args:
        report_path: Local path to the PDF report
        report_filename: Name of the PDF file
        report_data: Dictionary containing report metadata for email variables
        email_type: Type of email template to use ("weekly" or "on_demand")
        aws_region: AWS region for services
        
    Returns:
        Dictionary with overall results and individual email statuses
    """
    try:
        # Get email templates
        templates = get_email_templates(aws_region)
        
        # Check if summary templates exist
        if 'provider_payment_summary_report' not in templates['email_templates']:
            logger.error(
                "Provider payment summary report email templates not found in AWS Secrets Manager. "
                "Please add templates manually to 'surgicase/email_templates' secret under the key "
                "'provider_payment_summary_report' with 'weekly' and 'on_demand' sub-keys."
            )
            raise ValueError("Provider payment summary report email templates not configured in AWS Secrets")
        
        template_config = templates['email_templates']['provider_payment_summary_report'][email_type]
        
        # Get recipients based on email type - use same recipient list as main provider report
        recipients = get_report_email_recipients('provider_payment_summary_report', email_type)
        
        # If no specific recipients found for summary report, fall back to main provider report recipients
        if not recipients:
            logger.warning(f"No recipients found for provider_payment_summary_report_{email_type}, trying provider_payment_report_{email_type}")
            recipients = get_report_email_recipients('provider_payment_report', email_type)
        
        if not recipients:
            logger.warning(f"No recipients found for provider payment summary report - email_type: {email_type}")
            return {
                "success": True,
                "message": f"No recipients configured for provider_payment_summary_report_{email_type}",
                "emails_sent": 0,
                "total_recipients": 0,
                "results": []
            }
        
        # Prepare template variables
        template_variables = {
            "creation_date": report_data.get('creation_date', ''),
            "report_date": report_data.get('report_date', ''),
            "total_states": str(report_data.get('total_states', '')),
            "total_providers": str(report_data.get('total_providers', '')),
            "total_amount": str(report_data.get('total_amount', '')),
            "filename": report_filename
        }
        
        # Create attachment
        attachment = create_attachment_from_file(report_path, report_filename)
        
        results = []
        successful_sends = 0
        
        for recipient in recipients:
            try:
                # Prepare personalized template variables
                personalized_variables = template_variables.copy()
                personalized_variables.update({
                    "first_name": recipient.get('first_name', 'Team Member'),
                    "last_name": recipient.get('last_name', ''),
                })
                
                # Format email content
                subject = format_email_template(template_config['subject'], personalized_variables)
                body = format_email_template(template_config['body'], personalized_variables)
                
                # Send email
                email_result = send_email(
                    to_addresses=[recipient['email_address']],
                    subject=subject,
                    body=body,
                    attachments=[attachment],
                    email_type=f"provider_payment_summary_report_{email_type}",
                    report_type="provider_payment_summary_report",
                    aws_region=aws_region
                )
                
                # Format result for consistency
                formatted_result = {
                    "success": email_result.get('success', False),
                    "recipient": recipient['email_address'],
                    "message": email_result.get('message', 'Unknown result'),
                    "message_id": email_result.get('message_id')
                }
                results.append(formatted_result)
                
                if formatted_result['success']:
                    successful_sends += 1
                    logger.info(f"Successfully sent summary report email to {recipient['email_address']}")
                else:
                    logger.error(f"Failed to send summary report email to {recipient['email_address']}: {formatted_result['message']}")
                    
            except Exception as e:
                error_result = {
                    "success": False,
                    "recipient": recipient['email_address'],
                    "message": f"Error processing email for {recipient['email_address']}: {str(e)}",
                    "message_id": None
                }
                results.append(error_result)
                logger.error(error_result['message'])
        
        success_message = f"Summary report email sending completed. {successful_sends}/{len(recipients)} emails sent successfully"
        logger.info(success_message)
        
        return {
            "success": True,
            "message": success_message,
            "emails_sent": successful_sends,
            "total_recipients": len(recipients),
            "results": results
        }
        
    except Exception as e:
        error_msg = f"Error sending provider payment summary report emails: {str(e)}"
        logger.error(error_msg)
        return {
            "success": False,
            "message": error_msg,
            "emails_sent": 0,
            "total_recipients": 0,
            "results": []
        }

# ========================================
# Welcome Email Functions
# ========================================

def send_welcome_email(
    user_email: str,
    first_name: str,
    last_name: str,
    aws_region: str = "us-east-1"
) -> Dict[str, Any]:
    """
    Send welcome email to new users when they complete registration
    
    Args:
        user_email: User's email address
        first_name: User's first name
        last_name: User's last name
        aws_region: AWS region for services
        
    Returns:
        Dictionary with email sending results
    """
    try:
        # Get email templates
        templates = get_email_templates(aws_region)
        
        # Check if welcome template exists
        if 'welcome_user' not in templates['email_templates']:
            logger.error("Welcome user email template not found in AWS Secrets Manager")
            raise ValueError("Welcome user email template not configured in AWS Secrets")
        
        welcome_template = templates['email_templates']['welcome_user']
        
        # Prepare template variables
        template_variables = {
            "first_name": first_name or "New User",
            "last_name": last_name or ""
        }
        
        # Format email content
        subject = format_email_template(welcome_template['subject'], template_variables)
        body = format_email_template(welcome_template['body'], template_variables)
        
        # Send email
        result = send_email(
            to_addresses=user_email,
            subject=subject,
            body=body,
            from_address="SurgiCase Team <noreply@metoraymedical.com>",
            aws_region=aws_region,
            email_type="welcome_user",
            report_type="welcome_user"
        )
        
        if result.get('success'):
            logger.info(f"Successfully sent welcome email to {user_email}")
            return {
                "success": True,
                "message": f"Welcome email sent to {user_email}",
                "message_id": result.get('message_id'),
                "recipient": user_email
            }
        else:
            logger.error(f"Failed to send welcome email to {user_email}: {result.get('error', 'Unknown error')}")
            return {
                "success": False,
                "message": f"Failed to send welcome email to {user_email}: {result.get('error', 'Unknown error')}",
                "recipient": user_email
            }
        
    except Exception as e:
        error_msg = f"Error sending welcome email to {user_email}: {str(e)}"
        logger.error(error_msg)
        return {
            "success": False,
            "message": error_msg,
            "recipient": user_email
        }

def send_referral_report_emails(
    report_path: str,
    report_filename: str,
    report_data: Dict[str, Any],
    email_type: str = "weekly",
    aws_region: str = "us-east-1"
) -> Dict[str, Any]:
    """
    Send referral report to all configured recipients
    
    Args:
        report_path: Local path to the PDF report
        report_filename: Name of the PDF file
        report_data: Dictionary containing report metadata for email variables
        email_type: Type of email template to use ("weekly" or "on_demand")
        aws_region: AWS region for services
        
    Returns:
        Dictionary with overall results and individual email statuses
    """
    try:
        # Get email templates
        templates = get_email_templates(aws_region)
        
        # Check if referral report templates exist
        if 'referral_report' not in templates['email_templates']:
            logger.error(
                "Referral report email templates not found in AWS Secrets Manager. "
                "Please add templates manually to 'surgicase/email_templates' secret under the key "
                "'referral_report' with 'weekly' and 'on_demand' sub-keys."
            )
            raise ValueError("Referral report email templates not configured in AWS Secrets")
        
        template_config = templates['email_templates']['referral_report'][email_type]
        
        # Get recipients for referral report
        recipients = get_report_email_recipients('referral_report', email_type)
        
        if not recipients:
            logger.warning(f"No recipients found for referral_report_{email_type}")
            return {
                "success": True,
                "message": f"No recipients configured for referral_report_{email_type}",
                "emails_sent": 0,
                "total_recipients": 0,
                "individual_results": []
            }
        
        logger.info(f"Sending referral report to {len(recipients)} recipients")
        
        # Read the PDF file for attachment
        with open(report_path, 'rb') as f:
            pdf_content = f.read()
        
        attachment = EmailAttachment(
            filename=report_filename,
            content=pdf_content,
            content_type='application/pdf'
        )
        
        # Send emails to all recipients
        results = []
        successful_sends = 0
        
        for recipient in recipients:
            try:
                # Prepare template variables for this recipient
                template_vars = {
                    **report_data,
                    "recipient_name": f"{recipient.get('first_name', '')} {recipient.get('last_name', '')}".strip(),
                    "recipient_first_name": recipient.get('first_name', ''),
                    "recipient_last_name": recipient.get('last_name', '')
                }
                
                # Handle timezone conversion for creation_date if UTC datetime is provided
                if 'creation_date_utc' in template_vars and isinstance(template_vars['creation_date_utc'], datetime):
                    # Use recipient-specific timezone formatting if available
                    template_vars['creation_date'] = format_datetime_for_user(
                        template_vars['creation_date_utc'],
                        user_id=None,  # No specific user context for admin reports
                        format_string='%B %d, %Y'
                    )
                
                # Format email content
                subject = format_email_template(template_config['subject'], template_vars)
                body = format_email_template(template_config['body'], template_vars)
                
                result = send_email(
                    to_addresses=[recipient['email_address']],
                    subject=subject,
                    body=body,
                    attachments=[attachment],
                    email_type=f"referral_report_{email_type}",
                    report_type="referral_report",
                    aws_region=aws_region
                )
                
                if result.get('success', False):
                    successful_sends += 1
                    logger.info(f"Successfully sent referral report to {recipient['email_address']}")
                else:
                    logger.error(f"Failed to send referral report to {recipient['email_address']}: {result.get('message', 'Unknown error')}")
                
                results.append({
                    "recipient": recipient['email_address'],
                    "success": result.get('success', False),
                    "message": result.get('message', 'Unknown result')
                })
                
            except Exception as e:
                error_msg = f"Error sending referral report to {recipient['email_address']}: {str(e)}"
                logger.error(error_msg)
                results.append({
                    "recipient": recipient['email_address'],
                    "success": False,
                    "message": error_msg
                })
        
        # Return overall results
        overall_success = successful_sends > 0
        return {
            "success": overall_success,
            "message": f"Sent referral report to {successful_sends} of {len(recipients)} recipients",
            "emails_sent": successful_sends,
            "total_recipients": len(recipients),
            "individual_results": results
        }
        
    except Exception as e:
        error_msg = f"Error in send_referral_report_emails: {str(e)}"
        logger.error(error_msg)
        return {
            "success": False,
            "message": error_msg,
            "emails_sent": 0,
            "total_recipients": 0,
            "individual_results": []
        }