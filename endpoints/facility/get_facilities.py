# Created: 2025-07-15 09:20:13
# Last Modified: 2025-08-06 15:33:28
# Author: Scott Cadreau

# endpoints/facility/get_facilities.py
from fastapi import APIRouter, HTTPException, Query, Request
import pymysql.cursors
from core.database import get_db_connection, close_db_connection
from utils.monitoring import track_business_operation, business_metrics
import time

router = APIRouter()

@router.get("/facilities")
@track_business_operation("get", "facility")
def get_facilities(request: Request, user_id: str = Query(..., description="The user ID to retrieve facilities for")):
    """
    Retrieve all healthcare facilities associated with a specific user ID.
    
    This endpoint provides comprehensive facility retrieval functionality including:
    - Complete facility information lookup for a given user
    - All facility details including contact and location information
    - Comprehensive monitoring and business metrics tracking
    - Full request logging and execution time tracking
    - Prometheus metrics integration for operational monitoring
    - Proper error handling and connection management
    
    Args:
        request (Request): FastAPI request object for logging and monitoring
        user_id (str): The unique identifier of the user to retrieve facilities for
    
    Returns:
        dict: Response containing:
            - user_id (str): The user ID that was queried
            - facilities (List[dict]): Array of facilities associated with the user, each containing:
                - facility_id (int): Unique facility identifier
                - facility_name (str): Official name of the healthcare facility
                - facility_npi (int): National Provider Identifier for the facility
                - facility_addr (str): Physical street address of the facility
                - facility_city (str): City where the facility is located
                - facility_state (str): State abbreviation (e.g., "CA", "NY")
                - facility_zip (str): ZIP/postal code for the facility location
    
    Raises:
        HTTPException: 
            - 500 Internal Server Error: Database query failures or connection issues
    
    Database Operations:
        - Executes SELECT query on 'facility_list' table
        - Filters results by provided user_id
        - Returns all facility fields except timestamps
        - Uses proper cursor management with DictCursor for JSON serialization
        - Automatic connection cleanup in finally block
    
    Monitoring & Logging:
        - Business metrics tracking for facility retrieval operations
        - Prometheus monitoring via @track_business_operation decorator
        - Records success/error metrics via business_metrics.record_facility_operation()
        - Comprehensive request logging with execution time tracking
        - Error logging with full exception details
    
    Response Behavior:
        - Returns empty facilities array if user has no associated facilities
        - Does not validate if user_id exists in users table
        - Returns all facilities associated with the user regardless of status
        - Facilities are returned in database order (typically by facility_id)
    
    Example:
        GET /facilities?user_id=USER123
        
        Response:
        {
            "user_id": "USER123",
            "facilities": [
                {
                    "facility_id": 1,
                    "facility_name": "General Hospital Medical Center",
                    "facility_npi": 1234567890,
                    "facility_addr": "123 Medical Drive",
                    "facility_city": "Healthcare City",
                    "facility_state": "CA",
                    "facility_zip": "90210"
                },
                {
                    "facility_id": 2,
                    "facility_name": "Surgical Specialty Center",
                    "facility_npi": 9876543210,
                    "facility_addr": "456 Surgery Lane",
                    "facility_city": "Medical Town",
                    "facility_state": "CA",
                    "facility_zip": "90211"
                }
            ]
        }
        
        Empty Result Response:
        {
            "user_id": "USER456",
            "facilities": []
        }
    
    Note:
        - No pagination is implemented; all user facilities are returned
        - User ID validation is not performed (invalid users return empty array)
        - Facility data is returned exactly as stored (no formatting applied)
        - Consider implementing caching for frequently accessed user facilities
        - Results include all facility information needed for case creation
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
                    "SELECT facility_id, facility_name, facility_npi, facility_addr, facility_city, facility_state, facility_zip FROM facility_list WHERE user_id = %s",
                    (user_id,)
                )
                facilities = cursor.fetchall()

                # Record successful facility retrieval
                business_metrics.record_facility_operation("get", "success", None)
                
        finally:
            close_db_connection(conn)
            
        response_data = {
            "user_id": user_id,
            "facilities": facilities
        }
        return response_data
        
    except HTTPException as http_error:
        # Re-raise HTTP exceptions and capture error details
        response_status = http_error.status_code
        error_message = str(http_error.detail)
        raise
    except Exception as e:
        # Record failed facility retrieval
        response_status = 500
        error_message = str(e)
        business_metrics.record_facility_operation("get", "error", None)
        
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