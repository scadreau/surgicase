# Created: 2025-07-30 20:18:11
# Last Modified: 2025-07-30 20:20:18
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
    Retrieve dashboard data showing user counts grouped by user type categories.
    Returns aggregated user statistics by type groups:
    - Providers (1-9)
    - Case Admins (10-19) 
    - User Admins (20-29)
    - Global Admins (100+)
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

                # Execute the main query to get user counts by user_type
                cursor.execute("""
                    SELECT user_type, COUNT(*) as count 
                    FROM user_profile 
                    WHERE user_type < 1000 AND active = 1
                    GROUP BY user_type 
                    ORDER BY user_type
                """)
                user_stats = cursor.fetchall()
                
                # Initialize category counters
                categories = {
                    "Providers": {"range": "1-9", "count": 0, "user_types": []},
                    "Case Admins": {"range": "10-19", "count": 0, "user_types": []},
                    "User Admins": {"range": "20-29", "count": 0, "user_types": []},
                    "Global Admins": {"range": "100+", "count": 0, "user_types": []}
                }
                
                total_users = 0
                
                # Process each user_type result and categorize
                for stat in user_stats:
                    user_type = stat['user_type']
                    count = stat['count']
                    total_users += count
                    
                    # Categorize based on user_type ranges
                    if 1 <= user_type <= 9:
                        categories["Providers"]["count"] += count
                        categories["Providers"]["user_types"].append({
                            "user_type": user_type,
                            "count": count
                        })
                    elif 10 <= user_type <= 19:
                        categories["Case Admins"]["count"] += count
                        categories["Case Admins"]["user_types"].append({
                            "user_type": user_type,
                            "count": count
                        })
                    elif 20 <= user_type <= 29:
                        categories["User Admins"]["count"] += count
                        categories["User Admins"]["user_types"].append({
                            "user_type": user_type,
                            "count": count
                        })
                    elif user_type >= 100:
                        categories["Global Admins"]["count"] += count
                        categories["Global Admins"]["user_types"].append({
                            "user_type": user_type,
                            "count": count
                        })

                # Format the response data
                dashboard_data = []
                for category_name, category_data in categories.items():
                    dashboard_data.append({
                        "category": category_name,
                        "range": category_data["range"],
                        "total_count": category_data["count"],
                        "user_types": category_data["user_types"]
                    })

                # Record successful user dashboard data retrieval
                business_metrics.record_utility_operation("user_dashboard_data", "success")
                
        finally:
            close_db_connection(conn)
            
        response_data = {
            "user_dashboard_data": dashboard_data,
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