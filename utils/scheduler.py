# Created: 2025-01-15
# Last Modified: 2025-10-20 12:59:44
# Author: Scott Cadreau

import schedule
import time
import threading
import logging
import pymysql.cursors
import signal
import sys
import requests
from typing import List, Dict, Any
from core.database import get_db_connection, close_db_connection
from core.models import BulkCaseStatusUpdate
from endpoints.backoffice.bulk_update_case_status import bulk_update_case_status
from fastapi import Request
from unittest.mock import Mock
from utils.extract_npi_data import weekly_npi_data_update
from utils.db_backup import perform_database_backup, cleanup_old_backups

logger = logging.getLogger(__name__)

# Global flag for graceful shutdown
shutdown_requested = False

def signal_handler(signum, frame):
    """Handle shutdown signals gracefully."""
    global shutdown_requested
    logger.info(f"Received signal {signum}. Initiating graceful shutdown...")
    shutdown_requested = True

def get_cases_with_status(status: int) -> List[str]:
    """
    Get all case IDs that have the specified case_status.
    
    Args:
        status: The case_status to search for
        
    Returns:
        List of case IDs matching the status
    """
    conn = None
    case_ids = []
    
    try:
        conn = get_db_connection()
        
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute("""
                SELECT case_id 
                FROM cases 
                WHERE case_status = %s AND active = 1
            """, (status,))
            
            results = cursor.fetchall()
            case_ids = [row['case_id'] for row in results]
            
        logger.info(f"Found {len(case_ids)} cases with status {status}")
        return case_ids
        
    except Exception as e:
        logger.error(f"Error retrieving cases with status {status}: {str(e)}")
        return []
        
    finally:
        if conn:
            try:
                close_db_connection(conn)
            except Exception as close_error:
                logger.error(f"Error closing database connection: {str(close_error)}")

def weekly_pending_payment_update():
    """
    Weekly scheduled function to update case status from 10 to 15 (pending payment).
    
    This function:
    1. Searches for all cases with case_status=10
    2. Updates them to case_status=15 using the bulk_update_case_status function
    3. Logs the results
    """
    logger.info("Starting weekly pending payment update job...")
    
    try:
        # Get all cases with status 10
        case_ids = get_cases_with_status(10)
        
        if not case_ids:
            logger.info("No cases found with status 10. Weekly pending payment update job completed.")
            return
        
        # Create the bulk update request
        update_request = BulkCaseStatusUpdate(
            case_ids=case_ids,
            new_status=15,
            force=False  # Don't force backward progression
        )
        
        # Create a mock request object for the bulk_update_case_status function
        mock_request = Mock(spec=Request)
        
        # Call the bulk update function
        result = bulk_update_case_status(mock_request, update_request)
        
        # Log the results
        logger.info(f"Weekly pending payment update completed:")
        logger.info(f"  Total processed: {result['total_processed']}")
        logger.info(f"  Successfully updated: {result['total_updated']}")
        logger.info(f"  Exceptions: {result['total_exceptions']}")
        
        if result['exceptions']:
            logger.warning(f"Cases with exceptions: {[exc['case_id'] for exc in result['exceptions']]}")
            
        if result['updated_cases']:
            updated_case_ids = [case['case_id'] for case in result['updated_cases']]
            logger.info(f"Successfully updated cases: {updated_case_ids}")
        
    except Exception as e:
        logger.error(f"Error in weekly pending payment update job: {str(e)}")

def weekly_paid_update():
    """
    Weekly scheduled function to update case status from 15 to 20 (paid).
    
    This function:
    1. Searches for all cases with case_status=15
    2. Updates them to case_status=20 using the bulk_update_case_status function
    3. Logs the results
    """
    logger.info("Starting weekly paid update job...")
    
    try:
        # Get all cases with status 15
        case_ids = get_cases_with_status(15)
        
        if not case_ids:
            logger.info("No cases found with status 15. Weekly paid update job completed.")
            return
        
        # Create the bulk update request
        update_request = BulkCaseStatusUpdate(
            case_ids=case_ids,
            new_status=20,
            force=False  # Don't force backward progression
        )
        
        # Create a mock request object for the bulk_update_case_status function
        mock_request = Mock(spec=Request)
        
        # Call the bulk update function
        result = bulk_update_case_status(mock_request, update_request)
        
        # Log the results
        logger.info(f"Weekly paid update completed:")
        logger.info(f"  Total processed: {result['total_processed']}")
        logger.info(f"  Successfully updated: {result['total_updated']}")
        logger.info(f"  Exceptions: {result['total_exceptions']}")
        
        if result['exceptions']:
            logger.warning(f"Cases with exceptions: {[exc['case_id'] for exc in result['exceptions']]}")
            
        if result['updated_cases']:
            updated_case_ids = [case['case_id'] for case in result['updated_cases']]
            logger.info(f"Successfully updated cases: {updated_case_ids}")
        
    except Exception as e:
        logger.error(f"Error in weekly paid update job: {str(e)}")

