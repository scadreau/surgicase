# Created: 2025-07-30 14:30:30
# Last Modified: 2025-07-30 22:00:21
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
    Retrieve a specific key from AWS Secrets Manager
    
    Args:
        secret_name: Name of the secret in Secrets Manager
        key: Key within the secret to retrieve
        aws_region: AWS region where the secret is stored
        
    Returns:
        The secret value or None if not found
        
    Raises:
        ClientError: If there's an error accessing the secret
    """
    try:
        secrets_client = boto3.client('secretsmanager', region_name=aws_region)
        
        response = secrets_client.get_secret_value(SecretId=secret_name)
        secret_dict = json.loads(response['SecretString'])
        
        return secret_dict.get(key)
        
    except ClientError as e:
        error_code = e.response['Error']['Code']
        if error_code == 'ResourceNotFoundException':
            logger.error(f"Secret {secret_name} not found")
        elif error_code == 'InvalidRequestException':
            logger.error(f"Invalid request for secret {secret_name}")
        elif error_code == 'InvalidParameterException':
            logger.error(f"Invalid parameter for secret {secret_name}")
        else:
            logger.error(f"Error retrieving secret {secret_name}: {e}")
        raise
    except json.JSONDecodeError as e:
        logger.error(f"Error parsing secret {secret_name} as JSON: {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error retrieving secret {secret_name}: {e}")
        raise

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

def send_email(
    to_addresses: Union[str, List[str]],
    subject: str,
    body: str,
    from_address: Optional[str] = None,
    attachments: Optional[List[EmailAttachment]] = None,
    cc_addresses: Optional[Union[str, List[str]]] = None,
    bcc_addresses: Optional[Union[str, List[str]]] = None,
    body_html: Optional[str] = None,
    aws_region: str = "us-east-1"
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
    
    Returns:
        Dict containing success status and message ID or error details
        
    Raises:
        ValueError: If required parameters are missing or invalid
        ClientError: If AWS SES service returns an error
    """
    
    try:
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
            return _send_simple_email(
                ses_client, to_addresses, subject, body, from_address,
                cc_addresses, bcc_addresses
            )
        
        # For attachments or HTML, use send_raw_email
        return _send_raw_email(
            ses_client, to_addresses, subject, body, from_address,
            attachments, cc_addresses, bcc_addresses, body_html
        )
        
    except ClientError as e:
        error_msg = f"AWS SES error: {e.response['Error']['Message']}"
        logger.error(error_msg)
        return {
            "success": False,
            "error": error_msg,
            "error_code": e.response['Error']['Code']
        }
    except Exception as e:
        error_msg = f"Email sending failed: {str(e)}"
        logger.error(error_msg)
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

def auto_verify_recipients_for_report(report_name: str, aws_region: str = "us-east-1") -> Dict[str, Any]:
    """
    Automatically send verification emails to any unverified recipients for a report
    
    Args:
        report_name: Name of the report (e.g., 'provider_payment_report')
        aws_region: AWS region for SES
        
    Returns:
        Dictionary with verification results
    """
    try:
        # Get recipients for the report
        recipients = get_report_email_recipients(report_name)
        
        if not recipients:
            return {
                "success": True,
                "message": f"No recipients configured for {report_name}",
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
        error_msg = f"Error auto-verifying recipients for {report_name}: {str(e)}"
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
        client = boto3.client('secretsmanager', region_name=aws_region)
        response = client.get_secret_value(SecretId='surgicase/email_templates')
        templates = json.loads(response['SecretString'])
        logger.info("Successfully retrieved email templates from AWS Secrets Manager")
        return templates
    except Exception as e:
        logger.error(f"Error fetching email templates from Secrets Manager: {str(e)}")
        raise

def get_report_email_recipients(report_name: str) -> List[Dict[str, str]]:
    """
    Query the report_email_list table for recipients of a specific report
    
    Args:
        report_name: The name of the report (e.g., 'provider_payment_report')
        
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
            sql = """
                SELECT email_address, first_name, last_name 
                FROM report_email_list 
                WHERE report_name = %s
            """
            cursor.execute(sql, (report_name,))
            recipients = cursor.fetchall()
            logger.info(f"Found {len(recipients)} recipients for report: {report_name}")
            return recipients
    except Exception as e:
        logger.error(f"Error fetching email recipients for {report_name}: {str(e)}")
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
        
        # Get recipients
        recipients = get_report_email_recipients('provider_payment_report')
        
        if not recipients:
            logger.warning("No recipients found for provider_payment_report")
            return {
                "success": True,
                "message": "No recipients configured for provider_payment_report",
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
            "filename": report_filename
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
                    aws_region=aws_region
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