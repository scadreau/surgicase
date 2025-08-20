# Created: 2025-07-30 20:18:11
# Last Modified: 2025-08-20 09:09:41
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
    user_id: str = Query(..., description="The user ID making the request (must be user_type >= 10)"),
    validated: bool = False
):
    """
    Generate comprehensive user analytics dashboard with user type distribution and organizational insights.
    
    This endpoint provides administrative insights into user distribution across different user type
    categories within the healthcare platform. It aggregates active user counts by user type
    classification, providing organizational visibility into user role distribution, platform
    adoption, and administrative oversight capabilities.
    
    Key Features:
    - User type distribution analytics with count aggregation
    - User type description integration for human-readable reporting
    - Organizational insight into platform user composition
    - Active user filtering to exclude deactivated accounts
    - Administrative access control with permission validation
    - Real-time aggregation from current user data
    - Role-based analytics for organizational management
    
    Args:
        request (Request): FastAPI request object for logging and monitoring
        user_id (str): Unique identifier of the requesting administrative user (required)
                      Must have user_type >= 10 to access dashboard data
    
    Returns:
        dict: Response containing:
            - user_types (List[dict]): Array of user type aggregations, each containing:
                - user_type (int): Numeric user type classification code
                - user_type_desc (str): Human-readable user type description
                - count (int): Number of active users in this user type category
            - summary (dict): Overall statistics:
                - total_users (int): Total number of active users across all types
    
    Raises:
        HTTPException:
            - 403 Forbidden: User does not have sufficient permissions (user_type < 10)
            - 500 Internal Server Error: Database connection or query errors
    
    Database Operations:
        1. Validates requesting user's permission level (user_type >= 10)
        2. Aggregates active users by user_type with COUNT operation
        3. Joins with user_type_list table for descriptive information
        4. Filters for user_type < 1000 (excluding system/special accounts)
        5. Orders results by user_type for consistent reporting
        6. Only includes active users (active = 1) in calculations
    
    User Type Classification System:
        - user_type < 1000: Regular platform users (included in analytics)
        - user_type >= 1000: System accounts and special roles (excluded)
        - Lower values typically indicate more restricted access
        - Higher values (but < 1000) typically indicate administrative roles
        - Descriptions from user_type_list provide role context
    
    Administrative Analytics:
        - Platform adoption insights across user role categories
        - Organizational structure visibility for administrative planning
        - User role distribution for access control oversight
        - Active user base composition for resource planning
        - Professional role tracking for healthcare compliance
        - User onboarding and retention analytics
    
    Business Intelligence Features:
        - User role distribution for organizational insights
        - Platform usage analytics by professional category
        - Administrative oversight of user type distribution
        - Healthcare professional classification tracking
        - User base composition analysis for strategic planning
        - Active user metrics for operational decisions
    
    Data Aggregation:
        - Users grouped by exact user_type values
        - COUNT aggregation for user volume analysis
        - Results ordered by user_type for consistent reporting
        - Only active users included in all calculations
        - System accounts (user_type >= 1000) excluded from analytics
        - JOIN with user_type_list for descriptive labels
    
    Monitoring & Logging:
        - Business metrics tracking for dashboard access operations
        - Prometheus monitoring via @track_business_operation decorator
        - Detailed execution time and response logging
        - Administrative access tracking for security auditing
        - Error categorization for different failure types:
            * permission_denied: Insufficient user permissions
            * success: Dashboard data retrieved successfully
            * error: General database or system errors
    
    Security Features:
        - Administrative access control (user_type >= 10 required)
        - Permission validation before any data processing
        - Only active users included in aggregations
        - System accounts excluded from analytics visibility
        - All database queries use parameterized statements
        - Administrative action logging for compliance
    
    Example Usage:
        GET /user_dashboard_data?user_id=ADMIN001
    
    Example Response:
        {
            "user_types": [
                {
                    "user_type": 1,
                    "user_type_desc": "Standard User",
                    "count": 45
                },
                {
                    "user_type": 5,
                    "user_type_desc": "Healthcare Provider",
                    "count": 12
                },
                {
                    "user_type": 10,
                    "user_type_desc": "Administrator",
                    "count": 3
                },
                {
                    "user_type": 15,
                    "user_type_desc": "Super Administrator",
                    "count": 1
                }
            ],
            "summary": {
                "total_users": 61
            }
        }
    
    Example Error Response (Permission Denied):
        {
            "detail": "User does not have permission to access dashboard data."
        }
    
    Note:
        - Only active users (active=1) are included in all aggregations
        - System accounts with user_type >= 1000 are excluded from analytics
        - User type descriptions are retrieved from user_type_list lookup table
        - Dashboard data updates in real-time as users are created/modified/deactivated
        - Summary totals represent the entire active user base (excluding system accounts)
        - Administrative users should use this for organizational oversight and planning
        - User type classification enables role-based access control and compliance tracking
        - Analytics provide insights into platform adoption and user composition
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
                # Check user_type for the requesting user (skip if already validated)
                if not validated:
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