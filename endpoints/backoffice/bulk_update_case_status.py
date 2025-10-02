# Created: 2025-07-27 02:00:40
# Last Modified: 2025-10-02 20:29:58
# Author: Scott Cadreau

# endpoints/backoffice/bulk_update_case_status.py
from fastapi import APIRouter, HTTPException, Body, Request
import pymysql.cursors
import logging
import time
import threading
from typing import List, Dict, Any, Tuple
from core.database import get_db_connection, close_db_connection
from core.models import BulkCaseStatusUpdate
from utils.monitoring import track_business_operation, business_metrics

logger = logging.getLogger(__name__)

router = APIRouter()

# Configuration mapping for status codes to timestamp fields
# Format: status_code: timestamp_field_name
# Timestamps are updated whenever a case transitions TO the specified status
STATUS_TIMESTAMP_MAPPING = {
    7: "billable_flag_ts",
    8: "docs_needed_ts",
    15: "pending_payment_ts",
    20: "paid_to_provider_ts",
    30: "sent_to_biller_ts",
    40: "received_pmnt_ts",
    50: "sent_to_negotiation_ts",
    60: "settled_ts",
    70: "send_to_idr_ts",
    80: "idr_decision_ts",
    400: "rejected_ts",
    500: "closed_ts",
    # Add future timestamp mappings here as needed
}

def get_timestamp_field_for_status(to_status: int) -> str:
    """
    Get the timestamp field name for a target status.
    
    Args:
        to_status: Target case status
        
    Returns:
        str: Timestamp field name or None if no mapping exists
    """
    return STATUS_TIMESTAMP_MAPPING.get(to_status)

def build_update_query_with_timestamps(timestamp_field: str = None) -> str:
    """
    Build the UPDATE query with optional timestamp field.
    
    Args:
        timestamp_field: Name of the timestamp field to update, or None for status-only update
        
    Returns:
        str: Complete SQL UPDATE query
    """
    if timestamp_field:
        return f"""
            UPDATE cases 
            SET case_status = %s, {timestamp_field} = CURRENT_TIMESTAMP 
            WHERE case_id = %s AND active = 1
        """
    else:
        return """
            UPDATE cases 
            SET case_status = %s 
            WHERE case_id = %s AND active = 1
        """

