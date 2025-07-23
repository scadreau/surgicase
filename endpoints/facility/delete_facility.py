# Created: 2025-07-15 09:20:13
# Last Modified: 2025-07-23 12:16:57

# endpoints/facility/delete_facility.py
from fastapi import APIRouter, HTTPException, Query, Request
import pymysql.cursors
import pymysql
from core.database import get_db_connection, close_db_connection, is_connection_valid
from utils.monitoring import track_business_operation, business_metrics
import time

router = APIRouter()

@router.delete("/facility")
@track_business_operation("delete", "facility")
def delete_facility(request: Request, facility_id: int = Query(..., description="The facility ID to delete")):
    """
    Delete a facility by facility_id.
    """
    conn = None
    start_time = time.time()
    response_status = 200
    response_data = None
    error_message = None
    
    try:
        conn = get_db_connection()
        
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute("DELETE FROM facility_list WHERE facility_id = %s", (facility_id,))
            if cursor.rowcount == 0:
                # Record failed facility deletion (not found)
                business_metrics.record_facility_operation("delete", "not_found", facility_id)
                response_status = 404
                error_message = "Facility not found"
                raise HTTPException(status_code=404, detail={"error": "Facility not found", "facility_id": facility_id})
            conn.commit()

            # Record successful facility deletion
            business_metrics.record_facility_operation("delete", "success", facility_id)
            
        response_data = {
            "statusCode": 200,
            "body": {
                "message": "Facility deleted successfully",
                "facility_id": facility_id
            }
        }
        return response_data
        
    except HTTPException as http_error:
        # Re-raise HTTP exceptions and capture error details
        response_status = http_error.status_code
        error_message = str(http_error.detail)
        raise
    except Exception as e:
        # Record failed facility deletion
        response_status = 500
        error_message = str(e)
        business_metrics.record_facility_operation("delete", "error", facility_id)
        
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
            user_id=None,  # No user_id available in facility deletion
            response_data=response_data,
            error_message=error_message
        )
        
        # Always close the connection
        if conn:
            close_db_connection(conn)