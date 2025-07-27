# Created: 2025-01-15
# Last Modified: 2025-07-27 04:48:09
# Author: Scott Cadreau

import schedule
import time
import threading
import logging
import pymysql.cursors
from typing import List, Dict, Any
from core.database import get_db_connection, close_db_connection
from core.models import BulkCaseStatusUpdate
from endpoints.case.bulk_update_case_status import bulk_update_case_status
from fastapi import Request
from unittest.mock import Mock

logger = logging.getLogger(__name__)

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

def setup_weekly_scheduler():
    """
    Set up the weekly scheduler for case status updates.
    
    Schedules both weekly update functions:
    - weekly_pending_payment_update: Monday at 08:00 UTC (status 10 -> 15)
    - weekly_paid_update: Thursday at 08:00 UTC (status 15 -> 20)
    
    To change days/times: modify the schedule lines below
    """
    # Schedule pending payment update for Monday at 08:00 UTC
    schedule.every().monday.at("08:00").do(weekly_pending_payment_update)
    
    # Schedule paid update for Thursday at 08:00 UTC
    schedule.every().thursday.at("08:00").do(weekly_paid_update)
    
    logger.info("Weekly case status update scheduler configured:")
    logger.info("  - Pending payment update: Monday at 08:00 UTC")
    logger.info("  - Paid update: Thursday at 08:00 UTC")

def run_scheduler():
    """
    Run the scheduler in a continuous loop.
    
    This function should be called to start the scheduling service.
    It will run indefinitely, checking for scheduled jobs every hour.
    """
    setup_weekly_scheduler()
    
    logger.info("Case status scheduler started. Running continuously...")
    
    while True:
        schedule.run_pending()
        time.sleep(3600)  # Check every hour (3600 seconds)

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

def run_update_now():
    """
    Utility function to run the case status update immediately (for testing).
    Kept for backward compatibility - runs the pending payment update.
    """
    logger.info("Running case status update immediately...")
    weekly_pending_payment_update() 