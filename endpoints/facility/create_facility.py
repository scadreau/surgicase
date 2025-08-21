# Created: 2025-07-15 09:20:13
# Last Modified: 2025-08-21 17:54:09
# Author: Scott Cadreau

# endpoints/facility/create_facility.py
from fastapi import APIRouter, HTTPException, Request
import pymysql.cursors
import logging
from core.database import get_db_connection, close_db_connection, is_connection_valid
from core.models import FacilityCreate
from utils.monitoring import track_business_operation, business_metrics
import time

router = APIRouter()

@router.post("/facility")
@track_business_operation("create", "facility")
def add_facility(request: Request, facility: FacilityCreate):
    """
    Create a new healthcare facility with comprehensive validation and monitoring.
    
    This endpoint provides full facility creation functionality including:
    - Facility data validation and database insertion
    - Automatic facility ID generation via database auto-increment
    - Comprehensive monitoring and business metrics tracking
    - Transaction safety with proper rollback handling
    - Full request logging and execution time tracking
    - Prometheus metrics integration for operational monitoring
    
    Args:
        request (Request): FastAPI request object for logging and monitoring
        facility (FacilityCreate): The facility data model containing:
            - user_id (str): ID of the user creating the facility
            - facility_name (str): Official name of the healthcare facility
            - facility_npi (int): National Provider Identifier for the facility
            - facility_addr (str): Physical street address of the facility
            - facility_city (str): City where the facility is located
            - facility_state (str): State abbreviation (e.g., "CA", "NY")
            - facility_zip (str): ZIP/postal code for the facility location
    
    Returns:
        dict: Response containing:
            - statusCode (int): HTTP status code (201 for successful creation)
            - body (dict): Response data including:
                - message (str): Success confirmation message
                - facility_id (int): Auto-generated unique facility identifier
                - user_id (str): The user ID who created the facility
                - facility_name (str): Name of the created facility
                - facility_npi (int): NPI number of the facility
                - facility_addr (str): Address of the facility
                - facility_city (str): City of the facility
                - facility_state (str): State of the facility
                - facility_zip (str): ZIP code of the facility
    
    Raises:
        HTTPException: 
            - 500 Internal Server Error: Database insertion failures or connection issues
    
    Database Operations:
        - Inserts new record into 'facility_list' table
        - Uses auto-increment for facility_id generation
        - Commits transaction immediately after successful insertion
        - Automatic rollback on any operation failure
    
    Monitoring & Logging:
        - Business metrics tracking for facility creation operations
        - Prometheus monitoring via @track_business_operation decorator
        - Records success/error metrics via business_metrics.record_facility_operation()
        - Comprehensive request logging with execution time tracking
        - Error logging with full exception details and rollback status
    
    Transaction Handling:
        - Explicit transaction commit after successful insertion
        - Automatic rollback on any operation failure with connection validation
        - Proper connection cleanup in finally block
        - Safe rollback handling with interface error protection
    
    Example:
        POST /facility
        {
            "user_id": "USER123",
            "facility_name": "General Hospital Medical Center",
            "facility_npi": 1234567890,
            "facility_addr": "123 Medical Drive",
            "facility_city": "Healthcare City",
            "facility_state": "CA",
            "facility_zip": "90210"
        }
    
    Note:
        - Facility NPI must be a valid 10-digit National Provider Identifier
        - State should use standard 2-letter abbreviations
        - All facility information is stored exactly as provided (no normalization)
        - Auto-generated facility_id is returned for reference in subsequent operations
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
            
            # Clear user environment cache after successful facility creation
            try:
                from endpoints.utility.get_user_environment import invalidate_and_rewarm_user_environment_cache
                invalidate_and_rewarm_user_environment_cache(facility.user_id)
                logging.info(f"Invalidated user environment cache for user: {facility.user_id} after facility creation")
            except Exception as cache_error:
                # Don't fail the operation if cache invalidation fails
                logging.error(f"Failed to invalidate user environment cache for user {facility.user_id}: {str(cache_error)}")
            
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