# Created: 2025-07-15 09:20:13
# Last Modified: 2025-07-29 02:21:41
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
    Delete a surgeon by surgeon_id.
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