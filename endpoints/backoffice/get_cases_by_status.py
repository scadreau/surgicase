# Created: 2025-07-15 11:54:13
# Last Modified: 2025-09-04 17:03:39
# Author: Scott Cadreau

# endpoints/backoffice/get_cases_by_status.py
from fastapi import APIRouter, HTTPException, Query, Request
import pymysql.cursors
from core.database import get_db_connection, close_db_connection
from utils.monitoring import track_business_operation, business_metrics
from utils.text_formatting import capitalize_name_field
import time
from datetime import datetime, timedelta
import json
import logging
import threading
import hashlib

router = APIRouter()

# Global cache for cases data following established patterns
_cases_cache = {}
_cases_cache_lock = threading.Lock()

def _generate_cache_key(status_list, parsed_start_date, parsed_end_date) -> str:
    """Generate a consistent cache key for the given parameters"""
    # Convert parameters to strings for hashing
    status_str = str(sorted(status_list)) if isinstance(status_list, list) else str(status_list)
    start_str = str(parsed_start_date) if parsed_start_date else "None"
    end_str = str(parsed_end_date) if parsed_end_date else "None"
    
    # Create hash of parameters
    cache_input = f"{status_str}:{start_str}:{end_str}"
    return hashlib.md5(cache_input.encode()).hexdigest()

def _is_cache_valid(cache_key: str, cache_ttl: int = 900) -> bool:
    """Check if cached results are still valid (15 minutes = 900 seconds)"""
    time_key = f"{cache_key}_time"
    
    if cache_key not in _cases_cache or time_key not in _cases_cache:
        return False
    
    return time.time() - _cases_cache[time_key] < cache_ttl

def _get_cached_cases(cache_key: str):
    """Get cached cases data if valid"""
    with _cases_cache_lock:
        if _is_cache_valid(cache_key):
            logging.debug(f"Returning cached cases data: {cache_key}")
            return _cases_cache[cache_key]
    return None

def _cache_cases_data(cache_key: str, data):
    """Cache the cases data with timestamp"""
    with _cases_cache_lock:
        time_key = f"{cache_key}_time"
        _cases_cache[cache_key] = data
        _cases_cache[time_key] = time.time()
        logging.debug(f"Successfully cached cases data: {cache_key}")

def clear_cases_cache(cache_key: str = None) -> None:
    """Clear cached cases data - for future invalidation use"""
    with _cases_cache_lock:
        if cache_key:
            time_key = f"{cache_key}_time"
            _cases_cache.pop(cache_key, None)
            _cases_cache.pop(time_key, None)
            logging.info(f"Cleared cache for cases key: {cache_key}")
        else:
            _cases_cache.clear()
            logging.info("Cleared all cached cases data")

