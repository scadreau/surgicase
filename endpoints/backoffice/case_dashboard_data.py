# Created: 2025-07-27 02:29:13
# Last Modified: 2025-07-27 02:29:14
# Author: Scott Cadreau

# endpoints/backoffice/case_dashboard_data.py
from fastapi import APIRouter, HTTPException, Query, Request
import pymysql.cursors
from core.database import get_db_connection, close_db_connection
from utils.monitoring import track_business_operation, business_metrics
import time
from typing import Optional

router = APIRouter()

@router.get("/case_dashboard_data")
@track_business_operation("get", "case_dashboard_data")
def case_dashboard_data(
    request: Request, 
    user_id: str = Query(..., description="The user ID making the request (must be user_type >= 10)"),
    start_date: Optional[str] = Query(None, description="Start date for filtering (YYYY-MM-DD format)"),
    end_date: Optional[str] = Query(None, description="End date for filtering (YYYY-MM-DD format)")
):
    """
    Retrieve dashboard data showing case counts and totals by status.
    Returns aggregated case statistics with status descriptions.
    Optionally filters by date range if start_date and/or end_date are provided.
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
                    business_metrics.record_utility_operation("case_dashboard_data", "permission_denied")
                    response_status = 403
                    error_message = "User does not have permission to access dashboard data"
                    raise HTTPException(status_code=403, detail="User does not have permission to access dashboard data.")

                # Build the base query for case statistics
                base_query = """
                    SELECT 
                        c.case_status, 
                        COUNT(*) as cases, 
                        SUM(c.pay_amount) as total_amount
                    FROM cases c
                    WHERE c.active = 1
                """
                
                params = []
                
                # Add date filtering if provided
                if start_date:
                    base_query += " AND c.case_date >= %s"
                    params.append(start_date)
                
                if end_date:
                    base_query += " AND c.case_date <= %s"
                    params.append(end_date)
                
                base_query += " GROUP BY c.case_status ORDER BY c.case_status"
                
                # Execute the main query
                cursor.execute(base_query, params)
                case_stats = cursor.fetchall()
                
                # Get status descriptions
                cursor.execute("SELECT case_status, case_status_desc FROM case_status_list ORDER BY case_status")
                status_descriptions = {row['case_status']: row['case_status_desc'] for row in cursor.fetchall()}
                
                # Combine the data
                dashboard_data = []
                total_cases = 0
                total_amount = 0.0
                
                for stat in case_stats:
                    case_status = stat['case_status']
                    cases_count = stat['cases']
                    amount = float(stat['total_amount']) if stat['total_amount'] else 0.0
                    
                    dashboard_data.append({
                        'case_status': case_status,
                        'case_status_desc': status_descriptions.get(case_status, f"Status {case_status}"),
                        'cases': cases_count,
                        'total_amount': amount
                    })
                    
                    total_cases += cases_count
                    total_amount += amount

                # Record successful dashboard data retrieval
                business_metrics.record_utility_operation("case_dashboard_data", "success")
                
        finally:
            close_db_connection(conn)
            
        response_data = {
            "dashboard_data": dashboard_data,
            "summary": {
                "total_cases": total_cases,
                "total_amount": total_amount
            },
            "filters": {
                "start_date": start_date,
                "end_date": end_date
            }
        }
        return response_data

    except HTTPException as http_error:
        # Re-raise HTTP exceptions and capture error details
        response_status = http_error.status_code
        error_message = str(http_error.detail)
        raise
    except Exception as e:
        # Record failed dashboard data retrieval
        response_status = 500
        error_message = str(e)
        business_metrics.record_utility_operation("case_dashboard_data", "error")
        
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