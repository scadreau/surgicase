# Created: 2025-07-30 22:59:57
# Last Modified: 2025-07-30 23:01:32
# Author: Scott Cadreau

# endpoints/backoffice/build_dashboard.py
from fastapi import APIRouter, HTTPException, Query, Request
import pymysql.cursors
from core.database import get_db_connection, close_db_connection
from utils.monitoring import track_business_operation, business_metrics
import time
from typing import Optional, Dict, Any
from datetime import datetime

# Import the individual dashboard functions
from .case_dashboard_data import case_dashboard_data as get_case_dashboard_data
from .user_dashboard_data import user_dashboard_data as get_user_dashboard_data
from endpoints.health import health_check as get_health_data

router = APIRouter()

@router.get("/build_dashboard")
@track_business_operation("get", "build_dashboard")
def build_dashboard(
    request: Request, 
    user_id: str = Query(..., description="The user ID making the request (must be user_type >= 10)"),
    start_date: Optional[str] = Query(None, description="Start date for case filtering (YYYY-MM-DD format)"),
    end_date: Optional[str] = Query(None, description="End date for case filtering (YYYY-MM-DD format)")
):
    """
    Build a comprehensive dashboard combining health data, case dashboard data, and user dashboard data.
    Returns a cohesive JSON response with all information from the three functions.
    
    Args:
        request: FastAPI request object
        user_id: The user ID making the request (must be user_type >= 10)
        start_date: Optional start date for case filtering (YYYY-MM-DD format)
        end_date: Optional end date for case filtering (YYYY-MM-DD format)
    
    Returns:
        Dict containing combined data from health, case_dashboard_data, and user_dashboard_data functions
    """
    conn = None
    start_time = time.time()
    response_status = 200
    response_data = None
    error_message = None
    
    try:
        # First verify user permissions
        conn = get_db_connection()
        
        try:
            with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                # Check user_type for the requesting user
                cursor.execute("SELECT user_type FROM user_profile WHERE user_id = %s", (user_id,))
                user_row = cursor.fetchone()
                if not user_row or user_row.get("user_type", 0) < 10:
                    # Record failed access (permission denied)
                    business_metrics.record_utility_operation("build_dashboard", "permission_denied")
                    response_status = 403
                    error_message = "User does not have permission to access dashboard data"
                    raise HTTPException(status_code=403, detail="User does not have permission to access dashboard data.")
        finally:
            close_db_connection(conn)
        
        # Now collect data from all three functions
        dashboard_data = {}
        collection_errors = []
        
        # 1. Get health data
        try:
            health_data = get_health_data()
            dashboard_data["health"] = health_data
        except Exception as e:
            collection_errors.append(f"Health data collection failed: {str(e)}")
            dashboard_data["health"] = {
                "status": "error", 
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat() + "Z"
            }
        
        # 2. Get case dashboard data
        try:
            case_data = get_case_dashboard_data(request, user_id, start_date, end_date)
            dashboard_data["cases"] = case_data
        except Exception as e:
            collection_errors.append(f"Case dashboard data collection failed: {str(e)}")
            dashboard_data["cases"] = {
                "error": str(e),
                "dashboard_data": [],
                "summary": {"total_cases": 0, "total_amount": "0.00"}
            }
        
        # 3. Get user dashboard data
        try:
            user_data = get_user_dashboard_data(request, user_id)
            dashboard_data["users"] = user_data
        except Exception as e:
            collection_errors.append(f"User dashboard data collection failed: {str(e)}")
            dashboard_data["users"] = {
                "error": str(e),
                "user_types": [],
                "summary": {"total_users": 0}
            }
        
        # Calculate execution time
        execution_time_ms = int((time.time() - start_time) * 1000)
        
        # Build the cohesive response
        response_data = {
            "dashboard_type": "comprehensive",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "execution_time_ms": execution_time_ms,
            "request_filters": {
                "user_id": user_id,
                "start_date": start_date,
                "end_date": end_date
            },
            "data": dashboard_data,
            "summary": {
                "overall_health": dashboard_data["health"].get("status", "unknown"),
                "total_cases": dashboard_data["cases"].get("summary", {}).get("total_cases", 0),
                "total_users": dashboard_data["users"].get("summary", {}).get("total_users", 0),
                "case_total_amount": dashboard_data["cases"].get("summary", {}).get("total_amount", "0.00"),
                "healthy_services": dashboard_data["health"].get("summary", {}).get("healthy", 0),
                "total_services": dashboard_data["health"].get("summary", {}).get("total_services", 0)
            },
            "errors": collection_errors if collection_errors else None,
            "status": "partial" if collection_errors else "complete"
        }
        
        # Record successful dashboard build
        business_metrics.record_utility_operation("build_dashboard", "success")
        
        return response_data
        
    except HTTPException as http_error:
        # Re-raise HTTP exceptions and capture error details
        response_status = http_error.status_code
        error_message = str(http_error.detail)
        raise
    except Exception as e:
        # Record failed dashboard build
        response_status = 500
        error_message = str(e)
        business_metrics.record_utility_operation("build_dashboard", "error")
        
        if 'conn' in locals() and conn:
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