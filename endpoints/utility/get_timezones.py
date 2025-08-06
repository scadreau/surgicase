# Created: 2025-07-31 02:14:20
# Last Modified: 2025-08-06 15:42:39
# Author: Scott Cadreau

# endpoints/utility/get_timezones.py
from fastapi import APIRouter, HTTPException, Request
import pymysql.cursors
from core.database import get_db_connection, close_db_connection
from utils.monitoring import track_business_operation, business_metrics
import time

router = APIRouter()

@router.get("/timezones")
@track_business_operation("get", "timezones")
def get_timezones(request: Request):
    """
    Retrieve all available timezones with their identifiers and UTC offsets.
    
    This endpoint provides comprehensive timezone data used throughout the application
    for proper time zone handling and display. The timezone information includes both
    the standard timezone identifier (e.g., "America/New_York") and the corresponding
    UTC offset for proper datetime calculations and user interface displays.
    
    Args:
        request (Request): FastAPI request object for logging and monitoring
    
    Returns:
        dict: Response containing:
            - timezones (List[dict]): Array of timezone objects, each containing:
                - tz_identifier (str): Standard timezone identifier (e.g., "America/New_York")
                - utc_offset (str): UTC offset in standard format (e.g., "-05:00")
    
    Raises:
        HTTPException: 
            - 500 Internal Server Error: Database connection or query execution errors
    
    Database Operations:
        - Queries 'user_timezones' table for all available timezone data
        - Results ordered alphabetically by timezone identifier
        - Read-only operation with automatic connection management
    
    Monitoring & Logging:
        - Business metrics tracking for timezone retrieval operations
        - Prometheus monitoring via @track_business_operation decorator
        - Comprehensive request logging with execution time tracking
        - Error logging with full exception details
    
    Example Response:
        {
            "timezones": [
                {
                    "tz_identifier": "America/New_York",
                    "utc_offset": "-05:00"
                },
                {
                    "tz_identifier": "America/Los_Angeles", 
                    "utc_offset": "-08:00"
                },
                {
                    "tz_identifier": "UTC",
                    "utc_offset": "+00:00"
                }
            ]
        }
    
    Usage:
        GET /timezones
        
    Notes:
        - No authentication required for this utility endpoint
        - Results are sorted alphabetically by timezone identifier for consistent UI presentation
        - Used primarily for populating timezone dropdown lists in user profile and scheduling forms
        - Timezone data supports proper datetime handling across different geographical regions
        - UTC offsets may change due to daylight saving time transitions in some regions
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
                    "SELECT tz_identifier, utc_offset FROM user_timezones ORDER BY tz_identifier"
                )
                timezones = cursor.fetchall()

                # Record successful timezones retrieval
                business_metrics.record_utility_operation("get_timezones", "success")
                
        finally:
            close_db_connection(conn)
            
        response_data = {
            "timezones": timezones
        }
        return response_data
        
    except HTTPException as http_error:
        # Re-raise HTTP exceptions and capture error details
        response_status = http_error.status_code
        error_message = str(http_error.detail)
        raise
    except Exception as e:
        # Record failed timezones retrieval
        response_status = 500
        error_message = str(e)
        business_metrics.record_utility_operation("get_timezones", "error")
        
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