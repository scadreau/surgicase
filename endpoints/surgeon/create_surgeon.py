# Created: 2025-07-15 09:20:13
# Last Modified: 2025-08-21 17:54:09
# Author: Scott Cadreau

# endpoints/surgeon/create_surgeon.py
from fastapi import APIRouter, HTTPException, Request
import pymysql.cursors
import logging
from core.database import get_db_connection, close_db_connection, is_connection_valid
from core.models import SurgeonCreate
from utils.monitoring import track_business_operation, business_metrics
import time

router = APIRouter()

@router.post("/surgeon")
@track_business_operation("create", "surgeon")
def add_surgeon(request: Request, surgeon: SurgeonCreate):
    """
    Create a new surgeon profile with comprehensive validation and monitoring.
    
    This endpoint provides full surgeon creation functionality including:
    - Surgeon data validation and database insertion
    - Automatic surgeon ID generation via database auto-increment
    - Comprehensive monitoring and business metrics tracking
    - Transaction safety with proper rollback handling
    - Full request logging and execution time tracking
    - Prometheus metrics integration for operational monitoring
    
    Args:
        request (Request): FastAPI request object for logging and monitoring
        surgeon (SurgeonCreate): The surgeon data model containing:
            - user_id (str): ID of the user creating the surgeon profile
            - first_name (str): Surgeon's first name
            - last_name (str): Surgeon's last name  
            - surgeon_npi (int): National Provider Identifier for the surgeon
            - surgeon_addr (str): Physical street address of the surgeon's practice
            - surgeon_city (str): City where the surgeon practices
            - surgeon_state (str): State abbreviation (e.g., "CA", "NY")
            - surgeon_zip (str): ZIP/postal code for the surgeon's practice location
    
    Returns:
        dict: Response containing:
            - statusCode (int): HTTP status code (201 for successful creation)
            - body (dict): Response data including:
                - message (str): Success confirmation message
                - surgeon_id (int): Auto-generated unique surgeon identifier
                - user_id (str): The user ID who created the surgeon
                - first_name (str): Surgeon's first name
                - last_name (str): Surgeon's last name
                - surgeon_npi (int): NPI number of the surgeon
                - surgeon_addr (str): Address of the surgeon's practice
                - surgeon_city (str): City of the surgeon's practice
                - surgeon_state (str): State of the surgeon's practice
                - surgeon_zip (str): ZIP code of the surgeon's practice
    
    Raises:
        HTTPException: 
            - 500 Internal Server Error: Database insertion failures or connection issues
    
    Database Operations:
        - Inserts new record into 'surgeon_list' table
        - Uses auto-increment for surgeon_id generation
        - Commits transaction immediately after successful insertion
        - Automatic rollback on any operation failure
    
    Monitoring & Logging:
        - Business metrics tracking for surgeon creation operations
        - Prometheus monitoring via @track_business_operation decorator
        - Records success/error metrics via business_metrics.record_surgeon_operation()
        - Comprehensive request logging with execution time tracking
        - Error logging with full exception details and rollback status
    
    Transaction Handling:
        - Explicit transaction commit after successful insertion
        - Automatic rollback on any operation failure with connection validation
        - Proper connection cleanup in finally block
        - Safe rollback handling with interface error protection
    
    Example:
        POST /surgeon
        {
            "user_id": "USER123",
            "first_name": "John",
            "last_name": "Smith",
            "surgeon_npi": 1234567890,
            "surgeon_addr": "123 Medical Plaza",
            "surgeon_city": "Surgery City",
            "surgeon_state": "CA",
            "surgeon_zip": "90210"
        }
    
    Note:
        - Surgeon NPI must be a valid 10-digit National Provider Identifier
        - State should use standard 2-letter abbreviations
        - All surgeon information is stored exactly as provided (no normalization)
        - Auto-generated surgeon_id is returned for reference in subsequent operations
        - Multiple surgeons can be associated with the same user_id
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
            
            # Clear user environment cache after successful surgeon creation
            try:
                from endpoints.utility.get_user_environment import invalidate_and_rewarm_user_environment_cache
                invalidate_and_rewarm_user_environment_cache(surgeon.user_id)
                logging.info(f"Invalidated user environment cache for user: {surgeon.user_id} after surgeon creation")
            except Exception as cache_error:
                # Don't fail the operation if cache invalidation fails
                logging.error(f"Failed to invalidate user environment cache for user {surgeon.user_id}: {str(cache_error)}")
            
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