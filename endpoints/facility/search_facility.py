# Created: 2025-07-21 16:40:47
# Last Modified: 2025-07-23 13:52:04

# endpoints/facility/search_facility.py
from fastapi import APIRouter, HTTPException, Query, Request
import pymysql.cursors
from core.database import get_db_connection, close_db_connection
from utils.monitoring import track_business_operation, business_metrics
from utils.text_formatting import capitalize_name_field, capitalize_facility_field, capitalize_address_field
import time

router = APIRouter()

@router.get("/search-facility")
@track_business_operation("search", "facility")
def search_facility(
    request: Request,
    facility_name: str = Query(..., description="Facility name to search for")
):
    """
    Search for facilities by facility name.
    Returns all matching records from search_facility table.
    """
    conn = None
    start_time = time.time()
    response_status = 200
    response_data = None
    error_message = None
    
    try:
        if not facility_name.strip():
            response_status = 400
            error_message = "facility_name is required and cannot be empty"
            raise HTTPException(status_code=400, detail={"error": "facility_name is required and cannot be empty"})

        conn = get_db_connection()
        
        try:
            with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                # Search using LIKE for partial matching on facility name
                cursor.execute("""
                    SELECT *
                    FROM search_facility 
                    WHERE facility_name LIKE %s
                """, (f"%{facility_name}%",))
                
                facilities = cursor.fetchall()

                # Apply proper capitalization to facility fields
                for row in facilities:
                    if 'facility_name' in row and row['facility_name']:
                        row['facility_name'] = capitalize_facility_field(row['facility_name'])
                    if 'facility_city' in row and row['facility_city']:
                        row['facility_city'] = capitalize_name_field(row['facility_city'])
                    if 'facility_addr' in row and row['facility_addr']:
                        row['facility_addr'] = capitalize_address_field(row['facility_addr'])
                    if 'facility_state' in row and row['facility_state']:
                        # States are usually uppercase abbreviations, but handle full names
                        if len(row['facility_state']) > 2:
                            row['facility_state'] = capitalize_name_field(row['facility_state'])
                        else:
                            row['facility_state'] = row['facility_state'].upper()

                # Record successful facility search
                business_metrics.record_facility_operation("search", "success", None)
                
        finally:
            close_db_connection(conn)
            
        response_data = {
            "statusCode": 200,
            "body": {
                "message": f"Found {len(facilities)} matching facility(ies)",
                "search_criteria": {
                    "facility_name": facility_name
                },
                "facilities": facilities
            }
        }
        return response_data
        
    except HTTPException as http_error:
        # Re-raise HTTP exceptions and capture error details
        response_status = http_error.status_code
        error_message = str(http_error.detail)
        raise
    except Exception as e:
        # Record failed facility search
        response_status = 500
        error_message = str(e)
        business_metrics.record_facility_operation("search", "error", None)
        
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