# Created: 2025-01-15
# Last Modified: 2025-08-03 15:02:17
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
            logger.error(f"❌ Provider payment report failed with status {response.status_code}")
            logger.error(f"Response: {response.text[:500]}")  # Log first 500 chars of error
            
    except requests.exceptions.Timeout:
        logger.error("❌ Provider payment report timed out (>5 minutes)")
    except requests.exceptions.ConnectionError:
        logger.error("❌ Cannot connect to API server for provider payment report")
    except Exception as e:
        logger.error(f"❌ Error in weekly provider payment report job: {str(e)}")

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

def setup_weekly_scheduler():
    """
    Set up the weekly scheduler for case status updates, NPI data updates, and daily backups.
    
    Schedules all update functions:
    - daily_database_backup: Every day at 08:00 UTC (database backup)
    - weekly_pending_payment_update: Monday at 08:00 UTC (status 10 -> 15)
    - weekly_provider_payment_report: Monday at 08:30 UTC (generate report + send emails)
    - weekly_npi_update: Tuesday at 08:00 UTC (NPI data refresh)
    - weekly_paid_update: Thursday at 08:00 UTC (status 15 -> 20)
    
    To change days/times: modify the schedule lines below
    """
    # Schedule daily database backup at 08:00 UTC
    schedule.every().day.at("08:00").do(daily_database_backup)
    
    # Schedule pending payment update for Monday at 08:00 UTC
    schedule.every().monday.at("08:00").do(weekly_pending_payment_update)
    
    # Schedule provider payment report for Monday at 08:30 UTC (30 minutes after status update)
    schedule.every().monday.at("09:00").do(weekly_provider_payment_report)
    
    # Schedule NPI data update for Tuesday at 08:00 UTC
    schedule.every().tuesday.at("08:00").do(weekly_npi_update)
    
    # Schedule paid update for Thursday at 08:00 UTC
    schedule.every().thursday.at("08:00").do(weekly_paid_update)
    
    logger.info("Scheduler configured:")
    logger.info("  - Database backup: Daily at 08:00 UTC")
    logger.info("  - Pending payment update: Monday at 08:00 UTC")
    logger.info("  - Provider payment report: Monday at 08:30 UTC")
    logger.info("  - NPI data update: Tuesday at 08:00 UTC")
    logger.info("  - Paid update: Thursday at 08:00 UTC")

def run_scheduler():
    """
    Run the scheduler in a continuous loop.
    
    This function should be called to start the scheduling service.
    It will run indefinitely, checking for scheduled jobs every hour.
    Supports graceful shutdown via signal handling.
    """
    global shutdown_requested
    
    # Set up signal handlers for graceful shutdown
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
    setup_weekly_scheduler()
    
    logger.info("Case status scheduler started. Running continuously...")
    
    while not shutdown_requested:
        schedule.run_pending()
        
        # Sleep in smaller intervals to check shutdown flag more frequently
        for _ in range(3600):  # 3600 seconds (1 hour) total
            if shutdown_requested:
                break
            time.sleep(1)  # Check shutdown flag every second
    
    logger.info("Case status scheduler shutting down gracefully...")
    sys.exit(0)

def run_scheduler_in_background():
    """
    Start the scheduler in a background thread.
    
    This allows the scheduler to run alongside the main FastAPI application.
    """
    scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
    scheduler_thread.start()
    logger.info("Case status scheduler started in background thread")

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