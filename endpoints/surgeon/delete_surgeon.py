# Created: 2025-07-15 09:20:13
# Last Modified: 2025-08-06 15:36:45
# Author: Scott Cadreau

# endpoints/surgeon/delete_surgeon.py
from fastapi import APIRouter, HTTPException, Query, Request
import pymysql.cursors
from core.database import get_db_connection, close_db_connection, is_connection_valid
from utils.monitoring import track_business_operation, business_metrics
import time

router = APIRouter()

@router.delete("/surgeon")
@track_business_operation("delete", "surgeon")
def delete_surgeon(request: Request, surgeon_id: int = Query(..., description="The surgeon ID to delete")):
    """
    Delete a surgeon profile by surgeon ID with comprehensive validation and monitoring.
    
    This endpoint provides secure surgeon deletion functionality including:
    - Surgeon existence validation before deletion
    - Permanent record removal from database
    - Comprehensive monitoring and business metrics tracking
    - Transaction safety with proper rollback handling
    - Full request logging and execution time tracking
    - Prometheus metrics integration for operational monitoring
    - Proper error handling for non-existent surgeons
    
    Args:
        request (Request): FastAPI request object for logging and monitoring
        surgeon_id (int): The unique identifier of the surgeon to delete
    
    Returns:
        dict: Response containing:
            - statusCode (int): HTTP status code (200 for successful deletion)
            - body (dict): Response data including:
                - message (str): Success confirmation message
                - surgeon_id (int): The ID of the deleted surgeon
    
    Raises:
        HTTPException: 
            - 404 Not Found: Surgeon with the specified surgeon_id does not exist
            - 500 Internal Server Error: Database deletion failures or connection issues
    
    Database Operations:
        - Performs DELETE operation on 'surgeon_list' table
        - Validates surgeon existence by checking cursor.rowcount
        - Commits transaction immediately after successful deletion
        - Automatic rollback on any operation failure
    
    Monitoring & Logging:
        - Business metrics tracking for surgeon deletion operations
        - Prometheus monitoring via @track_business_operation decorator
        - Records success/error/not_found metrics via business_metrics.record_surgeon_operation()
        - Comprehensive request logging with execution time tracking
        - Error logging with full exception details and rollback status
    
    Transaction Handling:
        - Explicit transaction commit after successful deletion
        - Automatic rollback on any operation failure with connection validation
        - Proper connection cleanup in finally block
        - Safe rollback handling with interface error protection
    
    Validation:
        - Checks if surgeon exists before attempting deletion
        - Returns 404 error if surgeon not found (cursor.rowcount == 0)
        - Prevents silent failures with proper existence validation
    
    Example:
        DELETE /surgeon?surgeon_id=123
        
        Success Response:
        {
            "statusCode": 200,
            "body": {
                "message": "Surgeon deleted successfully",
                "surgeon_id": 123
            }
        }
        
        Not Found Response (404):
        {
            "error": "Surgeon not found",
            "surgeon_id": 123
        }
    
    Note:
        - Deletion is permanent and cannot be undone
        - Surgeon ID must be a valid integer
        - No user validation is performed (any user can delete any surgeon)
        - Consider implementing soft delete for audit trail requirements
        - Ensure no active cases reference this surgeon before deletion
        - Verify surgeon is not associated with critical medical procedures
    """
    conn = None
    start_time = time.time()
    response_status = 200
    response_data = None
    error_message = None
    
    try:
        conn = get_db_connection()
        
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute("DELETE FROM surgeon_list WHERE surgeon_id = %s", (surgeon_id,))
            if cursor.rowcount == 0:
                # Record failed surgeon deletion (not found)
                business_metrics.record_surgeon_operation("delete", "not_found", surgeon_id)
                response_status = 404
                error_message = "Surgeon not found"
                raise HTTPException(status_code=404, detail={"error": "Surgeon not found", "surgeon_id": surgeon_id})
            conn.commit()

            # Record successful surgeon deletion
            business_metrics.record_surgeon_operation("delete", "success", surgeon_id)
            
        response_data = {
            "statusCode": 200,
            "body": {
                "message": "Surgeon deleted successfully",
                "surgeon_id": surgeon_id
            }
        }
        return response_data
        
    except HTTPException as http_error:
        # Re-raise HTTP exceptions and capture error details
        response_status = http_error.status_code
        error_message = str(http_error.detail)
        raise
    except Exception as e:
        # Record failed surgeon deletion
        response_status = 500
        error_message = str(e)
        business_metrics.record_surgeon_operation("delete", "error", surgeon_id)
        
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
            user_id=None,  # No user_id available in surgeon deletion
            response_data=response_data,
            error_message=error_message
        )
        
        # Always close the connection
        if conn:
            close_db_connection(conn)