# Created: 2025-07-21 15:08:09
# Last Modified: 2025-07-23 12:01:37

# endpoints/surgeon/search_surgeon.py
from fastapi import APIRouter, HTTPException, Query, Request
import pymysql.cursors
from core.database import get_db_connection, close_db_connection
from utils.monitoring import track_business_operation, business_metrics
import time

router = APIRouter()

@router.get("/search-surgeon")
@track_business_operation("search", "surgeon")
def search_surgeon(
    request: Request,
    first_name: str = Query(..., description="First name to search for"),
    last_name: str = Query(..., description="Last name to search for")
):
    """
    Search for surgeons by first and last name.
    Returns all matching records from search_surgeon table.
    """
    conn = None
    start_time = time.time()
    response_status = 200
    response_data = None
    error_message = None
    
    try:
        if not first_name.strip() or not last_name.strip():
            response_status = 400
            error_message = "Both first_name and last_name are required and cannot be empty"
            raise HTTPException(status_code=400, detail={"error": "Both first_name and last_name are required and cannot be empty"})

        conn = get_db_connection()
        
        try:
            with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                # Search using LIKE for partial matching on both names
                cursor.execute("""
                    SELECT npi, first_name, last_name, address, city, state, zip
                    FROM search_surgeon 
                    WHERE first_name LIKE %s AND last_name LIKE %s
                """, (f"%{first_name}%", f"%{last_name}%"))
                
                surgeons = cursor.fetchall()

                # Record successful surgeon search
                business_metrics.record_surgeon_operation("search", "success", None)
                
        finally:
            close_db_connection(conn)
            
        response_data = {
            "statusCode": 200,
            "body": {
                "message": f"Found {len(surgeons)} matching surgeon(s)",
                "search_criteria": {
                    "first_name": first_name,
                    "last_name": last_name
                },
                "surgeons": surgeons
            }
        }
        return response_data
        
    except HTTPException as http_error:
        # Re-raise HTTP exceptions and capture error details
        response_status = http_error.status_code
        error_message = str(http_error.detail)
        raise
    except Exception as e:
        # Record failed surgeon search
        response_status = 500
        error_message = str(e)
        business_metrics.record_surgeon_operation("search", "error", None)
        
        if 'conn' in locals():
            close_db_connection(conn)
        raise HTTPException(status_code=500, detail={"error": f"Internal server error: {str(e)}"})
        
    finally:
        # Calculate execution time
        execution_time_ms = int((time.time() - start_time) * 1000)
        
        # Log request details for monitoring using the utility function
        from endpoints.utility.log_request import log_request_from_endpoint
        log_request_from_endpoint(
            request=request,
            execution_time_ms=execution_time_ms,
            response_status=response_status,
            user_id=None,  # No user_id available in search endpoints
            response_data=response_data,
            error_message=error_message
        ) 