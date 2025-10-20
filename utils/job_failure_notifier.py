# Created: 2025-10-20
# Last Modified: 2025-10-20 12:55:41
# Author: Scott Cadreau

"""
Job Failure Notification System

This module provides email notifications when critical scheduled jobs fail,
ensuring administrators are immediately alerted to issues that could impact
business operations.
"""

import logging
from typing import Dict, Any, Optional
from datetime import datetime
import traceback

logger = logging.getLogger(__name__)


def send_job_failure_notification(
    job_name: str,
    error_message: str,
    job_details: Optional[Dict[str, Any]] = None,
    exception: Optional[Exception] = None
) -> bool:
    """
    Send email notification when a critical scheduled job fails.
    
    Args:
        job_name: Name of the failed job
        error_message: Description of the failure
        job_details: Optional dictionary with additional job context
        exception: Optional exception object for full traceback
        
    Returns:
        True if notification sent successfully, False otherwise
    """
    try:
        from utils.email_service import send_email
        from utils.secrets_manager import get_secret_value
        
        # Get notification recipients from secrets
        try:
            recipients_str = get_secret_value("surgicase/main", "job_failure_recipients")
            if not recipients_str:
                # Fallback to admin email
                recipients_str = get_secret_value("surgicase/main", "admin_email")
            
            if not recipients_str:
                # Second fallback to dev email addresses
                recipients_str = get_secret_value("surgicase/main", "DEV_EMAIL_ADDRESSES")
            
            if not recipients_str:
                logger.error("No job failure notification recipients configured")
                return False
            
            # Handle both string and list formats (DEV_EMAIL_ADDRESSES might be a list)
            if isinstance(recipients_str, str):
                recipients = [email.strip() for email in recipients_str.split(",")]
            elif isinstance(recipients_str, list):
                recipients = [email.strip() if isinstance(email, str) else str(email) for email in recipients_str]
            else:
                recipients = [str(recipients_str)]
            
        except Exception as e:
            logger.error(f"Failed to get notification recipients: {str(e)}")
            return False
        
        # Build email content
        timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
        
        subject = f"🚨 CRITICAL: Scheduled Job Failed - {job_name}"
        
        # Build HTML body
        html_body = f"""
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; }}
                .header {{ background-color: #d32f2f; color: white; padding: 20px; }}
                .content {{ padding: 20px; }}
                .error-box {{ background-color: #ffebee; border-left: 4px solid #d32f2f; padding: 15px; margin: 15px 0; }}
                .details {{ background-color: #f5f5f5; padding: 15px; margin: 15px 0; border-radius: 4px; }}
                .footer {{ color: #666; font-size: 12px; margin-top: 30px; padding-top: 20px; border-top: 1px solid #ddd; }}
                code {{ background-color: #f5f5f5; padding: 2px 6px; border-radius: 3px; font-family: monospace; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>🚨 Scheduled Job Failure Alert</h1>
            </div>
            <div class="content">
                <p><strong>A critical scheduled job has failed and requires immediate attention.</strong></p>
                
                <div class="details">
                    <h3>Job Information:</h3>
                    <ul>
                        <li><strong>Job Name:</strong> {job_name}</li>
                        <li><strong>Time:</strong> {timestamp}</li>
                        <li><strong>Status:</strong> <span style="color: #d32f2f;">FAILED</span></li>
                    </ul>
                </div>
                
                <div class="error-box">
                    <h3>Error Details:</h3>
                    <p>{error_message}</p>
                </div>
        """
        
        # Add job details if provided
        if job_details:
            html_body += """
                <div class="details">
                    <h3>Additional Context:</h3>
                    <ul>
            """
            for key, value in job_details.items():
                html_body += f"<li><strong>{key}:</strong> {value}</li>\n"
            html_body += """
                    </ul>
                </div>
            """
        
        # Add exception traceback if provided
        if exception:
            tb = traceback.format_exception(type(exception), exception, exception.__traceback__)
            tb_str = "".join(tb).replace("\n", "<br>").replace(" ", "&nbsp;")
            html_body += f"""
                <div class="details">
                    <h3>Full Traceback:</h3>
                    <code style="display: block; white-space: pre-wrap; font-size: 11px;">
                        {tb_str}
                    </code>
                </div>
            """
        
        # Add action items
        html_body += """
                <div class="details">
                    <h3>Recommended Actions:</h3>
                    <ol>
                        <li>Check the application logs for detailed error information</li>
                        <li>Verify AWS services (Secrets Manager, RDS, SES, S3) are operational</li>
                        <li>Check network connectivity and API quotas</li>
                        <li>Manually re-run the job if needed using the scheduler utility functions</li>
                        <li>Monitor for recurring failures</li>
                    </ol>
                </div>
                
                <div class="footer">
                    <p>This is an automated alert from the SurgiCase Scheduler Service.</p>
                    <p>Server: Production | Environment: AWS</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        # Build plain text body (fallback)
        text_body = f"""
CRITICAL: Scheduled Job Failed

Job Name: {job_name}
Time: {timestamp}
Status: FAILED

Error Details:
{error_message}
"""
        
        if job_details:
            text_body += "\nAdditional Context:\n"
            for key, value in job_details.items():
                text_body += f"  {key}: {value}\n"
        
        if exception:
            tb = traceback.format_exception(type(exception), exception, exception.__traceback__)
            text_body += "\nFull Traceback:\n" + "".join(tb)
        
        text_body += """