@router.patch("/bulk_update_case_status")
@track_business_operation("bulk_update", "case_status")
def bulk_update_case_status(request: Request, update_request: BulkCaseStatusUpdate = Body(...)) -> Dict[str, Any]:
    """
    Bulk update case status for multiple cases with intelligent cache management.
    
    This function updates the case_status for a list of case IDs to a new status value.
    It performs validation to prevent backward status progression unless explicitly forced.
    Additionally updates specific timestamps based on target status values and
    automatically invalidates and re-warms relevant caches to ensure data consistency.
    
    Current timestamp mappings (updated when transitioning TO these statuses):
    - Status 15: Updates pending_payment_ts
    - Status 20: Updates paid_to_provider_ts
    - Status 30: Updates sent_to_biller_ts
    - Status 40: Updates received_pmnt_ts
    - Status 50: Updates sent_to_negotiation_ts
    - Status 60: Updates settled_ts
    - Status 70: Updates send_to_idr_ts
    - Status 80: Updates idr_decision_ts
    - Status 500: Updates closed_ts
    
    Args:
        update_request: BulkCaseStatusUpdate object containing:
            - case_ids: List of case IDs to update
            - new_status: The new status value to set
            - force: Optional boolean to allow backward status progression (default: False)
    
    Returns:
        Dict containing:
            - updated_cases: List of successfully updated case IDs with timestamp info
            - exceptions: List of cases that couldn't be updated with reasons
            - total_processed: Total number of cases processed
            - total_updated: Total number of cases successfully updated
            - total_exceptions: Total number of cases with exceptions
    
    Status Progression Logic:
        - Prevents updating to a lower status value unless force=True
        - Higher status values indicate more advanced case progression
        - When force=True, allows "undoing" mistakes by moving to lower status
        
    Timestamp Updates:
        - Automatically updates appropriate timestamp fields based on STATUS_TIMESTAMP_MAPPING
        - Timestamps are updated whenever transitioning TO a mapped status, regardless of previous status
        - New mappings can be added to STATUS_TIMESTAMP_MAPPING without code changes
    
    Cache Management:
        - Automatically clears global cases cache (get_cases_by_status) after successful updates
        - Spawns background thread to re-warm global cache with common filter combinations
        - Identifies affected users and invalidates their individual case caches (filter_cases)
        - Spawns background threads to re-warm user-specific caches for optimal performance
        - Cache operations are non-blocking and won't fail the main operation if they encounter errors
        - Comprehensive logging of all cache operations for monitoring and debugging
    """
    conn = None
    start_time = time.time()
    response_status = 200
    response_data = None
    error_message = None
    
    # Initialize response structure
    result = {
        "updated_cases": [],
        "exceptions": [],
        "total_processed": 0,
        "total_updated": 0,
        "total_exceptions": 0
    }
    
    try:
        # Input validation
        if not update_request.case_ids:
            response_status = 400
            error_message = "case_ids list cannot be empty"
            raise HTTPException(status_code=400, detail="case_ids list cannot be empty")
        
        if update_request.new_status < 0:
            response_status = 400
            error_message = "new_status must be a non-negative integer"
            raise HTTPException(status_code=400, detail="new_status must be a non-negative integer")
        
        # Remove duplicates while preserving order
        unique_case_ids = list(dict.fromkeys(update_request.case_ids))
        result["total_processed"] = len(unique_case_ids)
        
        conn = get_db_connection()
        
        # Start transaction
        conn.begin()
        
        try:
            with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                # Process each case
                for case_id in unique_case_ids:
                    try:
                        # Check if case exists and get current status
                        cursor.execute("""
                            SELECT case_id, case_status 
                            FROM cases 
                            WHERE case_id = %s AND active = 1
                        """, (case_id,))
                        
                        case_data = cursor.fetchone()
                        
                        if not case_data:
                            result["exceptions"].append({
                                "case_id": case_id,
                                "reason": "Case not found or inactive",
                                "current_status": None,
                                "attempted_status": update_request.new_status
                            })
                            continue
                        
                        current_status = case_data["case_status"]
                        
                        # Check for backward progression
                        if current_status > update_request.new_status and not update_request.force:
                            result["exceptions"].append({
                                "case_id": case_id,
                                "reason": "Cannot update to lower status without force=true",
                                "current_status": current_status,
                                "attempted_status": update_request.new_status
                            })
                            continue
                        
                        # Check if status is already at the target
                        if current_status == update_request.new_status:
                            result["exceptions"].append({
                                "case_id": case_id,
                                "reason": "Case status already at target value",
                                "current_status": current_status,
                                "attempted_status": update_request.new_status
                            })
                            continue
                        
                        # Determine if we need to update timestamps based on target status
                        timestamp_field = get_timestamp_field_for_status(update_request.new_status)
                        
                        # Build the UPDATE query dynamically
                        update_query = build_update_query_with_timestamps(timestamp_field)
                        
                        # Update the case status (and timestamps if applicable)
                        cursor.execute(update_query, (update_request.new_status, case_id))
                        
                        if cursor.rowcount > 0:
                            # Prepare the response object with timestamp update information
                            update_info = {
                                "case_id": case_id,
                                "previous_status": current_status,
                                "new_status": update_request.new_status,
                                "forced": update_request.force and current_status > update_request.new_status
                            }
                            
                            # Add timestamp update information if applicable
                            if timestamp_field:
                                update_info["timestamp_updated"] = {
                                    "field": timestamp_field,
                                    "transition": f"{current_status} → {update_request.new_status}"
                                }
                            
                            result["updated_cases"].append(update_info)
                        else:
                            result["exceptions"].append({
                                "case_id": case_id,
                                "reason": "Failed to update case status",
                                "current_status": current_status,
                                "attempted_status": update_request.new_status
                            })
                    
                    except Exception as case_error:
                        logger.error(f"Error processing case {case_id}: {str(case_error)}")
                        result["exceptions"].append({
                            "case_id": case_id,
                            "reason": f"Processing error: {str(case_error)}",
                            "current_status": None,
                            "attempted_status": update_request.new_status
                        })
                
                # Update result totals
                result["total_updated"] = len(result["updated_cases"])
                result["total_exceptions"] = len(result["exceptions"])
                
                # Record business metrics
                if result["total_updated"] > 0:
                    business_metrics.record_case_operation("bulk_update_status", "success", f"{result['total_updated']}_cases")
                
                if result["total_exceptions"] > 0:
                    business_metrics.record_case_operation("bulk_update_status", "partial_failure", f"{result['total_exceptions']}_exceptions")
                
                # Commit transaction
                conn.commit()
                
                # Invalidate and re-warm caches after successful bulk update
                if result["total_updated"] > 0:
                    try:
                        # 1. Clear and re-warm global cases cache (affects admin dashboard)
                        from endpoints.backoffice.get_cases_by_status import clear_cases_cache, warm_cases_cache
                        clear_cases_cache()  # Clear all cached data
                        logger.info(f"Cleared global cases cache after bulk status update of {result['total_updated']} cases")
                        
                        # Spawn background thread to re-warm global cache
                        threading.Thread(
                            target=warm_cases_cache,
                            daemon=True,
                            name="bulk_update_cache_rewarm_global"
                        ).start()
                        logger.info("Started background re-warming of global cases cache")
                        
                        # 2. Get unique user_ids from updated cases and invalidate their caches
                        from endpoints.case.filter_cases import invalidate_and_rewarm_user_cache
                        
                        # Extract unique user_ids from successfully updated cases
                        updated_case_ids = [case["case_id"] for case in result["updated_cases"]]
                        if updated_case_ids:
                            # Query to get user_ids for the updated cases
                            placeholders = ','.join(['%s'] * len(updated_case_ids))
                            cursor.execute(f"""
                                SELECT DISTINCT user_id 
                                FROM cases 
                                WHERE case_id IN ({placeholders}) AND active = 1
                            """, updated_case_ids)
                            
                            affected_users = cursor.fetchall()
                            
                            # Invalidate and re-warm cache for each affected user
                            for user_row in affected_users:
                                user_id = user_row['user_id']
                                invalidate_and_rewarm_user_cache(user_id)
                                logger.debug(f"Invalidated and re-warmed cache for user: {user_id}")
                            
                            logger.info(f"Invalidated user caches for {len(affected_users)} affected users")
                            
                    except Exception as cache_error:
                        # Don't fail the main operation if cache operations fail
                        logger.warning(f"Cache invalidation failed after bulk status update: {str(cache_error)}")
                
                response_data = result
                
                return result
        
        except Exception as db_error:
            # Rollback transaction on error
            conn.rollback()
            logger.error(f"Database error in bulk_update_case_status: {str(db_error)}")
            
            # Record failed operation
            business_metrics.record_case_operation("bulk_update_status", "failure", "database_error")
            
            response_status = 500
            error_message = "Database error occurred"
            raise HTTPException(status_code=500, detail=f"Database error: {str(db_error)}")
    
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        logger.error(f"Unexpected error in bulk_update_case_status: {str(e)}")
        
        # Record failed operation
        business_metrics.record_case_operation("bulk_update_status", "failure", "unexpected_error")
        
        response_status = 500
        error_message = "Internal server error"
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")
    
    finally:
        # Close database connection
        if conn:
            try:
                close_db_connection(conn)
            except Exception as close_error:
                logger.error(f"Error closing database connection: {str(close_error)}")
        
        # Record timing metrics
        execution_time = time.time() - start_time
        business_metrics.record_timing("bulk_update_case_status", execution_time * 1000)  # Convert to milliseconds
        
        # Calculate execution time in milliseconds for logging
        execution_time_ms = int((time.time() - start_time) * 1000)
        
        # Log request details for monitoring using the utility function
        from endpoints.utility.log_request import log_request_from_endpoint
        log_request_from_endpoint(
            request=request,
            execution_time_ms=execution_time_ms,
            response_status=response_status,
            user_id=None,
            response_data=response_data,
            error_message=error_message
        ) 