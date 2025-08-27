# Created: 2025-07-27 02:29:13
# Last Modified: 2025-08-27 06:09:51
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
    end_date: Optional[str] = Query(None, description="End date for filtering (YYYY-MM-DD format)"),
    validated: bool = False,
    skip_logging: bool = False
):
    """
    Generate comprehensive case analytics dashboard with status-based aggregation and financial summaries.
    
    This endpoint provides administrative insights into case distribution and financial performance
    across different case status categories. It aggregates case counts and payment amounts by
    status, with optional date filtering for time-based analysis. Access is restricted to
    administrative users for business intelligence and operational oversight.
    
    Key Features:
    - Case status distribution analytics with count and financial aggregation
    - Optional date range filtering for temporal analysis
    - Status description integration for human-readable reporting
    - Financial summary calculations with total amounts per status
    - Administrative access control with permission validation
    - Comprehensive dashboard data for business intelligence
    - Real-time aggregation from active case data
    
    Args:
        request (Request): FastAPI request object for logging and monitoring
        user_id (str): Unique identifier of the requesting administrative user (required)
                      Must have user_type >= 10 to access dashboard data
        start_date (str, optional): Start date for case filtering in YYYY-MM-DD format
                                   Filters cases where case_date >= start_date
        end_date (str, optional): End date for case filtering in YYYY-MM-DD format
                                 Filters cases where case_date <= end_date
    
    Returns:
        dict: Response containing:
            - dashboard_data (List[dict]): Array of status aggregations, each containing:
                - case_status (int): Numeric case status code
                - case_status_desc (str): Human-readable status description
                - cases (int): Number of cases in this status
                - total_amount (str): Total payment amount for cases in this status (formatted as decimal string)
            - summary (dict): Overall statistics:
                - total_cases (int): Total number of cases across all statuses
                - total_amount (str): Total payment amount across all cases (formatted as decimal string)
            - filters (dict): Applied filter parameters:
                - start_date (str): Start date filter applied (or null)
                - end_date (str): End date filter applied (or null)
    
    Raises:
        HTTPException:
            - 403 Forbidden: User does not have sufficient permissions (user_type < 10)
            - 500 Internal Server Error: Database connection or query errors
    
    Database Operations:
        1. Validates requesting user's permission level (user_type >= 10)
        2. Constructs dynamic case aggregation query with optional date filtering
        3. Groups cases by case_status with COUNT and SUM operations
        4. Retrieves status descriptions from case_status_list table
        5. Combines aggregated data with descriptive information
        6. Only includes active cases (active = 1) in calculations
    
    Business Intelligence Features:
        - Status distribution analysis for operational insights
        - Financial performance tracking across case lifecycle
        - Time-based filtering for trend analysis and reporting
        - Case workflow bottleneck identification through status concentrations
        - Revenue analysis by case progression stage
        - Administrative oversight of case management efficiency
    
    Date Filtering Logic:
        - start_date: Includes cases with case_date >= start_date (inclusive)
        - end_date: Includes cases with case_date <= end_date (inclusive)
        - Both filters can be used independently or together
        - Date format validation handled at query parameter level
        - Filters apply to case_date field representing surgery/service date
    
    Data Aggregation:
        - Cases grouped by exact case_status values
        - COUNT aggregation for case volume analysis
        - SUM aggregation for financial analysis (pay_amount field)
        - Results ordered by case_status for consistent reporting
        - Only active cases included in all calculations
        - Null pay_amount values treated as 0.00 in financial calculations
    
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
        - Only active cases included in aggregations
        - All database queries use parameterized statements
        - Administrative action logging for compliance
    
    Example Usage:
        GET /case_dashboard_data?user_id=ADMIN001
        GET /case_dashboard_data?user_id=ADMIN001&start_date=2024-01-01&end_date=2024-01-31
    
    Example Response:
        {
            "dashboard_data": [
                {
                    "case_status": 1,
                    "case_status_desc": "New Case",
                    "cases": 15,
                    "total_amount": "22500.00"
                },
                {
                    "case_status": 2,
                    "case_status_desc": "In Progress",
                    "cases": 8,
                    "total_amount": "12000.00"
                },
                {
                    "case_status": 10,
                    "case_status_desc": "Completed",
                    "cases": 25,
                    "total_amount": "37500.00"
                }
            ],
            "summary": {
                "total_cases": 48,
                "total_amount": "72000.00"
            },
            "filters": {
                "start_date": "2024-01-01",
                "end_date": "2024-01-31"
            }
        }
    
    Example Error Response (Permission Denied):
        {
            "detail": "User does not have permission to access dashboard data."
        }
    
    Note:
        - Only active cases (active=1) are included in all aggregations
        - Financial amounts are formatted as decimal strings for precise display
        - Status descriptions are retrieved from case_status_list lookup table
        - Date filtering is optional and can be used for custom reporting periods
        - Dashboard data updates in real-time as cases are created/modified
        - Summary totals represent the filtered dataset, not global totals
        - Administrative users should use this for operational oversight and reporting
        - Time-based analysis enables trend identification and performance monitoring
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
                        business_metrics.record_utility_operation("case_dashboard_data", "permission_denied")
                        response_status = 403
                        error_message = "User does not have permission to access dashboard data"
                        raise HTTPException(status_code=403, detail="User does not have permission to access dashboard data.")

                # Build the optimized query with JOIN to get case statistics and descriptions in one query
                base_query = """
                    SELECT 
                        c.case_status, 
                        COUNT(*) as cases, 
                        SUM(c.pay_amount) as total_amount,
                        csl.case_status_desc
                    FROM cases c
                    LEFT JOIN case_status_list csl ON c.case_status = csl.case_status
                    WHERE c.active = 1
                    AND c.user_id NOT IN (
                        '04e884e8-4011-70e9-f3bd-d89fabd15c7b', 
                        '94883428-50c1-7049-9d3d-e095ca81f174', 
                        '94b80418-6091-701b-eac8-8b325f95a799', 
                        '74081438-80d1-7055-f5df-2221b7f96049',
                        '54d8e448-0091-7031-86bb-d66da5e8f7e0'
                    )
                """
                
                params = []
                
                # Add date filtering if provided
                if start_date:
                    base_query += " AND c.case_date >= %s"
                    params.append(start_date)
                
                if end_date:
                    base_query += " AND c.case_date <= %s"
                    params.append(end_date)
                
                base_query += " GROUP BY c.case_status, csl.case_status_desc ORDER BY c.case_status"
                
                # Execute the optimized single query
                cursor.execute(base_query, params)
                case_stats = cursor.fetchall()
                
                # Process the joined data (no need for separate status lookup)
                dashboard_data = []
                total_cases = 0
                total_amount = 0.0
                
                for stat in case_stats:
                    case_status = stat['case_status']
                    cases_count = stat['cases']
                    amount = float(stat['total_amount']) if stat['total_amount'] else 0.0
                    case_status_desc = stat['case_status_desc'] or f"Status {case_status}"
                    
                    dashboard_data.append({
                        'case_status': case_status,
                        'case_status_desc': case_status_desc,
                        'cases': cases_count,
                        'total_amount': f"{amount:.2f}"
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
                "total_amount": f"{total_amount:.2f}"
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
        
        # Log request details for monitoring using the utility function (skip if called internally)
        if not skip_logging:
            from endpoints.utility.log_request import log_request_from_endpoint
            log_request_from_endpoint(
                request=request,
                execution_time_ms=execution_time_ms,
                response_status=response_status,
                user_id=user_id,
                response_data=response_data,
                error_message=error_message
            ) 