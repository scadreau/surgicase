# Created: 2025-07-30 20:18:11
# Last Modified: 2025-07-30 22:41:16
# Author: Scott Cadreau

# endpoints/backoffice/user_dashboard_data.py
from fastapi import APIRouter, HTTPException, Query, Request
import pymysql.cursors
from core.database import get_db_connection, close_db_connection
from utils.monitoring import track_business_operation, business_metrics
import time

router = APIRouter()

@router.get("/user_dashboard_data")
@track_business_operation("get", "user_dashboard_data")
def user_dashboard_data(
    request: Request, 
    user_id: str = Query(..., description="The user ID making the request (must be user_type >= 10)")
):
    """
    Retrieve dashboard data showing user counts by user type.
    Returns user statistics for each user type < 1000 with descriptions from user_type_list table.
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
                    business_metrics.record_utility_operation("user_dashboard_data", "permission_denied")
                    response_status = 403
                    error_message = "User does not have permission to access dashboard data"
                    raise HTTPException(status_code=403, detail="User does not have permission to access dashboard data.")

                # Execute the main query to get user counts by user_type with descriptions
                cursor.execute("""
                    SELECT 
                        up.user_type, 
                        utl.user_type_desc,
                        COUNT(*) as count 
                    FROM user_profile up
                    LEFT JOIN user_type_list utl ON up.user_type = utl.user_type
                    WHERE up.user_type < 1000 AND up.active = 1
                    GROUP BY up.user_type, utl.user_type_desc
                    ORDER BY up.user_type
                """)
                user_stats = cursor.fetchall()
                
                total_users = 0
                dashboard_data = []
                
                # Process each user_type result
                for stat in user_stats:
                    user_type = stat['user_type']
                    user_type_desc = stat['user_type_desc'] or f"User Type {user_type}"
                    count = stat['count']
                    total_users += count
                    
                    dashboard_data.append({
                        "user_type": user_type,
                        "user_type_desc": user_type_desc,
                        "count": count
                    })

                # Record successful user dashboard data retrieval
                business_metrics.record_utility_operation("user_dashboard_data", "success")
                
        finally:
            close_db_connection(conn)
            
        response_data = {
            "user_types": dashboard_data,
            "summary": {
                "total_users": total_users
            }
        }
        return response_data

    except HTTPException as http_error:
        # Re-raise HTTP exceptions and capture error details
        response_status = http_error.status_code
        error_message = str(http_error.detail)
        raise
    except Exception as e:
        # Record failed user dashboard data retrieval
        response_status = 500
        error_message = str(e)
        business_metrics.record_utility_operation("user_dashboard_data", "error")
        
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