def weekly_npi_update():
    """
    Weekly scheduled function to update NPI data from CMS website.
    
    This function:
    1. Downloads the latest weekly NPI file from CMS
    2. Checks if the file has already been processed (duplicate prevention)
    3. Processes the data and updates npi_data tables
    4. Creates search tables for surgeon and facility lookups
    5. Archives the processed file
    """
    logger.info("Starting weekly NPI data update job...")
    
    try:
        # Call the NPI update function with duplicate prevention
        result = weekly_npi_data_update()
        
        # Log the results based on status
        if result['status'] == 'success':
            logger.info(f"Weekly NPI data update completed successfully:")
            logger.info(f"  Filename processed: {result['filename']}")
            logger.info(f"  Execution time: {result['execution_time']:.2f} seconds")
            logger.info(f"  Entity type 0 records: {result['entity_counts']['total_0_rows']}")
            logger.info(f"  Entity type 1 records: {result['entity_counts']['total_1_rows']}")
            logger.info(f"  Entity type 2 records: {result['entity_counts']['total_2_rows']}")
            
        elif result['status'] == 'skipped':
            logger.info(f"Weekly NPI data update skipped:")
            logger.info(f"  Reason: {result['reason']}")
            logger.info(f"  Filename: {result['filename']}")
            logger.info("  This typically indicates the CMS website has not updated with a new weekly file yet.")
            
        elif result['status'] == 'error':
            logger.error(f"Weekly NPI data update failed: {result['error']}")
        
    except Exception as e:
        logger.error(f"Error in weekly NPI data update job: {str(e)}")

def weekly_provider_payment_report():
    """
    Weekly scheduled function to generate provider payment report and send emails.
    
    This function:
    1. Calls the provider payment report endpoint with weekly email type
    2. Generates PDF report for cases with status=15 (pending payment)
    3. Automatically sends emails to configured recipients
    4. Uses weekly email template for professional notifications
    
    Runs after weekly_pending_payment_update to capture newly eligible cases.
    """
    logger.info("Starting weekly provider payment report job...")
    
    try:
        # Call the provider payment report endpoint with weekly email type
        response = requests.get(
            'http://localhost:8000/provider_payment_report?email_type=weekly',
            timeout=300  # 5 minute timeout for report generation
        )
        
        if response.status_code == 200:
            logger.info("✅ Weekly provider payment report generated successfully")
            
            # Log email status from response headers
            email_headers = {k: v for k, v in response.headers.items() if k.startswith('X-Email')}
            if email_headers:
                emails_sent = email_headers.get('X-Email-Count', '0')
                total_recipients = email_headers.get('X-Email-Total-Recipients', '0')
                email_success = email_headers.get('X-Email-Sent', 'False')
                
                logger.info(f"📧 Email notifications: {emails_sent}/{total_recipients} sent successfully")
                logger.info(f"📧 Email status: {email_success}")
            
            # Log report details
            content_length = len(response.content)
            logger.info(f"📄 Report size: {content_length} bytes")
            logger.info("Weekly provider payment report job completed successfully")
            
        else:
            error_msg = f"Provider payment report failed with HTTP status {response.status_code}"
            logger.error(f"❌ {error_msg}")
            logger.error(f"Response: {response.text[:500]}")  # Log first 500 chars of error
            
            # Send failure notification
            from utils.job_failure_notifier import send_job_failure_notification
            send_job_failure_notification(
                job_name="Weekly Provider Payment Report",
                error_message=error_msg,
                job_details={
                    "HTTP Status": response.status_code,
                    "Response": response.text[:500]
                }
            )
            
    except requests.exceptions.Timeout as e:
        error_msg = "Provider payment report timed out (>5 minutes)"
        logger.error(f"❌ {error_msg}")
        
        from utils.job_failure_notifier import send_job_failure_notification
        send_job_failure_notification(
            job_name="Weekly Provider Payment Report",
            error_message=error_msg,
            exception=e
        )
        
    except requests.exceptions.ConnectionError as e:
        error_msg = "Cannot connect to API server for provider payment report"
        logger.error(f"❌ {error_msg}")
        
        from utils.job_failure_notifier import send_job_failure_notification
        send_job_failure_notification(
            job_name="Weekly Provider Payment Report",
            error_message=error_msg,
            job_details={
                "Note": "Check if FastAPI server is running on localhost:8000"
            },
            exception=e
        )
        
    except Exception as e:
        error_msg = f"Unexpected error in weekly provider payment report job: {str(e)}"
        logger.error(f"❌ {error_msg}")
        
        from utils.job_failure_notifier import send_job_failure_notification
        send_job_failure_notification(
            job_name="Weekly Provider Payment Report",
            error_message=error_msg,
            exception=e
        )

