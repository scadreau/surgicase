# Created: 2025-07-22 12:20:56
# Last Modified: 2025-07-23 11:59:48

# endpoints/backoffice/get_users.py
from fastapi import APIRouter, HTTPException, Query, Request
import pymysql.cursors
from core.database import get_db_connection, close_db_connection
from utils.monitoring import track_business_operation, business_metrics
import time

router = APIRouter()

@router.get("/users")
@track_business_operation("get", "users_list")
def get_users(request: Request, user_id: str = Query(..., description="The user ID making the request (must be user_type >= 10)")):
    """
    Retrieve all users for administration purposes, only if the calling user has user_type >= 10.
    Returns a list of users with the same information as get_user endpoint plus user_tier.
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
                # Check user_type for the requesting user
                cursor.execute("SELECT user_type FROM user_profile WHERE user_id = %s", (user_id,))
                user_row = cursor.fetchone()
                if not user_row or user_row.get("user_type", 0) < 10:
                    # Record failed access (permission denied)
                    business_metrics.record_utility_operation("get_users_list", "permission_denied")
                    response_status = 403
                    error_message = "User does not have permission to access user list"
                    raise HTTPException(status_code=403, detail="User does not have permission to access user list.")

                requesting_user_type = user_row.get("user_type", 0)

                # Fetch all active users with user_tier where user_type <= requesting user's user_type
                cursor.execute("""
                    SELECT user_id, user_email, first_name, last_name, addr1, addr2, city, state, zipcode, 
                           telephone, user_npi, referred_by_user, user_type, message_pref, states_licensed, user_tier
                    FROM user_profile 
                    WHERE active = 1 AND user_type <= %s
                    ORDER BY last_name, first_name
                """, (requesting_user_type,))
                users = cursor.fetchall()

                result = []
                for user_data in users:
                    # Fetch user documents for each user
                    cursor.execute("SELECT document_type, document_name FROM user_documents WHERE user_id = %s", (user_data["user_id"],))
                    docs = [{"document_type": row['document_type'], "document_name": row['document_name']} for row in cursor.fetchall()]
                    user_data['documents'] = docs
                    result.append(user_data)

                # Record successful users retrieval
                business_metrics.record_utility_operation("get_users_list", "success")
                
        finally:
            close_db_connection(conn)
            
        response_data = {
            "users": result,
            "total_count": len(result)
        }
        return response_data

    except HTTPException as http_error:
        # Re-raise HTTP exceptions and capture error details
        response_status = http_error.status_code
        error_message = str(http_error.detail)
        raise
    except Exception as e:
        # Record failed users retrieval
        response_status = 500
        error_message = str(e)
        business_metrics.record_utility_operation("get_users_list", "error")
        
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