# Created: 2025-08-05 22:15:27
# Last Modified: 2025-08-06 11:34:28
# Author: Scott Cadreau

# endpoints/utility/get_lists.py
from fastapi import APIRouter, HTTPException, Request, Query
import pymysql.cursors
from core.database import get_db_connection, close_db_connection
from utils.monitoring import track_business_operation, business_metrics
import time

router = APIRouter()

def validate_user_access(user_id: str, conn) -> bool:
    """
    Validate that the user has user_type >= 100 to access list endpoints.
    Returns True if authorized, raises HTTPException if not.
    """
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute(
                "SELECT user_type FROM user_profile WHERE user_id = %s AND active = 1",
                (user_id,)
            )
            user = cursor.fetchone()
            
            if not user:
                raise HTTPException(status_code=404, detail={"error": "User not found or inactive"})
            
            if user['user_type'] < 100:
                raise HTTPException(status_code=403, detail={"error": "Insufficient privileges. User type must be >= 100"})
            
            return True
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail={"error": f"Error validating user access: {str(e)}"})

@router.get("/user_types")
@track_business_operation("get", "user_types")
def get_user_types(request: Request, user_id: str = Query(..., description="User ID for authorization")):
    """
    Get all user types with user_type < 1000.
    Returns user_type, user_type_desc, user_max_case_status from user_type_list table.
    Requires user_type >= 100 for access.
    """
    conn = None
    start_time = time.time()
    response_status = 200
    response_data = None
    error_message = None
    
    try:
        conn = get_db_connection()
        
        # Validate user access
        validate_user_access(user_id, conn)
        
        try:
            with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                cursor.execute(
                    "SELECT user_type, user_type_desc, user_max_case_status FROM user_type_list WHERE user_type < 1000"
                )
                user_types = cursor.fetchall()

                # Record successful user types retrieval
                business_metrics.record_utility_operation("get_user_types", "success")
                
        finally:
            close_db_connection(conn)
            
        response_data = {
            "user_types": user_types
        }
        return response_data
        
    except HTTPException as http_error:
        # Re-raise HTTP exceptions and capture error details
        response_status = http_error.status_code
        error_message = str(http_error.detail)
        raise
    except Exception as e:
        # Record failed user types retrieval
        response_status = 500
        error_message = str(e)
        business_metrics.record_utility_operation("get_user_types", "error")
        
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

@router.get("/case_statuses")
@track_business_operation("get", "case_statuses")
def get_case_statuses(request: Request, user_id: str = Query(..., description="User ID for authorization")):
    """
    Get all case statuses.
    Returns case_status, case_status_desc from case_status_list table.
    Requires user_type >= 100 for access.
    """
    conn = None
    start_time = time.time()
    response_status = 200
    response_data = None
    error_message = None
    
    try:
        conn = get_db_connection()
        
        # Validate user access
        validate_user_access(user_id, conn)
        
        try:
            with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                cursor.execute(
                    "SELECT case_status, case_status_desc FROM case_status_list"
                )
                case_statuses = cursor.fetchall()

                # Record successful case statuses retrieval
                business_metrics.record_utility_operation("get_case_statuses", "success")
                
        finally:
            close_db_connection(conn)
            
        response_data = {
            "case_statuses": case_statuses
        }
        return response_data
        
    except HTTPException as http_error:
        # Re-raise HTTP exceptions and capture error details
        response_status = http_error.status_code
        error_message = str(http_error.detail)
        raise
    except Exception as e:
        # Record failed case statuses retrieval
        response_status = 500
        error_message = str(e)
        business_metrics.record_utility_operation("get_case_statuses", "error")
        
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

@router.get("/user_doc_types")
@track_business_operation("get", "user_doc_types")
def get_user_doc_types(request: Request, user_id: str = Query(..., description="User ID for authorization")):
    """
    Get all user document types.
    Returns doc_type, doc_prefix from user_doc_type_list table.
    Requires user_type >= 100 for access.
    """
    conn = None
    start_time = time.time()
    response_status = 200
    response_data = None
    error_message = None
    
    try:
        conn = get_db_connection()
        
        # Validate user access
        validate_user_access(user_id, conn)
        
        try:
            with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                cursor.execute(
                    "SELECT doc_type, doc_prefix FROM user_doc_type_list"
                )
                user_doc_types = cursor.fetchall()

                # Record successful user doc types retrieval
                business_metrics.record_utility_operation("get_user_doc_types", "success")
                
        finally:
            close_db_connection(conn)
            
        response_data = {
            "user_doc_types": user_doc_types
        }
        return response_data
        
    except HTTPException as http_error:
        # Re-raise HTTP exceptions and capture error details
        response_status = http_error.status_code
        error_message = str(http_error.detail)
        raise
    except Exception as e:
        # Record failed user doc types retrieval
        response_status = 500
        error_message = str(e)
        business_metrics.record_utility_operation("get_user_doc_types", "error")
        
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

@router.get("/faqs")
@track_business_operation("get", "faqs")
def get_faqs(request: Request, user_id: str = Query(..., description="User ID for authorization")):
    """
    Get FAQ entries based on user type.
    Returns faq_header, faq_text from faq_list table filtered by user_type.
    Sorts results by display_order.
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
                # Get user_type from user_profile
                cursor.execute(
                    "SELECT user_type FROM user_profile WHERE user_id = %s AND active = 1",
                    (user_id,)
                )
                user = cursor.fetchone()
                
                if not user:
                    # Record failed FAQs retrieval - user not found
                    business_metrics.record_utility_operation("get_faqs", "user_not_found")
                    response_status = 404
                    error_message = "User not found or inactive"
                    raise HTTPException(status_code=404, detail={"error": "User not found or inactive"})
                
                user_type = user['user_type']
                
                # Query FAQ list for the user's type, sorted by display_order
                cursor.execute(
                    "SELECT faq_header, faq_text FROM faq_list WHERE user_type = %s ORDER BY display_order",
                    (user_type,)
                )
                faqs = cursor.fetchall()

                # Record successful FAQs retrieval
                business_metrics.record_utility_operation("get_faqs", "success")
                
        finally:
            close_db_connection(conn)
            
        response_data = {
            "faqs": faqs,
            "user_type": user_type
        }
        return response_data
        
    except HTTPException as http_error:
        # Re-raise HTTP exceptions and capture error details
        response_status = http_error.status_code
        error_message = str(http_error.detail)
        raise
    except Exception as e:
        # Record failed FAQs retrieval
        response_status = 500
        error_message = str(e)
        business_metrics.record_utility_operation("get_faqs", "error")
        
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