def weekly_provider_payment_summary_report():
    """
    Weekly scheduled function to generate provider payment summary report and send emails.
    
    This function:
    1. Calls the provider payment summary report endpoint with weekly email type
    2. Generates PDF summary report grouped by state for cases with status=15 (pending payment)
    3. Automatically sends emails to configured recipients
    4. Uses weekly email template for professional notifications
    
    Runs 15 minutes after weekly_provider_payment_report to allow consolidated report to complete first.
    """
    logger.info("Starting weekly provider payment summary report job...")
    
    try:
        # Call the provider payment summary report endpoint with weekly email type
        response = requests.get(
            'http://localhost:8000/provider_payment_summary_report?email_type=weekly',
            timeout=300  # 5 minute timeout for report generation
        )
        
        if response.status_code == 200:
            logger.info("✅ Weekly provider payment summary report generated successfully")
            
            # Log email status from response headers
            email_headers = {k: v for k, v in response.headers.items() if k.startswith('X-Email')}
            if email_headers:
                emails_sent = email_headers.get('X-Email-Count', '0')
                total_recipients = email_headers.get('X-Email-Total-Recipients', '0')
                email_success = email_headers.get('X-Email-Sent', 'False')
                
                logger.info(f"📧 Email notifications: {emails_sent}/{total_recipients} sent successfully")
                logger.info(f"📧 Email status: {email_success}")
            
            # Log report details
            content_length = len(response.content)
            logger.info(f"📄 Report size: {content_length} bytes")
            logger.info("Weekly provider payment summary report job completed successfully")
            
        else:
            error_msg = f"Provider payment summary report failed with HTTP status {response.status_code}"
            logger.error(f"❌ {error_msg}")
            logger.error(f"Response: {response.text[:500]}")  # Log first 500 chars of error
            
            # Send failure notification
            from utils.job_failure_notifier import send_job_failure_notification
            send_job_failure_notification(
                job_name="Weekly Provider Payment Summary Report",
                error_message=error_msg,
                job_details={
                    "HTTP Status": response.status_code,
                    "Response": response.text[:500]
                }
            )
            
    except requests.exceptions.Timeout as e:
        error_msg = "Provider payment summary report timed out (>5 minutes)"
        logger.error(f"❌ {error_msg}")
        
        from utils.job_failure_notifier import send_job_failure_notification
        send_job_failure_notification(
            job_name="Weekly Provider Payment Summary Report",
            error_message=error_msg,
            exception=e
        )
        
    except requests.exceptions.ConnectionError as e:
        error_msg = "Cannot connect to API server for provider payment summary report"
        logger.error(f"❌ {error_msg}")
        
        from utils.job_failure_notifier import send_job_failure_notification
        send_job_failure_notification(
            job_name="Weekly Provider Payment Summary Report",
            error_message=error_msg,
            job_details={
                "Note": "Check if FastAPI server is running on localhost:8000"
            },
            exception=e
        )
        
    except Exception as e:
        error_msg = f"Unexpected error in weekly provider payment summary report job: {str(e)}"
        logger.error(f"❌ {error_msg}")
        
        from utils.job_failure_notifier import send_job_failure_notification
        send_job_failure_notification(
            job_name="Weekly Provider Payment Summary Report",
            error_message=error_msg,
            exception=e
        )