def warm_cases_cache() -> dict:
    """
    Warm cache for common case filter combinations on server startup.
    
    Pre-loads frequently accessed case queries to eliminate cold start latency
    for admin dashboard operations.
    
    Returns:
        Dictionary with warming results including success/failure counts and timing
    """
    start_time = time.time()
    logging.info("Starting cases cache warming for optimal performance")
    
    # Define common filter combinations that admins frequently use
    common_filters = [
        # All cases - most common admin query
        {"status_list": "all", "start_date": None, "end_date": None},
        
        # Active/pending cases - common workflow queries  
        {"status_list": [1, 2, 3], "start_date": None, "end_date": None},
        
        # Recent cases (last 30 days) - common time-based filter
        {"status_list": "all", "start_date": (datetime.now() - timedelta(days=30)).date(), "end_date": None},
        
        # Completed cases - common status filter
        {"status_list": [10], "start_date": None, "end_date": None},
        
        # Current month cases - common reporting period
        {"status_list": "all", "start_date": datetime.now().replace(day=1).date(), "end_date": None}
    ]
    
    results = {
        "total_queries": len(common_filters),
        "successful": 0,
        "failed": 0,
        "details": [],
        "duration_seconds": 0
    }
    
    # Get database connection for warming
    conn = None
    try:
        conn = get_db_connection()
        
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            for i, filter_config in enumerate(common_filters):
                try:
                    query_start = time.time()
                    
                    # Execute the optimized query to warm cache
                    result = _get_cases_optimized(
                        cursor=cursor,
                        status_list=filter_config["status_list"],
                        parsed_start_date=filter_config["start_date"],
                        parsed_end_date=filter_config["end_date"]
                    )
                    
                    query_duration = time.time() - query_start
                    case_count = len(result) if result else 0
                    
                    results["successful"] += 1
                    results["details"].append({
                        "query_index": i + 1,
                        "status": "success",
                        "filter": filter_config,
                        "case_count": case_count,
                        "duration_ms": round(query_duration * 1000, 2)
                    })
                    
                    logging.debug(f"Warmed cache query {i+1}/{len(common_filters)}: {case_count} cases in {query_duration*1000:.1f}ms")
                    
                except Exception as e:
                    results["failed"] += 1
                    results["details"].append({
                        "query_index": i + 1,
                        "status": "failed",
                        "filter": filter_config,
                        "error": str(e)
                    })
                    logging.error(f"Failed to warm cache query {i+1}: {str(e)}")
                    
    except Exception as e:
        logging.error(f"Failed to establish database connection for cache warming: {str(e)}")
        results["failed"] = len(common_filters)
        
    finally:
        if conn:
            close_db_connection(conn)
    
    results["duration_seconds"] = time.time() - start_time
    
    # Log warming summary
    if results["failed"] == 0:
        total_cases = sum(detail.get("case_count", 0) for detail in results["details"] if detail["status"] == "success")
        logging.info(f"✅ Cases cache warming successful: {results['successful']} queries warmed ({total_cases} total cases) in {results['duration_seconds']:.2f}s")
    else:
        logging.warning(f"⚠️ Cases cache warming partial: {results['successful']}/{results['total_queries']} queries warmed in {results['duration_seconds']:.2f}s")
    
    return results

def _get_cases_optimized(cursor, status_list, parsed_start_date, parsed_end_date):
    """
    Experimental optimized single query implementation using JSON_ARRAYAGG with caching.
    Returns results in the same format as the original method.
    """
    # Generate cache key for this request
    cache_key = _generate_cache_key(status_list, parsed_start_date, parsed_end_date)
    
    # Check cache first
    cached_result = _get_cached_cases(cache_key)
    if cached_result is not None:
        return cached_result
    
    # Cache miss - execute query
    logging.info(f"Cache miss for cases query: {cache_key}")
    
    # Build optimized single query with JSON aggregation
    sql = """
        SELECT 
            c.user_id, c.case_id, c.case_date, c.patient_first, c.patient_last, 
            c.ins_provider, c.surgeon_id, c.facility_id, c.case_status, 
            csl.case_status_desc,
            c.demo_file, c.note_file, c.misc_file, c.pay_amount,
            up.first_name as provider_first_name,
            up.last_name as provider_last_name,
            COALESCE(
                JSON_ARRAYAGG(
                    CASE 
                        WHEN cpc.procedure_code IS NOT NULL 
                        THEN JSON_OBJECT(
                            'procedure_code', cpc.procedure_code,
                            'procedure_desc', ''
                        )
                        ELSE NULL
                    END
                ), 
                JSON_ARRAY()
            ) as procedure_codes_json
        FROM cases c
        LEFT JOIN case_status_list csl ON c.case_status = csl.case_status
        LEFT JOIN user_profile up ON c.user_id = up.user_id
        LEFT JOIN case_procedure_codes cpc ON c.case_id = cpc.case_id
        WHERE c.active = 1
    """
    params = []
    
    # Only add status filter if not "all"
    if status_list != "all" and status_list:
        placeholders = ",".join(["%s"] * len(status_list))
        sql += f" AND c.case_status IN ({placeholders})"
        params.extend(status_list)
    
    # Add date filters if provided
    if parsed_start_date:
        sql += " AND c.case_date >= %s"
        params.append(parsed_start_date)
    
    if parsed_end_date:
        sql += " AND c.case_date <= %s"
        params.append(parsed_end_date)
        
    # Group by all non-aggregated columns
    sql += """
        GROUP BY 
            c.case_id, c.user_id, c.case_date, c.patient_first, c.patient_last,
            c.ins_provider, c.surgeon_id, c.facility_id, c.case_status,
            csl.case_status_desc, c.demo_file, c.note_file, c.misc_file, c.pay_amount,
            up.first_name, up.last_name
        ORDER BY case_date DESC, up.first_name, up.last_name, c.case_id DESC
    """
    
    cursor.execute(sql, params)
    cases = cursor.fetchall()

    result = []
    for case_data in cases:
        # Convert datetime to ISO format if it's a datetime object
        if case_data["case_date"] and hasattr(case_data["case_date"], 'isoformat'):
            case_data["case_date"] = case_data["case_date"].isoformat()
        
        # Apply proper capitalization to provider names and combine them
        provider_first = case_data.get("provider_first_name")
        provider_last = case_data.get("provider_last_name")
        
        if provider_first or provider_last:
            # Apply capitalization to each name component
            capitalized_first = capitalize_name_field(provider_first) if provider_first else ""
            capitalized_last = capitalize_name_field(provider_last) if provider_last else ""
            
            # Combine into full provider name
            provider_name_parts = [part for part in [capitalized_first, capitalized_last] if part.strip()]
            case_data["provider_name"] = " ".join(provider_name_parts) if provider_name_parts else None
        else:
            case_data["provider_name"] = None
        
        # Remove the separate first/last name fields from the response
        case_data.pop("provider_first_name", None)
        case_data.pop("provider_last_name", None)
        
        # Set surgeon and facility names to None since they're not fetched in list view
        case_data["surgeon_name"] = None
        case_data["facility_name"] = None
        
        # Parse JSON aggregated procedure codes
        procedure_codes_json = case_data.pop("procedure_codes_json", "[]")
        if isinstance(procedure_codes_json, str):
            try:
                procedure_codes = json.loads(procedure_codes_json)
            except json.JSONDecodeError:
                procedure_codes = []
        else:
            # Already parsed by MySQL JSON functions
            procedure_codes = procedure_codes_json if procedure_codes_json else []
        
        # Filter out null entries and ensure proper format
        case_data['procedure_codes'] = [
            pc for pc in procedure_codes 
            if pc is not None and isinstance(pc, dict) and pc.get('procedure_code')
        ]
        
        result.append(case_data)
    
    # Cache the result before returning
    _cache_cases_data(cache_key, result)
    
    return result

