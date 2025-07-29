# Created: 2025-07-15 09:20:13
# Last Modified: 2025-07-29 02:21:48
# Author: Scott Cadreau

# endpoints/surgeon/create_surgeon.py
from fastapi import APIRouter, HTTPException, Request
import pymysql.cursors
from core.database import get_db_connection, close_db_connection, is_connection_valid
from core.models import SurgeonCreate
from utils.monitoring import track_business_operation, business_metrics
import time

router = APIRouter()

@router.post("/surgeon")
@track_business_operation("create", "surgeon")
def add_surgeon(request: Request, surgeon: SurgeonCreate):
    """
    Add a new surgeon for a user.
    """
    conn = None
    start_time = time.time()
    response_status = 201
    response_data = None
    error_message = None
    
    try:
        conn = get_db_connection()
        
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute(
                "INSERT INTO surgeon_list (user_id, first_name, last_name, surgeon_npi, surgeon_addr, surgeon_city, surgeon_state, surgeon_zip) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                (surgeon.user_id, surgeon.first_name, surgeon.last_name, surgeon.surgeon_npi, surgeon.surgeon_addr, surgeon.surgeon_city, surgeon.surgeon_state, surgeon.surgeon_zip)
            )
            conn.commit()
            surgeon_id = cursor.lastrowid

            # Record successful surgeon creation
            business_metrics.record_surgeon_operation("create", "success", surgeon_id)
            
        response_data = {
            "statusCode": 201,
            "body": {
                "message": "Surgeon created successfully",
                "surgeon_id": surgeon_id,
                "user_id": surgeon.user_id,
                "first_name": surgeon.first_name,
                "last_name": surgeon.last_name,
                "surgeon_npi": surgeon.surgeon_npi,
                "surgeon_addr": surgeon.surgeon_addr,
                "surgeon_city": surgeon.surgeon_city,
                "surgeon_state": surgeon.surgeon_state,
                "surgeon_zip": surgeon.surgeon_zip
            }
        }
        return response_data
        
    except HTTPException as http_error:
        # Re-raise HTTP exceptions and capture error details
        response_status = http_error.status_code
        error_message = str(http_error.detail)
        raise
    except Exception as e:
        # Record failed surgeon creation
        response_status = 500
        error_message = str(e)
        business_metrics.record_surgeon_operation("create", "error", None)
        
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
            user_id=surgeon.user_id,
            response_data=response_data,
            error_message=error_message
        )
        
        # Always close the connection
        if conn:
            close_db_connection(conn)