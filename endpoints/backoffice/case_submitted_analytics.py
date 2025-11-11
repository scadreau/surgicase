# Created: 2025-11-11 14:09:38
# Last Modified: 2025-11-11 16:21:57
# Author: Scott Cadreau

# endpoints/backoffice/case_submitted_analytics.py
from fastapi import APIRouter, HTTPException, Query, Request
import pymysql.cursors
from core.database import get_db_connection, close_db_connection
from utils.monitoring import track_business_operation, business_metrics
import time
from typing import Optional
from datetime import datetime, timedelta

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
    - Period-over-period comparison when custom date filters are provided
    - Automatic previous period calculation (same length, immediately before current)
    - Pay category level comparison metrics for trend analysis
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
            - current_period (dict): Current period analytics:
                - pay_category_data (List[dict]): Array of pay category aggregations, each containing:
                    - pay_category (str): Payment category name
                    - case_count (int): Number of cases in this pay category
                    - total_amount (str): Total payment amount (formatted as decimal string)
                - summary (dict): Current period overall statistics:
                    - total_cases (int): Total number of cases across all pay categories
                    - total_amount (str): Total payment amount across all cases
            - previous_period (dict, optional): Previous period analytics (only when custom dates provided):
                - pay_category_data (List[dict]): Array of pay category aggregations
                - summary (dict): Previous period overall statistics
            - comparison (dict, optional): Period-over-period comparison (only when custom dates provided):
                - overall (dict): Aggregate comparison metrics:
                    - case_count_change (int): Difference in total cases
                    - case_count_change_percent (float): Percentage change in cases
                    - amount_change (str): Difference in total amount
                    - amount_change_percent (float): Percentage change in amount
                - by_pay_category (List[dict]): Per-category comparison, each containing:
                    - pay_category (str): Payment category name
                    - current_cases (int): Current period case count
                    - previous_cases (int): Previous period case count
                    - case_change (int): Difference in case count
                    - case_change_percent (float): Percentage change in cases
                    - current_amount (str): Current period amount
                    - previous_amount (str): Previous period amount
                    - amount_change (str): Difference in amount
                    - amount_change_percent (float): Percentage change in amount
            - filters (dict): Applied filter parameters:
                - current_start_date (str): Current period start date
                - current_end_date (str): Current period end date
                - previous_start_date (str, optional): Previous period start date (if comparison done)
                - previous_end_date (str, optional): Previous period end date (if comparison done)
                - period_days (int, optional): Length of period in days (if comparison done)
                - comparison_enabled (bool): Whether period comparison was performed
    
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
        6. Only includes cases with case_status >= 10 (submitted/completed cases)
    
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
    
    Period-Over-Period Comparison Logic:
        - Comparison is ONLY performed when BOTH start_date and end_date are provided by user
        - If default dates are used (no filters), comparison is skipped
        - Previous period is automatically calculated:
            * Length = (end_date - start_date) in days
            * Previous end = start_date - 1 day
            * Previous start = previous_end - same length
        - Example: Current 10/30-11/10 (12 days) → Previous 10/18-10/29 (12 days)
        - Comparison includes both overall and per-pay-category metrics
        - Percentage changes calculated as: ((current - previous) / previous) * 100
        - Zero division handled gracefully (previous = 0 shows as null percent change)
    
    Data Aggregation:
        - Cases grouped by pay_category values
        - COUNT aggregation for case volume analysis
        - SUM aggregation for financial analysis (pay_amount field)
        - Results ordered by pay_category for consistent reporting
        - Only active cases (active = 1) included in all calculations
        - Only cases with case_status >= 10 (submitted/completed) included
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
    
    Example Response (With Date Filters - Includes Comparison):
        {
            "current_period": {
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
                    }
                ],
                "summary": {
                    "total_cases": 63,
                    "total_amount": "94500.00"
                }
            },
            "previous_period": {
                "pay_category_data": [
                    {
                        "pay_category": "Insurance",
                        "case_count": 38,
                        "total_amount": "57000.00"
                    },
                    {
                        "pay_category": "Self-Pay",
                        "case_count": 15,
                        "total_amount": "22500.00"
                    }
                ],
                "summary": {
                    "total_cases": 53,
                    "total_amount": "79500.00"
                }
            },
            "comparison": {
                "overall": {
                    "case_count_change": 10,
                    "case_count_change_percent": 18.87,
                    "amount_change": "15000.00",
                    "amount_change_percent": 18.87
                },
                "by_pay_category": [
                    {
                        "pay_category": "Insurance",
                        "current_cases": 45,
                        "previous_cases": 38,
                        "case_change": 7,
                        "case_change_percent": 18.42,
                        "current_amount": "67500.00",
                        "previous_amount": "57000.00",
                        "amount_change": "10500.00",
                        "amount_change_percent": 18.42
                    },
                    {
                        "pay_category": "Self-Pay",
                        "current_cases": 18,
                        "previous_cases": 15,
                        "case_change": 3,
                        "case_change_percent": 20.0,
                        "current_amount": "27000.00",
                        "previous_amount": "22500.00",
                        "amount_change": "4500.00",
                        "amount_change_percent": 20.0
                    }
                ]
            },
            "filters": {
                "current_start_date": "2024-10-30",
                "current_end_date": "2024-11-10",
                "previous_start_date": "2024-10-18",
                "previous_end_date": "2024-10-29",
                "period_days": 12,
                "comparison_enabled": true
            }
        }
    
    Example Response (No Date Filters - No Comparison):
        {
            "current_period": {
                "pay_category_data": [
                    {
                        "pay_category": "Insurance",
                        "case_count": 145,
                        "total_amount": "217500.00"
                    }
                ],
                "summary": {
                    "total_cases": 145,
                    "total_amount": "217500.00"
                }
            },
            "filters": {
                "current_start_date": "2025-01-01",
                "current_end_date": "2025-11-11",
                "comparison_enabled": false
            }
        }
    
    Example Error Response (Permission Denied):
        {
            "detail": "User does not have permission to access analytics data."
        }
    
    Note:
        - Only active cases (active=1) are included in all aggregations
        - Only cases with case_status >= 10 (submitted/completed) are included
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

                # Track whether user provided custom dates (for comparison logic)
                user_provided_start = start_date is not None
                user_provided_end = end_date is not None
                comparison_enabled = user_provided_start and user_provided_end
                
                # Apply default date range if not provided
                # Default: 2025-01-01 to current date (NOW())
                if not start_date:
                    start_date = "2025-01-01"
                
                # Get current date for end_date default
                if not end_date:
                    cursor.execute("SELECT DATE(NOW()) as today")
                    current_date_result = cursor.fetchone()
                    end_date = current_date_result['today'].strftime('%Y-%m-%d')
                
                # Calculate previous period dates if comparison is enabled
                previous_start_date = None
                previous_end_date = None
                period_days = None
                
                if comparison_enabled:
                    # Parse dates
                    start_date_obj = datetime.strptime(start_date, '%Y-%m-%d').date()
                    end_date_obj = datetime.strptime(end_date, '%Y-%m-%d').date()
                    
                    # Calculate period length
                    period_days = (end_date_obj - start_date_obj).days
                    
                    # Calculate previous period (same length, immediately before current)
                    previous_end_date_obj = start_date_obj - timedelta(days=1)
                    previous_start_date_obj = previous_end_date_obj - timedelta(days=period_days)
                    
                    previous_start_date = previous_start_date_obj.strftime('%Y-%m-%d')
                    previous_end_date = previous_end_date_obj.strftime('%Y-%m-%d')
                
                # Build the pay_category analytics query with submitted_ts filtering
                pay_category_query = """
                    SELECT 
                        pay_category, 
                        COUNT(*) as case_count, 
                        SUM(pay_amount) as total_amount
                    FROM cases 
                    WHERE active = 1
                      AND case_status >= 10
                      AND submitted_ts >= %s
                      AND submitted_ts <= %s
                    GROUP BY pay_category 
                    ORDER BY pay_category
                """
                
                # Execute query for CURRENT period
                cursor.execute(pay_category_query, [start_date, end_date])
                current_stats = cursor.fetchall()
                
                # Process current period data
                current_pay_category_data = []
                current_total_cases = 0
                current_total_amount = 0.0
                
                for stat in current_stats:
                    pay_category = stat['pay_category'] or 'Unknown'
                    case_count = stat['case_count']
                    amount = float(stat['total_amount']) if stat['total_amount'] else 0.0
                    
                    current_pay_category_data.append({
                        'pay_category': pay_category,
                        'case_count': case_count,
                        'total_amount': f"{amount:.2f}"
                    })
                    
                    current_total_cases += case_count
                    current_total_amount += amount
                
                # Execute query for PREVIOUS period (if comparison enabled)
                previous_pay_category_data = []
                previous_total_cases = 0
                previous_total_amount = 0.0
                
                if comparison_enabled:
                    cursor.execute(pay_category_query, [previous_start_date, previous_end_date])
                    previous_stats = cursor.fetchall()
                    
                    for stat in previous_stats:
                        pay_category = stat['pay_category'] or 'Unknown'
                        case_count = stat['case_count']
                        amount = float(stat['total_amount']) if stat['total_amount'] else 0.0
                        
                        previous_pay_category_data.append({
                            'pay_category': pay_category,
                            'case_count': case_count,
                            'total_amount': f"{amount:.2f}"
                        })
                        
                        previous_total_cases += case_count
                        previous_total_amount += amount
                
                # Build comparison metrics if enabled
                comparison_data = None
                if comparison_enabled:
                    # Overall comparison
                    case_count_change = current_total_cases - previous_total_cases
                    amount_change = current_total_amount - previous_total_amount
                    
                    case_count_change_percent = None
                    if previous_total_cases > 0:
                        case_count_change_percent = round((case_count_change / previous_total_cases) * 100, 2)
                    
                    amount_change_percent = None
                    if previous_total_amount > 0:
                        amount_change_percent = round((amount_change / previous_total_amount) * 100, 2)
                    
                    # Per-category comparison
                    # Build lookup dictionaries for efficient matching
                    current_dict = {item['pay_category']: item for item in current_pay_category_data}
                    previous_dict = {item['pay_category']: item for item in previous_pay_category_data}
                    
                    # Get all unique pay categories from both periods
                    all_categories = set(current_dict.keys()) | set(previous_dict.keys())
                    
                    by_category_comparison = []
                    for category in sorted(all_categories):
                        current_item = current_dict.get(category, {'case_count': 0, 'total_amount': '0.00'})
                        previous_item = previous_dict.get(category, {'case_count': 0, 'total_amount': '0.00'})
                        
                        curr_cases = current_item['case_count']
                        prev_cases = previous_item['case_count']
                        curr_amount = float(current_item['total_amount'])
                        prev_amount = float(previous_item['total_amount'])
                        
                        case_change = curr_cases - prev_cases
                        amount_change_cat = curr_amount - prev_amount
                        
                        case_change_percent_cat = None
                        if prev_cases > 0:
                            case_change_percent_cat = round((case_change / prev_cases) * 100, 2)
                        
                        amount_change_percent_cat = None
                        if prev_amount > 0:
                            amount_change_percent_cat = round((amount_change_cat / prev_amount) * 100, 2)
                        
                        by_category_comparison.append({
                            'pay_category': category,
                            'current_cases': curr_cases,
                            'previous_cases': prev_cases,
                            'case_change': case_change,
                            'case_change_percent': case_change_percent_cat,
                            'current_amount': f"{curr_amount:.2f}",
                            'previous_amount': f"{prev_amount:.2f}",
                            'amount_change': f"{amount_change_cat:.2f}",
                            'amount_change_percent': amount_change_percent_cat
                        })
                    
                    comparison_data = {
                        'overall': {
                            'case_count_change': case_count_change,
                            'case_count_change_percent': case_count_change_percent,
                            'amount_change': f"{amount_change:.2f}",
                            'amount_change_percent': amount_change_percent
                        },
                        'by_pay_category': by_category_comparison
                    }

                # Record successful analytics data retrieval
                business_metrics.record_utility_operation("case_submitted_analytics", "success")
                
        finally:
            close_db_connection(conn)
            
        # Build response with new structure
        response_data = {
            "current_period": {
                "pay_category_data": current_pay_category_data,
                "summary": {
                    "total_cases": current_total_cases,
                    "total_amount": f"{current_total_amount:.2f}"
                }
            },
            "filters": {
                "current_start_date": start_date,
                "current_end_date": end_date,
                "comparison_enabled": comparison_enabled
            }
        }
        
        # Add previous period data if comparison was performed
        if comparison_enabled and previous_pay_category_data is not None:
            response_data["previous_period"] = {
                "pay_category_data": previous_pay_category_data,
                "summary": {
                    "total_cases": previous_total_cases,
                    "total_amount": f"{previous_total_amount:.2f}"
                }
            }
            response_data["comparison"] = comparison_data
            response_data["filters"]["previous_start_date"] = previous_start_date
            response_data["filters"]["previous_end_date"] = previous_end_date
            response_data["filters"]["period_days"] = period_days + 1  # +1 to show inclusive day count
        
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