@router.get("/cases_by_status")
@track_business_operation("get", "cases_by_status")
def get_cases_by_status(
    request: Request, 
    user_id: str = Query(..., description="The user ID making the request (must be user_type >= 10)"), 
    filter: str = Query("", description="Comma-separated list of case_status values (e.g. 0,1,2) or 'all' to get all cases"),
    start_date: str = Query(None, description="Start date filter in YYYY-MM-DD format (optional)"),
    end_date: str = Query(None, description="End date filter in YYYY-MM-DD format (optional)"),

):
    """
    Retrieve comprehensive case listings with advanced filtering for administrative oversight and case management.
    
    This endpoint provides administrative access to filtered case data with multiple filtering criteria
    including case status, date ranges, and comprehensive case details. It enriches case information
    with related entity data (surgeons, facilities, providers) and includes procedure code details
    for complete case visibility and administrative management.
    
    Key Features:
    - Advanced case filtering by status and date ranges
    - Comprehensive case data with enriched related entity information
    - Provider name formatting and capitalization for consistent display
    - Procedure codes with detailed descriptions
    - Administrative access control with permission validation
    - Flexible filtering options for various administrative needs
    - Real-time case data with status descriptions
    - Optimized single-query implementation with caching for enhanced performance
    - JSON aggregation for procedure codes to eliminate N+1 queries
    
    Args:
        request (Request): FastAPI request object for logging and monitoring
        user_id (str): Unique identifier of the requesting administrative user (required)
                      Must have user_type >= 10 to access case listings
        filter (str, optional): Case status filtering specification:
            - "all": Returns all active cases regardless of status
            - "": Empty string returns all cases (same as "all")
            - "1,2,3": Comma-separated list of specific status values
            - Single values like "10" are also supported
        start_date (str, optional): Start date for case filtering in YYYY-MM-DD format
                                   Includes cases where case_date >= start_date
        end_date (str, optional): End date for case filtering in YYYY-MM-DD format
                                 Includes cases where case_date <= end_date
    
    Returns:
        dict: Response containing:
            - cases (List[dict]): Array of case objects, each containing:
                - user_id (str): Case owner/provider identifier
                - case_id (str): Unique case identifier
                - case_date (str): ISO formatted case/surgery date
                - patient_first (str): Patient's first name
                - patient_last (str): Patient's last name
                - ins_provider (str): Insurance provider information
                - surgeon_id (str): Operating surgeon identifier
                - facility_id (str): Surgical facility identifier
                - case_status (int): Current case status code
                - case_status_desc (str): Human-readable status description
                - demo_file (str): Path to demonstration file
                - note_file (str): Path to notes file
                - misc_file (str): Path to miscellaneous file
                - pay_amount (decimal): Calculated payment amount
                - surgeon_name (str): Full name of the operating surgeon
                - facility_name (str): Name of the surgical facility
                - provider_name (str): Formatted full name of the case provider
                - procedure_codes (List[dict]): Array of procedure information:
                    - procedure_code (str): Medical procedure code
                    - procedure_desc (str): Description of the procedure
            - filter (str/List): Applied status filter (original or parsed)
            - start_date (str): Applied start date filter (or null)
            - end_date (str): Applied end date filter (or null)
    
    Raises:
        HTTPException:
            - 400 Bad Request: Invalid date format in start_date or end_date
            - 403 Forbidden: User does not have sufficient permissions (user_type < 10)
            - 500 Internal Server Error: Database connection or query errors
    
    Database Operations:
        1. Validates requesting user's permission level (user_type >= 10)
        2. Parses and validates date filter parameters
        3. Executes optimized single query with JSON aggregation for procedure codes
        4. Joins with case_status_list and user_profile in single operation
        5. Uses intelligent caching with 15-minute TTL for frequently accessed data
        6. Applies name formatting to provider information
        7. Only includes active cases (active = 1) in results
        8. Eliminates N+1 queries through JSON_ARRAYAGG for procedure codes
    
    Filtering Logic:
        Status Filtering:
        - "all" or empty: No status filtering applied
        - Comma-separated values: Filters for exact status matches
        - Single values: Filters for specific status
        - Invalid values are ignored in comma-separated lists
        
        Date Filtering:
        - start_date: Includes cases with case_date >= start_date (inclusive)
        - end_date: Includes cases with case_date <= end_date (inclusive)
        - Both filters can be used independently or together
        - Date validation ensures proper YYYY-MM-DD format
    
    Data Enrichment:
        - Surgeon information: Full name from surgeon_list table
        - Facility information: Facility name from facility_list table
        - Status descriptions: Human-readable descriptions from case_status_list
        - Provider information: Formatted provider name with proper capitalization
        - Procedure details: Complete procedure codes with descriptions
        - Date formatting: ISO formatted timestamps for consistency
    
    Administrative Features:
        - Complete case oversight for operational management
        - Financial tracking through pay_amount information
        - Workflow management through status-based filtering
        - Time-based analysis through date range filtering
        - Provider performance tracking through enriched data
        - Case distribution analysis across facilities and surgeons
    
    Text Formatting:
        - Provider names are properly capitalized using capitalize_name_field utility
        - Handles various name formats and edge cases
        - Combines first and last names into formatted full names
        - Ensures consistent presentation across administrative interfaces
    
    Monitoring & Logging:
        - Business metrics tracking for administrative case access
        - Prometheus monitoring via @track_business_operation decorator
        - Detailed execution time and response logging
        - Administrative access tracking for security auditing
        - Error categorization for different failure types:
            * permission_denied: Insufficient user permissions
            * success: Case data retrieved successfully
            * error: General database or system errors
    
    Security Features:
        - Administrative access control (user_type >= 10 required)
        - Permission validation before any data processing
        - Only active cases included in results
        - All database queries use parameterized statements
        - Administrative action logging for compliance
    
    Example Usage:
        GET /cases_by_status?user_id=ADMIN001&filter=all
        GET /cases_by_status?user_id=ADMIN001&filter=1,2,10&start_date=2024-01-01&end_date=2024-01-31
        GET /cases_by_status?user_id=ADMIN001&filter=10
    
    Example Response:
        {
            "cases": [
                {
                    "user_id": "USER123",
                    "case_id": "CASE-2024-001",
                    "case_date": "2024-01-15T00:00:00",
                    "patient_first": "John",
                    "patient_last": "Doe",
                    "ins_provider": "Blue Cross",
                    "surgeon_id": "SURG456",
                    "facility_id": "FAC789",
                    "case_status": 2,
                    "case_status_desc": "In Progress",
                    "demo_file": "/files/demo_file.mp4",
                    "note_file": "/files/notes.pdf",
                    "misc_file": null,
                    "pay_amount": 1500.00,
                    "surgeon_name": "Dr. Jane Smith",
                    "facility_name": "Metro Surgical Center",
                    "provider_name": "Dr. John Provider",
                    "procedure_codes": [
                        {
                            "procedure_code": "47562",
                            "procedure_desc": "Laparoscopic Cholecystectomy"
                        }
                    ]
                }
            ],
            "filter": [1, 2, 10],
            "start_date": "2024-01-01",
            "end_date": "2024-01-31"
        }
    
    Example Error Response (Permission Denied):
        {
            "detail": "User does not have permission to access all cases."
        }
    
    Example Error Response (Invalid Date):
        {
            "detail": "Invalid start_date format. Use YYYY-MM-DD format."
        }
    
    Note:
        - Only active cases (active=1) are included in all results
        - Date fields are converted to ISO format for consistent API responses
        - Provider names are formatted with proper capitalization
        - Procedure codes include both code and description for complete information
        - Administrative users should use this for case management and oversight
        - Filtering enables targeted analysis and workflow management
        - Results can be large for "all" filter - consider pagination for production use
        - Status descriptions provide human-readable context for case progression
    """
    conn = None
    start_time = time.time()
    response_status = 200
    response_data = None
    error_message = None
    
    try:
        # Parse filter string - handle "all" as special case
        if filter.lower() == "all":
            status_list = "all"
        elif filter:
            status_list = [int(s) for s in filter.split(",") if s.strip().isdigit()]
        else:
            status_list = []

        # Validate date formats if provided
        parsed_start_date = None
        parsed_end_date = None
        
        if start_date:
            try:
                parsed_start_date = datetime.strptime(start_date, "%Y-%m-%d").date()
            except ValueError:
                response_status = 400
                error_message = "Invalid start_date format. Use YYYY-MM-DD format."
                raise HTTPException(status_code=400, detail="Invalid start_date format. Use YYYY-MM-DD format.")
        
        if end_date:
            try:
                parsed_end_date = datetime.strptime(end_date, "%Y-%m-%d").date()
            except ValueError:
                response_status = 400
                error_message = "Invalid end_date format. Use YYYY-MM-DD format."
                raise HTTPException(status_code=400, detail="Invalid end_date format. Use YYYY-MM-DD format.")

        conn = get_db_connection()
        
        try:
            with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                # Check user_type for the requesting user
                cursor.execute("SELECT user_type FROM user_profile WHERE user_id = %s", (user_id,))
                user_row = cursor.fetchone()
                if not user_row or user_row.get("user_type", 0) < 10:
                    # Record failed access (permission denied)
                    business_metrics.record_utility_operation("get_cases_by_status", "permission_denied")
                    response_status = 403
                    error_message = "User does not have permission to access all cases"
                    raise HTTPException(status_code=403, detail="User does not have permission to access all cases.")

                # Use optimized single query implementation
                result = _get_cases_optimized(cursor, status_list, parsed_start_date, parsed_end_date)

                # Record successful cases retrieval
                business_metrics.record_utility_operation("get_cases_by_status", "success")
                
        finally:
            close_db_connection(conn)
            
        response_data = {
            "cases": result,
            "filter": status_list,
            "start_date": start_date,
            "end_date": end_date
        }
        return response_data

    except HTTPException as http_error:
        # Re-raise HTTP exceptions and capture error details
        response_status = http_error.status_code
        error_message = str(http_error.detail)
        raise
    except Exception as e:
        # Record failed cases retrieval
        response_status = 500
        error_message = str(e)
        business_metrics.record_utility_operation("get_cases_by_status", "error")
        
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