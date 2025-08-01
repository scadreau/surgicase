# Created: 2025-07-15 09:20:13
# Last Modified: 2025-07-29 02:20:24
# Author: Scott Cadreau

# endpoints/utility/get_doctypes.py
from fastapi import APIRouter, HTTPException, Request
import pymysql.cursors
from core.database import get_db_connection, close_db_connection
from utils.monitoring import track_business_operation, business_metrics
import time

router = APIRouter()

@router.get("/doctypes")
@track_business_operation("get", "doctypes")
def get_doc_types(request: Request):
    """
    Get all document types.
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
                    "SELECT doc_type FROM user_doc_type_list"
                )
                doc_types = cursor.fetchall()

                # Record successful document types retrieval
                business_metrics.record_utility_operation("get_doctypes", "success")
                
        finally:
            close_db_connection(conn)
            
        response_data = {
            "document_types": doc_types
        }
        return response_data
        
    except HTTPException as http_error:
        # Re-raise HTTP exceptions and capture error details
        response_status = http_error.status_code
        error_message = str(http_error.detail)
        raise
    except Exception as e:
        # Record failed document types retrieval
        response_status = 500
        error_message = str(e)
        business_metrics.record_utility_operation("get_doctypes", "error")
        
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
            user_id=None,  # No user_id available in utility endpoints
            response_data=response_data,
            error_message=error_message
        )