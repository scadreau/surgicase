# Created: 2025-07-15 09:20:13
# Last Modified: 2025-07-29 02:21:35
# Author: Scott Cadreau

# endpoints/surgeon/get_surgeons.py
from fastapi import APIRouter, HTTPException, Query, Request
import pymysql.cursors
from core.database import get_db_connection, close_db_connection
from utils.monitoring import track_business_operation, business_metrics
import time

router = APIRouter()

@router.get("/surgeons")
@track_business_operation("get", "surgeon")
def get_surgeons(request: Request, user_id: str = Query(..., description="The user ID to retrieve surgeons for")):
    """
    Get all surgeons for a user_id.
    """
    conn = None
    start_time = time.time()
    response_status = 200
    response_data = None
    error_message = None
    
    try:
        conn = get_db_connection()
        
        try:
            with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                cursor.execute(
                    "SELECT surgeon_id, first_name, last_name, surgeon_npi, surgeon_addr, surgeon_city, surgeon_state, surgeon_zip FROM surgeon_list WHERE user_id = %s",
                    (user_id,)
                )
                surgeons = cursor.fetchall()

                # Record successful surgeon retrieval
                business_metrics.record_surgeon_operation("get", "success", None)
                
        finally:
            close_db_connection(conn)
            
        response_data = {
            "user_id": user_id,
            "surgeons": surgeons
        }
        return response_data
        
    except HTTPException as http_error:
        # Re-raise HTTP exceptions and capture error details
        response_status = http_error.status_code
        error_message = str(http_error.detail)
        raise
    except Exception as e:
        # Record failed surgeon retrieval
        response_status = 500
        error_message = str(e)
        business_metrics.record_surgeon_operation("get", "error", None)
        
        if 'conn' in locals():
            close_db_connection(conn)
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
            user_id=user_id,
            response_data=response_data,
            error_message=error_message
        )