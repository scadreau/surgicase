# Created: 2025-11-11 14:09:38
# Last Modified: 2025-11-11 14:10:39
# Author: Scott Cadreau

# endpoints/backoffice/case_submitted_analytics.py
from fastapi import APIRouter, HTTPException, Query, Request
import pymysql.cursors
from core.database import get_db_connection, close_db_connection
from utils.monitoring import track_business_operation, business_metrics
import time
from typing import Optional

router = APIRouter()

@router.get("/case_submitted_analytics")
@track_business_operation("get", "case_submitted_analytics")
def case_submitted_analytics(
    request: Request,
    user_id: str = Query(..., description="The user ID making the request (must be user_type >= 10)"),
    start_date: Optional[str] = Query(None, description="Start date for filtering (YYYY-MM-DD format). Defaults to 2025-01-01 if not provided."),
    end_date: Optional[str] = Query(None, description="End date for filtering (YYYY-MM-DD format). Defaults to current date if not provided."),
    validated: bool = False,
    skip_logging: bool = False
):
    """
    Generate case analytics based on submission timestamps with pay category aggregation.
    
    This endpoint provides administrative analytics for cases filtered by when they were
    submitted (submitted_ts) rather than when they were created (case_create_ts). This
    enables time-based analysis of case submission patterns and financial performance
    by pay category. Access is restricted to administrative users for business intelligence
    and operational oversight.
    
    Key Features:
    - Pay category distribution analytics based on submission timestamps
    - Count and financial aggregation by pay category
    - Flexible date range filtering with sensible defaults (2025-01-01 to current date)
    - Financial summary calculations with total amounts per pay category
    - Administrative access control with permission validation
    - Real-time aggregation from active case data
    - Extensible structure for future advanced analytics
    
    Args:
        request (Request): FastAPI request object for logging and monitoring
        user_id (str): Unique identifier of the requesting administrative user (required)
                      Must have user_type >= 10 to access analytics data
        start_date (str, optional): Start date for case filtering in YYYY-MM-DD format
                                   Filters cases where submitted_ts >= start_date
                                   Defaults to '2025-01-01' if not provided
        end_date (str, optional): End date for case filtering in YYYY-MM-DD format
                                 Filters cases where submitted_ts <= end_date
                                 Defaults to current date (NOW()) if not provided
        validated (bool, optional): Skip user permission validation if already validated
        skip_logging (bool, optional): Skip request logging if called internally
    
    Returns:
        dict: Response containing:
            - pay_category_data (List[dict]): Array of pay category aggregations, each containing:
                - pay_category (str): Payment category name
                - case_count (int): Number of cases in this pay category
                - total_amount (str): Total payment amount for cases in this pay category (formatted as decimal string)
            - summary (dict): Overall statistics:
                - total_cases (int): Total number of cases across all pay categories
                - total_amount (str): Total payment amount across all cases (formatted as decimal string)
            - filters (dict): Applied filter parameters:
                - start_date (str): Start date filter applied (actual value used, including defaults)
                - end_date (str): End date filter applied (actual value used, including defaults)
    
    Raises:
        HTTPException:
            - 403 Forbidden: User does not have sufficient permissions (user_type < 10)
            - 500 Internal Server Error: Database connection or query errors
    
    Database Operations:
        1. Validates requesting user's permission level (user_type >= 10)
        2. Applies default date range if not provided (2025-01-01 to NOW())
        3. Constructs case aggregation query filtering by submitted_ts
        4. Groups cases by pay_category with COUNT and SUM operations
        5. Only includes active cases (active = 1) in all calculations
    
    Business Intelligence Features:
        - Submission pattern analysis for operational insights
        - Financial performance tracking by submission date
        - Pay category distribution for revenue analysis
        - Time-based filtering for trend analysis and reporting
        - Revenue analysis by payment type
        - Administrative oversight of submission patterns
    
    Date Filtering Logic:
        - start_date: Includes cases with submitted_ts >= start_date (inclusive)
                     Defaults to '2025-01-01' if not provided
        - end_date: Includes cases with submitted_ts <= end_date (inclusive)
                   Defaults to current date (NOW()) if not provided
        - Both filters can be used independently or together
        - Date format validation handled at query parameter level
        - Filters apply to submitted_ts field (when case was submitted)
    
    Data Aggregation:
        - Cases grouped by pay_category values
        - COUNT aggregation for case volume analysis
        - SUM aggregation for financial analysis (pay_amount field)
        - Results ordered by pay_category for consistent reporting
        - Only active cases included in all calculations
        - Null pay_amount values treated as 0.00 in financial calculations
        - Null or empty pay_category values displayed as 'Unknown'
    
    Monitoring & Logging:
        - Business metrics tracking for analytics access operations
        - Prometheus monitoring via @track_business_operation decorator
        - Detailed execution time and response logging
        - Administrative access tracking for security auditing
        - Error categorization for different failure types:
            * permission_denied: Insufficient user permissions
            * success: Analytics data retrieved successfully
            * error: General database or system errors
    
    Security Features:
        - Administrative access control (user_type >= 10 required)
        - Permission validation before any data processing
        - Only active cases included in aggregations
        - All database queries use parameterized statements
        - Administrative action logging for compliance
    
    Example Usage:
        # Get all cases from 2025-01-01 to current date (default behavior)
        GET /case_submitted_analytics?user_id=ADMIN001
        
        # Get cases for specific date range
        GET /case_submitted_analytics?user_id=ADMIN001&start_date=2024-01-01&end_date=2024-01-31
        
        # Get cases from specific start date to current date
        GET /case_submitted_analytics?user_id=ADMIN001&start_date=2024-06-01
    
    Example Response:
        {
            "pay_category_data": [
                {
                    "pay_category": "Insurance",
                    "case_count": 45,
                    "total_amount": "67500.00"
                },
                {
                    "pay_category": "Self-Pay",
                    "case_count": 18,
                    "total_amount": "27000.00"
                },
                {
                    "pay_category": "Workers Comp",
                    "case_count": 12,
                    "total_amount": "18000.00"
                },
                {
                    "pay_category": "Unknown",
                    "case_count": 3,
                    "total_amount": "4500.00"
                }
            ],
            "summary": {
                "total_cases": 78,
                "total_amount": "117000.00"
            },
            "filters": {
                "start_date": "2025-01-01",
                "end_date": "2025-11-11"
            }
        }
    
    Example Error Response (Permission Denied):
        {
            "detail": "User does not have permission to access analytics data."
        }
    
    Note:
        - Only active cases (active=1) are included in all aggregations
        - Financial amounts are formatted as decimal strings for precise display
        - Date filtering uses submitted_ts (submission timestamp), not case_create_ts
        - Default date range covers all cases from 2025-01-01 to current date
        - Summary totals represent the filtered dataset, not global totals
        - Administrative users should use this for submission pattern analysis
        - This endpoint is designed to be easily extended for future analytics features
        - Time-based analysis enables trend identification and performance monitoring
    
    Future Extension Points:
        - Additional aggregation dimensions (surgeon, facility, procedure type, etc.)
        - Comparative analytics (period-over-period comparisons)
        - Advanced statistical calculations (averages, medians, percentiles)
        - Multi-dimensional groupings and pivot table style outputs
        - Trend analysis and forecasting metrics
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
                # INPUT VALIDATION -- Check user permissions for administrative access
                if not validated:
                    cursor.execute("SELECT user_type FROM user_profile WHERE user_id = %s", (user_id,))
                    user_row = cursor.fetchone()
                    if not user_row or user_row.get("user_type", 0) < 10:
                        # Record failed access (permission denied)
                        business_metrics.record_utility_operation("case_submitted_analytics", "permission_denied")
                        response_status = 403
                        error_message = "User does not have permission to access analytics data"
                        raise HTTPException(status_code=403, detail="User does not have permission to access analytics data.")

                # Apply default date range if not provided
                # Default: 2025-01-01 to current date (NOW())
                if not start_date:
                    start_date = "2025-01-01"
                
                # Build the pay_category analytics query with submitted_ts filtering
                pay_category_query = """
                    SELECT 
                        pay_category, 
                        COUNT(*) as case_count, 
                        SUM(pay_amount) as total_amount
                    FROM cases 
                    WHERE active = 1
                      AND submitted_ts >= %s
                """
                
                params = [start_date]
                
                # Add end_date filtering if provided, otherwise use NOW()
                if end_date:
                    pay_category_query += " AND submitted_ts <= %s"
                    params.append(end_date)
                else:
                    pay_category_query += " AND submitted_ts <= NOW()"
                    # Get current date for response
                    cursor.execute("SELECT DATE(NOW()) as current_date")
                    current_date_result = cursor.fetchone()
                    end_date = current_date_result['current_date'].strftime('%Y-%m-%d')
                
                pay_category_query += " GROUP BY pay_category ORDER BY pay_category"
                
                # Execute the pay_category query
                cursor.execute(pay_category_query, params)
                pay_category_stats = cursor.fetchall()
                
                # Process pay_category data
                pay_category_data = []
                total_cases = 0
                total_amount = 0.0
                
                for stat in pay_category_stats:
                    pay_category = stat['pay_category'] or 'Unknown'
                    case_count = stat['case_count']
                    amount = float(stat['total_amount']) if stat['total_amount'] else 0.0
                    
                    pay_category_data.append({
                        'pay_category': pay_category,
                        'case_count': case_count,
                        'total_amount': f"{amount:.2f}"
                    })
                    
                    total_cases += case_count
                    total_amount += amount

                # Record successful analytics data retrieval
                business_metrics.record_utility_operation("case_submitted_analytics", "success")
                
        finally:
            close_db_connection(conn)
            
        response_data = {
            "pay_category_data": pay_category_data,
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
        # Record failed analytics data retrieval
        response_status = 500
        error_message = str(e)
        business_metrics.record_utility_operation("case_submitted_analytics", "error")
        
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

