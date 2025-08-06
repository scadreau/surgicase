# Created: 2025-07-15 09:20:13
# Last Modified: 2025-08-06 15:36:45
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
    Retrieve all surgeon profiles associated with a specific user ID.
    
    This endpoint provides comprehensive surgeon retrieval functionality including:
    - Complete surgeon information lookup for a given user
    - All surgeon details including contact and location information
    - Comprehensive monitoring and business metrics tracking
    - Full request logging and execution time tracking
    - Prometheus metrics integration for operational monitoring
    - Proper error handling and connection management
    
    Args:
        request (Request): FastAPI request object for logging and monitoring
        user_id (str): The unique identifier of the user to retrieve surgeons for
    
    Returns:
        dict: Response containing:
            - user_id (str): The user ID that was queried
            - surgeons (List[dict]): Array of surgeons associated with the user, each containing:
                - surgeon_id (int): Unique surgeon identifier
                - first_name (str): Surgeon's first name
                - last_name (str): Surgeon's last name
                - surgeon_npi (int): National Provider Identifier for the surgeon
                - surgeon_addr (str): Physical street address of the surgeon's practice
                - surgeon_city (str): City where the surgeon practices
                - surgeon_state (str): State abbreviation (e.g., "CA", "NY")
                - surgeon_zip (str): ZIP/postal code for the surgeon's practice location
    
    Raises:
        HTTPException: 
            - 500 Internal Server Error: Database query failures or connection issues
    
    Database Operations:
        - Executes SELECT query on 'surgeon_list' table
        - Filters results by provided user_id
        - Returns all surgeon fields except timestamps
        - Uses proper cursor management with DictCursor for JSON serialization
        - Automatic connection cleanup in finally block
    
    Monitoring & Logging:
        - Business metrics tracking for surgeon retrieval operations
        - Prometheus monitoring via @track_business_operation decorator
        - Records success/error metrics via business_metrics.record_surgeon_operation()
        - Comprehensive request logging with execution time tracking
        - Error logging with full exception details
    
    Response Behavior:
        - Returns empty surgeons array if user has no associated surgeons
        - Does not validate if user_id exists in users table
        - Returns all surgeons associated with the user regardless of status
        - Surgeons are returned in database order (typically by surgeon_id)
    
    Example:
        GET /surgeons?user_id=USER123
        
        Response:
        {
            "user_id": "USER123",
            "surgeons": [
                {
                    "surgeon_id": 1,
                    "first_name": "John",
                    "last_name": "Smith",
                    "surgeon_npi": 1234567890,
                    "surgeon_addr": "123 Medical Plaza",
                    "surgeon_city": "Surgery City",
                    "surgeon_state": "CA",
                    "surgeon_zip": "90210"
                },
                {
                    "surgeon_id": 2,
                    "first_name": "Jane",
                    "last_name": "Doe",
                    "surgeon_npi": 9876543210,
                    "surgeon_addr": "456 Healthcare Drive",
                    "surgeon_city": "Medical Town",
                    "surgeon_state": "CA",
                    "surgeon_zip": "90211"
                }
            ]
        }
        
        Empty Result Response:
        {
            "user_id": "USER456",
            "surgeons": []
        }
    
    Note:
        - No pagination is implemented; all user surgeons are returned
        - User ID validation is not performed (invalid users return empty array)
        - Surgeon data is returned exactly as stored (no formatting applied)
        - Consider implementing caching for frequently accessed user surgeons
        - Results include all surgeon information needed for case creation
        - Multiple surgeons can be associated with the same user_id
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