Recommended Actions:
1. Check the application logs for detailed error information
2. Verify AWS services (Secrets Manager, RDS, SES, S3) are operational
3. Check network connectivity and API quotas
4. Manually re-run the job if needed using the scheduler utility functions
5. Monitor for recurring failures

---
This is an automated alert from the SurgiCase Scheduler Service.
        """
        
        # Send the email
        result = send_email(
            to_addresses=recipients,
            subject=subject,
            body=text_body,
            body_html=html_body,
            email_type="job_failure_alert"
        )
        
        if result.get('success'):
            logger.info(f"✅ Job failure notification sent successfully for {job_name}")
            return True
        else:
            logger.error(f"❌ Failed to send job failure notification: {result.get('error')}")
            return False
            
    except Exception as e:
        logger.error(f"❌ Critical error in job failure notification system: {str(e)}")
        logger.error(traceback.format_exc())
        return False


def send_job_partial_failure_notification(
    job_name: str,
    warning_message: str,
    stats: Dict[str, Any]
) -> bool:
    """
    Send email notification when a job completes with warnings or partial failures.
    
    Args:
        job_name: Name of the job
        warning_message: Description of the warning condition
        stats: Dictionary with job statistics (successful, failed, etc.)
        
    Returns:
        True if notification sent successfully, False otherwise
    """
    try:
        from utils.email_service import send_email
        from utils.secrets_manager import get_secret_value
        
        # Get notification recipients
        try:
            recipients_str = get_secret_value("surgicase/main", "job_failure_recipients")
            if not recipients_str:
                recipients_str = get_secret_value("surgicase/main", "admin_email")
            
            if not recipients_str:
                # Second fallback to dev email addresses
                recipients_str = get_secret_value("surgicase/main", "DEV_EMAIL_ADDRESSES")
            
            if not recipients_str:
                logger.warning("No job failure notification recipients configured")
                return False
            
            # Handle both string and list formats (DEV_EMAIL_ADDRESSES might be a list)
            if isinstance(recipients_str, str):
                recipients = [email.strip() for email in recipients_str.split(",")]
            elif isinstance(recipients_str, list):
                recipients = [email.strip() if isinstance(email, str) else str(email) for email in recipients_str]
            else:
                recipients = [str(recipients_str)]
            
        except Exception as e:
            logger.error(f"Failed to get notification recipients: {str(e)}")
            return False
        
        timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
        
        subject = f"⚠️ WARNING: Scheduled Job Partial Failure - {job_name}"
        
        # Build HTML body
        html_body = f"""
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; }}
                .header {{ background-color: #ff9800; color: white; padding: 20px; }}
                .content {{ padding: 20px; }}
                .warning-box {{ background-color: #fff3e0; border-left: 4px solid #ff9800; padding: 15px; margin: 15px 0; }}
                .stats {{ background-color: #f5f5f5; padding: 15px; margin: 15px 0; border-radius: 4px; }}
                .footer {{ color: #666; font-size: 12px; margin-top: 30px; padding-top: 20px; border-top: 1px solid #ddd; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>⚠️ Scheduled Job Partial Failure</h1>
            </div>
            <div class="content">
                <p><strong>A scheduled job completed with warnings or partial failures.</strong></p>
                
                <div class="stats">
                    <h3>Job Information:</h3>
                    <ul>
                        <li><strong>Job Name:</strong> {job_name}</li>
                        <li><strong>Time:</strong> {timestamp}</li>
                        <li><strong>Status:</strong> <span style="color: #ff9800;">PARTIAL FAILURE</span></li>
                    </ul>
                </div>
                
                <div class="warning-box">
                    <h3>Warning Details:</h3>
                    <p>{warning_message}</p>
                </div>
                
                <div class="stats">
                    <h3>Job Statistics:</h3>
                    <ul>
        """
        
        for key, value in stats.items():
            html_body += f"<li><strong>{key}:</strong> {value}</li>\n"
        
        html_body += """
                    </ul>
                </div>
                
                <div class="footer">
                    <p>This is an automated alert from the SurgiCase Scheduler Service.</p>
                    <p>The job may need to be re-run or investigated for recurring issues.</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        # Plain text version
        text_body = f"""
WARNING: Scheduled Job Partial Failure

Job Name: {job_name}
Time: {timestamp}
Status: PARTIAL FAILURE

Warning Details:
{warning_message}

Job Statistics:
"""
        for key, value in stats.items():
            text_body += f"  {key}: {value}\n"
        
        text_body += """
---
This is an automated alert from the SurgiCase Scheduler Service.
The job may need to be re-run or investigated for recurring issues.
        """
        
        # Send the email
        result = send_email(
            to_addresses=recipients,
            subject=subject,
            body=text_body,
            body_html=html_body,
            email_type="job_warning_alert"
        )
        
        if result.get('success'):
            logger.info(f"✅ Job warning notification sent successfully for {job_name}")
            return True
        else:
            logger.error(f"❌ Failed to send job warning notification: {result.get('error')}")
            return False
            
    except Exception as e:
        logger.error(f"❌ Error in job warning notification system: {str(e)}")
        return False