def weekly_individual_provider_reports():
    """
    Weekly scheduled function to generate individual password-protected provider reports.
    
    This function:
    1. Calls the individual provider reports endpoint with weekly email type
    2. Generates individual PDF reports for each provider with cases status=15
    3. Password protects each PDF with provider_lastname_npi format
    4. Emails each provider only their own cases
    5. Uses individual provider email template with password information
    
    Runs 1 hour after weekly_provider_payment_report to ensure consolidated report is sent first.
    """
    logger.info("Starting weekly individual provider reports job...")
    
    try:
        # Call the individual provider reports endpoint with weekly email type
        response = requests.get(
            'http://localhost:8000/individual_provider_reports?email_type=weekly',
            timeout=600  # 10 minute timeout for individual report generation (longer than consolidated)
        )
        
        if response.status_code == 200:
            logger.info("✅ Weekly individual provider reports generated successfully")
            
            # Parse response JSON for detailed results
            try:
                result_data = response.json()
                providers_processed = result_data.get('providers_processed', 0)
                reports_generated = result_data.get('reports_generated', 0)
                emails_sent = result_data.get('emails_sent', 0)
                errors = result_data.get('errors', [])
                
                logger.info(f"📊 Individual provider reports summary:")
                logger.info(f"  Providers processed: {providers_processed}")
                logger.info(f"  Reports generated: {reports_generated}")
                logger.info(f"  Emails sent: {emails_sent}")
                
                if errors:
                    logger.warning(f"⚠️ {len(errors)} providers had errors:")
                    for error in errors[:5]:  # Log first 5 errors
                        logger.warning(f"  Provider {error.get('provider', 'unknown')}: {error.get('error', 'unknown error')}")
                    if len(errors) > 5:
                        logger.warning(f"  ... and {len(errors) - 5} more errors")
                else:
                    logger.info("  No errors reported")
                
                logger.info("Weekly individual provider reports job completed successfully")
                
            except Exception as json_error:
                logger.warning(f"Could not parse response JSON: {str(json_error)}")
                logger.info("✅ Weekly individual provider reports completed (response parsing failed)")
            
        else:
            logger.error(f"❌ Individual provider reports failed with status {response.status_code}")
            logger.error(f"Response: {response.text[:500]}")  # Log first 500 chars of error
            
    except requests.exceptions.Timeout:
        logger.error("❌ Individual provider reports timed out (>10 minutes)")
    except requests.exceptions.ConnectionError:
        logger.error("❌ Cannot connect to API server for individual provider reports")
    except Exception as e:
        logger.error(f"❌ Error in weekly individual provider reports job: {str(e)}")

def weekly_referral_report():
    """
    Weekly scheduled function to generate referral report and send emails.
    
    This function:
    1. Calls the referral report endpoint
    2. Generates PDF report for referral network analysis with cases status=15 (pending payment)
    3. Password protects PDF with weekly_YYYYMMDD format
    4. Automatically sends emails to configured recipients
    5. Uses weekly email template for professional notifications
    
    Runs at 09:30 UTC on Monday mornings, between the summary report and individual reports.
    """
    logger.info("Starting weekly referral report job...")
    
    try:
        # Call the referral report endpoint
        response = requests.get(
            'http://localhost:8000/referral_report',
            timeout=300  # 5 minute timeout for report generation
        )
        
        if response.status_code == 200:
            logger.info("✅ Weekly referral report generated successfully")
            
            # Log email status from response headers
            email_headers = {k: v for k, v in response.headers.items() if k.startswith('X-Email')}
            if email_headers:
                emails_sent = email_headers.get('X-Email-Count', '0')
                total_recipients = email_headers.get('X-Email-Total-Recipients', '0')
                email_success = email_headers.get('X-Email-Sent', 'False')
                
                logger.info(f"📧 Email notifications: {emails_sent}/{total_recipients} sent successfully")
                logger.info(f"📧 Email status: {email_success}")
            
            # Log S3 upload status from response headers
            s3_headers = {k: v for k, v in response.headers.items() if k.startswith('X-S3')}
            if s3_headers:
                s3_success = s3_headers.get('X-S3-Upload-Success', 'False')
                s3_url = s3_headers.get('X-S3-URL', '')
                logger.info(f"☁️ S3 upload status: {s3_success}")
                if s3_url:
                    logger.info(f"☁️ S3 URL: {s3_url}")
            
            # Log report details
            content_length = len(response.content)
            logger.info(f"📄 Report size: {content_length} bytes")
            logger.info("Weekly referral report job completed successfully")
            
        elif response.status_code == 404:
            logger.info("ℹ️ No referral data found for weekly referral report")
            
        else:
            logger.error(f"❌ Referral report failed with status {response.status_code}")
            logger.error(f"Response: {response.text[:500]}")  # Log first 500 chars of error
            
    except requests.exceptions.Timeout:
        logger.error("❌ Referral report timed out (>5 minutes)")
    except requests.exceptions.ConnectionError:
        logger.error("❌ Cannot connect to API server for referral report")
    except Exception as e:
        logger.error(f"❌ Error in weekly referral report job: {str(e)}")

