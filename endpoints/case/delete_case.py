# Created: 2025-07-15 09:20:13
# Last Modified: 2025-08-06 15:15:22
# Author: Scott Cadreau

# endpoints/case/delete_case.py
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse
import pymysql.cursors
import json
import datetime as dt
import time
from core.database import get_db_connection, close_db_connection, is_connection_valid
from utils.monitoring import track_business_operation, business_metrics
from utils.archive_deleted_case import archive_deleted_case

router = APIRouter()

@router.delete("/case")
@track_business_operation("delete", "case")
def delete_case(request: Request, case_id: str = Query(..., description="The case ID to delete")):
    """
    Soft delete (deactivate) a surgical case with comprehensive archiving and rollback capabilities.
    
    This endpoint performs a soft deletion by setting the case's active status to 0 rather than 
    permanently removing the record. The operation includes automatic archiving of case files
    to AWS S3 with rollback capabilities if archiving fails.
    
    Key Features:
    - Soft deletion (sets active=0) for data preservation
    - Automatic case file archiving to AWS S3
    - Full rollback on archiving failure
    - Duplicate deletion protection
    - Comprehensive monitoring and logging
    - Prometheus metrics tracking
    
    Args:
        request (Request): FastAPI request object for logging and monitoring
        case_id (str): Unique identifier of the case to delete (required query parameter)
    
    Returns:
        dict: Response containing:
            - statusCode (int): HTTP status code (200 for success)
            - body (dict): Response body with:
                - message (str): Success or status message
                - case_id (str): The case identifier that was processed
                - active (int): Current active status (0 after successful deletion)
                - deactivated_at (str, optional): ISO timestamp of deactivation
                - details (str, optional): Additional information for error cases
    
    Raises:
        HTTPException:
            - 400 Bad Request: Missing case_id parameter
            - 404 Not Found: Case does not exist in the database
            - 500 Internal Server Error: Database errors or archiving failures
    
    Database Operations:
        1. Validates case existence and retrieves current active status
        2. Checks for already inactive cases (returns success with notice)
        3. Sets active=0 to soft delete the case
        4. Commits the transaction before archiving
        5. Attempts case file archiving via archive_deleted_case()
        6. Rolls back deletion if archiving fails
    
    Archiving Process:
        - Moves case files from active storage to archive storage in AWS S3
        - Updates file paths in database to reflect archived locations
        - Handles all file types: demo_file, note_file, misc_file
        - Performs atomic rollback if any archiving step fails
    
    Business Logic:
        - Cases already marked as inactive return success without changes
        - Archiving failure triggers automatic rollback of the soft deletion
        - All operations are logged for audit and monitoring purposes
        - Case restoration possible if archiving fails
    
    Monitoring & Logging:
        - Business metrics for deletion success/failure tracking
        - Prometheus monitoring via @track_business_operation decorator
        - Detailed execution time and response logging
        - Specific error tracking for different failure scenarios:
            * not_found: Case doesn't exist
            * already_inactive: Case was already deleted
            * update_failed: Database update failed
            * archive_failed: S3 archiving failed
            * error: General errors
    
    Error Handling:
        - Graceful handling of already inactive cases
        - Automatic rollback on archiving failures
        - Detailed error messages with context
        - Connection state validation before rollback attempts
    
    Example Response (Success):
        {
            "statusCode": 200,
            "body": {
                "message": "Case deactivated successfully",
                "case_id": "CASE-2024-001",
                "active": 0,
                "deactivated_at": "2024-01-15T10:30:00+00:00"
            }
        }
    
    Example Response (Already Inactive):
        {
            "statusCode": 200,
            "body": {
                "message": "Case already inactive", 
                "case_id": "CASE-2024-001",
                "active": 0
            }
        }
    
    Example Response (Archive Failure):
        {
            "statusCode": 500,
            "body": {
                "error": "Case deletion failed during archive/S3 operations: S3 bucket not accessible",
                "case_id": "CASE-2024-001",
                "details": "Case has been restored to active status"
            }
        }
    
    Note:
        - This is a soft delete operation - data is preserved for recovery
        - Archiving includes movement of all associated files to AWS S3 archive storage
        - Failed archiving automatically restores the case to active status
        - All file operations are atomic - either all succeed or all are rolled back
        - Case files in S3 are moved to archive buckets with updated database references
    """
    conn = None
    start_time = time.time()
    response_status = 200
    response_data = None
    error_message = None
    
    try:
        if not case_id:
            response_status = 400
            error_message = "Missing case_id parameter"
            raise HTTPException(status_code=400, detail="Missing case_id parameter")

        print(f"INFO: Connecting to database")
        conn = get_db_connection()
        print("INFO: Database connection established successfully")

        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            # First check if case exists and get current status
            cursor.execute("""SELECT case_id, active FROM cases WHERE case_id = %s""", (case_id,))
            case_data = cursor.fetchone()

            if not case_data:
                print(f"ERROR: Case not found - case_id: {case_id}")
                # Record failed case deletion (not found)
                business_metrics.record_case_operation("delete", "not_found", case_id)
                response_status = 404
                error_message = "Case not found"
                response_data = {
                    "statusCode": 404,
                    "body": {"error": "Case not found", "case_id": case_id}
                }
                return response_data

            current_active_status = case_data.get('active')
            print(f"INFO: Case found - case_id: {case_id}, current active status: {current_active_status}")

            # Check if case is already inactive
            if current_active_status == 0:
                print(f"WARNING: Case already inactive - case_id: {case_id}")
                # Record case deletion (already inactive)
                business_metrics.record_case_operation("delete", "already_inactive", case_id)
                response_data = {
                    "statusCode": 200,
                    "body": {
                        "message": "Case already inactive",
                        "case_id": case_id,
                        "active": 0
                    }
                }
                return response_data

            # Soft delete: set active = 0
            cursor.execute("""UPDATE cases SET active = 0 WHERE case_id = %s""", (case_id,))

            # Check if update was successful
            if cursor.rowcount == 0:
                print(f"ERROR: Failed to update case active status - case_id: {case_id}")
                # Record failed case deletion
                business_metrics.record_case_operation("delete", "update_failed", case_id)
                response_status = 500
                error_message = "Failed to deactivate case"
                response_data = {
                    "statusCode": 500,
                    "body": {"error": "Failed to deactivate case", "case_id": case_id}
                }
                return response_data

            print(f"SUCCESS: Case soft deleted (deactivated) - case_id: {case_id}, rows affected: {cursor.rowcount}")

            # Commit the transaction
            conn.commit()
            
            # Record successful case deletion
            business_metrics.record_case_operation("delete", "success", case_id)

            # Archive the deleted case
            # Note: This includes S3 file movement and will raise exceptions on failure
            try:
                archive_deleted_case(case_id)
            except Exception as archive_error:
                # If archiving (including S3 movement) fails, we need to rollback the soft delete
                print(f"ERROR: Archive operation failed for case {case_id}: {str(archive_error)}")
                
                # Rollback the soft delete by setting active = 1
                try:
                    cursor.execute("""UPDATE cases SET active = 1 WHERE case_id = %s""", (case_id,))
                    conn.commit()
                    print(f"INFO: Rolled back case soft delete due to archive failure - case_id: {case_id}")
                except Exception as rollback_error:
                    print(f"CRITICAL: Failed to rollback case soft delete - case_id: {case_id}, error: {str(rollback_error)}")
                
                # Record failed case deletion due to archive/S3 failure
                business_metrics.record_case_operation("delete", "archive_failed", case_id)
                
                response_status = 500
                error_message = f"Case deletion failed during archive/S3 operations: {str(archive_error)}"
                response_data = {
                    "statusCode": 500,
                    "body": {
                        "error": f"Case deletion failed during archive/S3 operations: {str(archive_error)}",
                        "case_id": case_id,
                        "details": "Case has been restored to active status"
                    }
                }
                return response_data

        response_data = {
            "statusCode": 200,
            "body": {
                "message": "Case deactivated successfully",
                "case_id": case_id,
                "active": 0,
                "deactivated_at": dt.datetime.now(dt.timezone.utc).isoformat()
            }
        }
        return response_data

    except HTTPException as http_error:
        # Re-raise HTTP exceptions and capture error details
        response_status = http_error.status_code
        error_message = str(http_error.detail)
        raise
    except Exception as e:
        # Record failed case deletion
        response_status = 500
        error_message = str(e)
        business_metrics.record_case_operation("delete", "error", case_id)
        
        # Safe rollback with connection state check
        if conn and is_connection_valid(conn):
            try:
                conn.rollback()
            except (pymysql.err.InterfaceError, pymysql.err.OperationalError) as rollback_error:
                # Log rollback error but don't raise it
                print(f"Rollback failed: {rollback_error}")
        raise HTTPException(status_code=500, detail={"error": str(e)})
        
    finally:
        # Calculate execution time
        execution_time_ms = int((time.time() - start_time) * 1000)
        
        # Log request details for monitoring using the utility function
        from endpoints.utility.log_request import log_request_from_endpoint
        log_request_from_endpoint(
            request=request,
            execution_time_ms=execution_time_ms,
            response_status=response_status,
            user_id=None,  # No user_id available in delete case endpoint
            response_data=response_data,
            error_message=error_message
        )
        
        # Always close the connection
        if conn:
            close_db_connection(conn)