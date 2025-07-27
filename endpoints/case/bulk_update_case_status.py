# Created: 2025-07-27 02:00:40
# Last Modified: 2025-07-27 02:00:42
# Author: Scott Cadreau

# endpoints/case/bulk_update_case_status.py
from fastapi import APIRouter, HTTPException, Body, Request
import pymysql.cursors
import pymysql
import logging
import time
from typing import List, Dict, Any
from core.database import get_db_connection, close_db_connection
from core.models import BulkCaseStatusUpdate
from utils.monitoring import track_business_operation, business_metrics

logger = logging.getLogger(__name__)

router = APIRouter()

@router.patch("/bulkupdatecasestatus")
@track_business_operation("bulk_update", "case_status")
def bulk_update_case_status(request: Request, update_request: BulkCaseStatusUpdate = Body(...)) -> Dict[str, Any]:
    """
    Bulk update case status for multiple cases.
    
    This function updates the case_status for a list of case IDs to a new status value.
    It performs validation to prevent backward status progression unless explicitly forced.
    
    Args:
        update_request: BulkCaseStatusUpdate object containing:
            - case_ids: List of case IDs to update
            - new_status: The new status value to set
            - force: Optional boolean to allow backward status progression (default: False)
    
    Returns:
        Dict containing:
            - updated_cases: List of successfully updated case IDs
            - exceptions: List of cases that couldn't be updated with reasons
            - total_processed: Total number of cases processed
            - total_updated: Total number of cases successfully updated
            - total_exceptions: Total number of cases with exceptions
    
    Status Progression Logic:
        - Prevents updating to a lower status value unless force=True
        - Higher status values indicate more advanced case progression
        - When force=True, allows "undoing" mistakes by moving to lower status
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
                        
                        # Update the case status
                        cursor.execute("""
                            UPDATE cases 
                            SET case_status = %s 
                            WHERE case_id = %s AND active = 1
                        """, (update_request.new_status, case_id))
                        
                        if cursor.rowcount > 0:
                            result["updated_cases"].append({
                                "case_id": case_id,
                                "previous_status": current_status,
                                "new_status": update_request.new_status,
                                "forced": update_request.force and current_status > update_request.new_status
                            })
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