def daily_database_backup():
    """
    Daily scheduled function to backup database tables.
    
    This function:
    1. Creates mysqldump backup of all tables except npi* and search_* tables
    2. Compresses the backup using gzip
    3. Stores backup in ~/vol2/db_backups directory
    4. Uploads backup to S3 bucket under /private/db_backups
    5. Cleans up old backup files (keeps 7 days)
    """
    logger.info("Starting daily database backup job...")
    
    try:
        # Perform database backup
        backup_result = perform_database_backup()
        
        if backup_result['status'] == 'success':
            logger.info("✅ Database backup completed successfully")
            logger.info(f"📄 Backup file: {backup_result['backup_filename']}")
            logger.info(f"📊 Tables backed up: {backup_result['tables_backed_up']}")
            logger.info(f"💾 File size: {backup_result['file_size_mb']:.2f} MB")
            logger.info(f"⏱️ Execution time: {backup_result['execution_time_seconds']:.2f} seconds")
            
            # Log S3 upload status
            if backup_result['s3_upload']['success']:
                logger.info(f"☁️ S3 upload successful: {backup_result['s3_upload']['s3_url']}")
            else:
                logger.warning(f"⚠️ S3 upload failed: {backup_result['s3_upload']['message']}")
            
            # Clean up old backups
            cleanup_result = cleanup_old_backups(days_to_keep=7)
            if cleanup_result['status'] == 'success' and cleanup_result['files_deleted'] > 0:
                logger.info(f"🧹 Cleaned up {cleanup_result['files_deleted']} old backup files")
            
        elif backup_result['status'] == 'error':
            logger.error(f"❌ Database backup failed: {backup_result['error']}")
            
    except Exception as e:
        logger.error(f"❌ Error in daily database backup job: {str(e)}")

def pool_cleanup_job():
    """
    Scheduled function to clean up stale database connections.
    
    This function:
    1. Removes connections that have been idle > max_idle_time (1 hour normally, 2h during AWS outages)
    2. Removes connections older than max_lifetime (4 hours normally, 8h during AWS outages)
    3. Removes invalid/stale connections
    4. Logs cleanup statistics
    
    Note: During AWS Secrets Manager outages, connection lifetimes are automatically
    extended 2x to preserve existing authenticated connections which continue to work.
    """
    logger.info("Starting database connection pool cleanup...")
    
    try:
        from core.database import cleanup_stale_connections
        
        result = cleanup_stale_connections()
        
        if result["status"] == "success":
            # Log degraded mode if active
            if result.get("secrets_degraded"):
                logger.warning("🛡️ Pool cleanup running in resilience mode - extended connection lifetimes due to AWS Secrets Manager issues")
            
            if result["cleaned"] > 0:
                logger.info(f"✅ Pool cleanup completed: removed {result['cleaned']} stale connections")
                logger.info(f"📊 Remaining in pool: {result['remaining_in_pool']}, Tracked: {result['tracked_connections']}")
            else:
                logger.info("✅ Pool cleanup completed: no stale connections found")
        else:
            logger.warning(f"⚠️ Pool cleanup status: {result['status']}")
            
    except Exception as e:
        logger.error(f"❌ Error in pool cleanup job: {str(e)}")

def pool_prewarm_job():
    """
    Scheduled function to pre-warm the database connection pool.
    
    This function:
    1. Ensures the pool has the target number of connections ready
    2. Creates new connections if needed
    3. Prepares for expected traffic increases
    4. Logs prewarming statistics
    """
    logger.info("Starting database connection pool pre-warming...")
    
    try:
        from core.database import prewarm_connection_pool
        
        # Pre-warm to full pool size (50 connections)
        result = prewarm_connection_pool(target_connections=50)
        
        if result["status"] == "success":
            if result["created"] > 0:
                logger.info(f"🔥 Pool pre-warming completed: created {result['created']} new connections")
                logger.info(f"📊 Pool size: {result['current_size']}/{result['target_size']}")
            else:
                logger.info("✅ Pool already warm: no new connections needed")
        elif result["status"] == "already_warm":
            logger.info(f"✅ Pool already warm: {result['current_size']}/{result['target_size']} connections")
        else:
            logger.warning(f"⚠️ Pool pre-warming status: {result['status']}")
            
    except Exception as e:
        logger.error(f"❌ Error in pool pre-warming job: {str(e)}")

