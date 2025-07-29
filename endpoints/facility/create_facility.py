# Created: 2025-07-15 09:20:13
# Last Modified: 2025-07-29 02:22:31
# Author: Scott Cadreau

# endpoints/facility/create_facility.py
from fastapi import APIRouter, HTTPException, Request
import pymysql.cursors
from core.database import get_db_connection, close_db_connection, is_connection_valid
from core.models import FacilityCreate
from utils.monitoring import track_business_operation, business_metrics
import time

router = APIRouter()

@router.post("/facility")
@track_business_operation("create", "facility")
def add_facility(request: Request, facility: FacilityCreate):
    """
    Add a new facility for a user.
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
                "INSERT INTO facility_list (user_id, facility_name, facility_npi, facility_addr, facility_city, facility_state, facility_zip) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (facility.user_id, facility.facility_name, facility.facility_npi, facility.facility_addr, facility.facility_city, facility.facility_state, facility.facility_zip)
            )
            conn.commit()
            facility_id = cursor.lastrowid

            # Record successful facility creation
            business_metrics.record_facility_operation("create", "success", facility_id)
            
        response_data = {
            "statusCode": 201,
            "body": {
                "message": "Facility created successfully",
                "facility_id": facility_id,
                "user_id": facility.user_id,
                "facility_name": facility.facility_name,
                "facility_npi": facility.facility_npi,
                "facility_addr": facility.facility_addr,
                "facility_city": facility.facility_city,
                "facility_state": facility.facility_state,
                "facility_zip": facility.facility_zip
            }
        }
        return response_data
        
    except HTTPException as http_error:
        # Re-raise HTTP exceptions and capture error details
        response_status = http_error.status_code
        error_message = str(http_error.detail)
        raise
    except Exception as e:
        # Record failed facility creation
        response_status = 500
        error_message = str(e)
        business_metrics.record_facility_operation("create", "error", None)
        
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
            user_id=facility.user_id,
            response_data=response_data,
            error_message=error_message
        )
        
        # Always close the connection
        if conn:
            close_db_connection(conn)