def pool_stats_job():
    """
    Scheduled function to log database connection pool statistics.
    
    This function provides visibility into:
    1. Current pool utilization
    2. Connection ages and idle times
    3. Pool health metrics
    """
    try:
        from core.database import get_pool_stats
        
        stats = get_pool_stats()
        
        if stats.get("status") == "no_pool":
            logger.info("📊 Pool stats: No connection pool initialized")
            return
        
        logger.info("📊 Database Connection Pool Statistics:")
        logger.info(f"   Pool Size: {stats['pool_size']}/{stats['max_pool_size']} (max overflow: {stats['max_overflow']})")
        logger.info(f"   Tracked Connections: {stats['tracked_connections']}")
        
        if stats.get("avg_connection_age"):
            logger.info(f"   Avg Connection Age: {stats['avg_connection_age']:.1f}s (max: {stats['max_connection_age']:.1f}s)")
            logger.info(f"   Avg Idle Time: {stats['avg_idle_time']:.1f}s (max: {stats['max_idle_time']:.1f}s)")
            
    except Exception as e:
        logger.error(f"❌ Error in pool stats job: {str(e)}")

def secrets_warming_job():
    """
    Scheduled function to refresh the secrets cache.
    
    This function:
    1. Pre-loads all application secrets to prevent cache misses
    2. Refreshes secrets before they expire (proactive warming)
    3. Eliminates AWS API call latency during normal operations
    4. Logs warming statistics and any failures
    
    Note: This job uses graceful degradation - stale cached secrets will continue
    to be used if AWS Secrets Manager is experiencing issues.
    """
    logger.info("Starting scheduled secrets cache warming...")
    
    try:
        from utils.secrets_manager import warm_all_secrets
        
        results = warm_all_secrets()
        
        if results["failed"] == 0:
            logger.info(f"✅ Secrets warming completed: {results['successful']} secrets refreshed in {results['duration_seconds']:.2f}s")
        else:
            failure_rate = results["failed"] / results["total_secrets"]
            
            logger.warning(f"⚠️ Secrets warming partial: {results['successful']}/{results['total_secrets']} secrets refreshed")
            logger.warning(f"   Duration: {results['duration_seconds']:.2f}s, Failed: {results['failed']}")
            
            # Log failed secrets for monitoring
            failed_secrets = []
            for detail in results["details"]:
                if detail["status"] == "failed":
                    logger.error(f"   Failed secret: {detail['secret_name']} - {detail['error']}")
                    failed_secrets.append(f"{detail['secret_name']}: {detail['error']}")
            
            # Send notification if failure rate is high (>50%)
            # This indicates a likely AWS service issue
            if failure_rate > 0.5:
                from utils.job_failure_notifier import send_job_partial_failure_notification
                send_job_partial_failure_notification(
                    job_name="Secrets Cache Warming",
                    warning_message=f"High failure rate detected during secrets cache warming. {results['failed']} out of {results['total_secrets']} secrets failed to refresh. Stale cached values will continue to be used until AWS Secrets Manager recovers.",
                    stats={
                        "Total Secrets": results["total_secrets"],
                        "Successful": results["successful"],
                        "Failed": results["failed"],
                        "Duration": f"{results['duration_seconds']:.2f}s",
                        "Failed Secrets": ", ".join([s.split(":")[0] for s in failed_secrets]),
                        "Note": "Application will continue using stale cached secrets"
                    }
                )
                    
    except Exception as e:
        error_msg = f"Critical error in secrets warming job: {str(e)}"
        logger.error(f"❌ {error_msg}")
        
        # This is a critical failure - notify immediately
        from utils.job_failure_notifier import send_job_failure_notification
        send_job_failure_notification(
            job_name="Secrets Cache Warming",
            error_message=error_msg,
            exception=e
        )

def user_environment_cache_warming_job():
    """
    Scheduled function to refresh the user environment cache.
    
    This function:
    1. Pre-loads all active users' environment data to prevent cache misses
    2. Refreshes user caches before they expire (proactive warming)
    3. Eliminates database query latency during normal operations
    4. Logs warming statistics and any failures
    """
    logger.info("🔥 Starting scheduled user environment cache warming...")
    
    try:
        from endpoints.utility.get_user_environment import warm_all_user_environment_caches
        
        results = warm_all_user_environment_caches()
        
        if results.get("error"):
            logger.error(f"❌ User environment cache warming failed: {results['error']}")
        elif results["failed_warms"] == 0:
            logger.info(f"✅ User environment cache warming completed: {results['successful_warms']} users refreshed in {results['execution_time_seconds']}s")
        else:
            logger.warning(f"⚠️ User environment cache warming partial: {results['successful_warms']}/{results['total_users']} users refreshed")
            logger.warning(f"   Duration: {results['execution_time_seconds']}s, Failed: {results['failed_warms']}")
                    
    except Exception as e:
        logger.error(f"❌ Error in user environment cache warming job: {str(e)}")

def setup_weekly_scheduler(scheduler_role: str = "leader"):
    """
    Set up the scheduler based on server role.
    
    Args:
        scheduler_role: "leader" or "worker"
            - leader: Runs all scheduled jobs (business operations + maintenance)
            - worker: Runs only maintenance jobs (backups, cache/pool management)
    
    Leader schedules (business operations + maintenance):
    - daily_database_backup: Every day at 08:00 UTC (database backup)
    - weekly_pending_payment_update: Monday at 08:00 UTC (status 10 -> 15)
    - weekly_provider_payment_report: Monday at 09:00 UTC (generate consolidated report + send emails)
    - weekly_provider_payment_summary_report: Monday at 09:15 UTC (generate summary report + send emails)
    - weekly_referral_report: Monday at 09:30 UTC (generate referral network report + send emails)
    - weekly_individual_provider_reports: Monday at 10:00 UTC (generate individual provider reports + send emails)
    - weekly_npi_update: Tuesday at 08:00 UTC (NPI data refresh)
    - weekly_paid_update: Friday at 08:00 UTC (status 15 -> 20)
    - pool_cleanup_job: Every hour
    - pool_prewarm_job: Daily at 10:30 UTC
    - pool_stats_job: Daily at 17:00 UTC
    - secrets_warming_job: Every 30 minutes
    
    Worker schedules (maintenance only):
    - daily_database_backup: Every day at 08:00 UTC (database backup)
    - pool_cleanup_job: Every hour
    - pool_prewarm_job: Daily at 10:30 UTC
    - pool_stats_job: Daily at 17:00 UTC
    - secrets_warming_job: Every 30 minutes
    
    To change days/times: modify the schedule lines below
    """
    # Always schedule maintenance tasks (both leader and worker servers)
    schedule.every().hour.do(pool_cleanup_job)  # Clean up stale connections every hour
    schedule.every().day.at("10:30").do(pool_prewarm_job)  # Pre-warm pool before business hours
    schedule.every().day.at("17:00").do(pool_stats_job)  # Log pool stats
    schedule.every(30).minutes.do(secrets_warming_job)  # Refresh secrets cache every 30 minutes
    schedule.every(6).hours.do(user_environment_cache_warming_job)  # Refresh user environment cache every 6 hours
    
    # Schedule business operations only on leader server
    if scheduler_role.lower() == "leader":
        schedule.every().day.at("08:00").do(daily_database_backup)  # Database backup
        schedule.every().monday.at("08:00").do(weekly_pending_payment_update)
        schedule.every().monday.at("09:00").do(weekly_provider_payment_report)
        schedule.every().monday.at("09:15").do(weekly_provider_payment_summary_report)
        schedule.every().monday.at("09:30").do(weekly_referral_report)
        schedule.every().monday.at("10:00").do(weekly_individual_provider_reports)
        schedule.every().tuesday.at("08:00").do(weekly_npi_update)
        # schedule.every().friday.at("08:00").do(weekly_paid_update)  # Commented out - client wants to run manually
    
    logger.info(f"Scheduler configured in {scheduler_role.upper()} mode:")
    
    # Always log maintenance tasks
    logger.info("  📋 MAINTENANCE TASKS (All Servers):")
    logger.info("    - Database backup: Daily at 08:00 UTC")
    logger.info("    - Pool cleanup: Every hour")
    logger.info("    - Pool pre-warming: Daily at 10:30 UTC")
    logger.info("    - Pool statistics: Daily at 17:00 UTC")
    logger.info("    - Secrets cache warming: Every 30 minutes")
    logger.info("    - User environment cache warming: Every 6 hours")
    
    # Log business operations only for leader
    if scheduler_role.lower() == "leader":
        logger.info("  🏢 BUSINESS OPERATIONS (Leader Only):")
        logger.info("    - Pending payment update: Monday at 08:00 UTC")
        logger.info("    - Consolidated provider payment report: Monday at 09:00 UTC")
        logger.info("    - Provider payment summary report: Monday at 09:15 UTC")
        logger.info("    - Referral network report: Monday at 09:30 UTC")
        logger.info("    - Individual provider reports: Monday at 10:00 UTC")
        logger.info("    - NPI data update: Tuesday at 08:00 UTC")
        logger.info("    - Paid update: Friday at 08:00 UTC (manual)")
    else:
        logger.info("  🏢 BUSINESS OPERATIONS: Disabled (Worker Mode)")

def run_scheduler(scheduler_role: str = "leader"):
    """
    Run the scheduler in a continuous loop.
    
    Args:
        scheduler_role: "leader" or "worker" - determines which jobs to schedule
    
    This function should be called to start the scheduling service.
    It will run indefinitely, checking for scheduled jobs every hour.
    Supports graceful shutdown via signal handling.
    """
    global shutdown_requested
    
    # Note: Signal handlers can only be set up in the main thread
    # When running in background, we rely on the daemon thread behavior
    
    setup_weekly_scheduler(scheduler_role=scheduler_role)
    
    logger.info(f"Scheduler started in {scheduler_role.upper()} mode. Running continuously...")
    
    while not shutdown_requested:
        schedule.run_pending()
        
        # Sleep in smaller intervals to check shutdown flag more frequently
        for _ in range(300):  # 3600 seconds (1 hour) total
            if shutdown_requested:
                break
            time.sleep(1)  # Check shutdown flag every second
    
    logger.info("Case status scheduler shutting down gracefully...")
    sys.exit(0)

def run_scheduler_in_background(scheduler_role: str = "leader"):
    """
    Start the scheduler in a background thread.
    
    Args:
        scheduler_role: "leader" or "worker" - determines which jobs to schedule
    
    This allows the scheduler to run alongside the main FastAPI application.
    """
    scheduler_thread = threading.Thread(target=lambda: run_scheduler(scheduler_role), daemon=True)
    scheduler_thread.start()
    logger.info(f"Scheduler started in background thread ({scheduler_role.upper()} mode)")

def run_pending_payment_update_now():
    """
    Utility function to run the pending payment update immediately (for testing).
    """
    logger.info("Running pending payment update immediately...")
    weekly_pending_payment_update()

def run_paid_update_now():
    """
    Utility function to run the paid update immediately (for testing).
    """
    logger.info("Running paid update immediately...")
    weekly_paid_update()

def run_npi_update_now():
    """
    Utility function to run the NPI data update immediately (for testing).
    """
    logger.info("Running NPI data update immediately...")
    weekly_npi_update()

def run_update_now():
    """
    Utility function to run the case status update immediately (for testing).
    Kept for backward compatibility - runs the pending payment update.
    """
    logger.info("Running case status update immediately...")
    weekly_pending_payment_update()

def run_backup_now():
    """
    Utility function to run the database backup immediately (for testing).
    """
    logger.info("Running database backup immediately...")
    daily_database_backup()

def run_individual_provider_reports_now():
    """
    Utility function to run the individual provider reports immediately (for testing).
    """
    logger.info("Running individual provider reports immediately...")
    weekly_individual_provider_reports()

def run_provider_payment_report_now():
    """
    Utility function to run the consolidated provider payment report immediately (for testing).
    """
    logger.info("Running consolidated provider payment report immediately...")
    weekly_provider_payment_report()

def run_provider_payment_summary_report_now():
    """
    Utility function to run the provider payment summary report immediately (for testing).
    """
    logger.info("Running provider payment summary report immediately...")
    weekly_provider_payment_summary_report()

def run_referral_report_now():
    """
    Utility function to run the referral report immediately (for testing).
    """
    logger.info("Running referral report immediately...")
    weekly_referral_report() 