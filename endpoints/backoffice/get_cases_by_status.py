# Created: 2025-07-15 11:54:13
# Last Modified: 2025-08-06 15:23:15
# Author: Scott Cadreau

# endpoints/backoffice/get_cases_by_status.py
from fastapi import APIRouter, HTTPException, Query, Request
import pymysql.cursors
from core.database import get_db_connection, close_db_connection
from utils.monitoring import track_business_operation, business_metrics
from utils.text_formatting import capitalize_name_field
import time
from datetime import datetime

router = APIRouter()

@router.get("/cases_by_status")
@track_business_operation("get", "cases_by_status")
def get_cases_by_status(
    request: Request, 
    user_id: str = Query(..., description="The user ID making the request (must be user_type >= 10)"), 
    filter: str = Query("", description="Comma-separated list of case_status values (e.g. 0,1,2) or 'all' to get all cases"),
    start_date: str = Query(None, description="Start date filter in YYYY-MM-DD format (optional)"),
    end_date: str = Query(None, description="End date filter in YYYY-MM-DD format (optional)")
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
        3. Constructs dynamic case query with status and date filtering
        4. Joins with surgeon_list, facility_list, case_status_list, and user_profile
        5. Retrieves procedure codes with descriptions for each case
        6. Applies name formatting to provider information
        7. Only includes active cases (active = 1) in results
    
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

                # Build query for all cases with surgeon, facility, and provider names
                sql = """
                    SELECT 
                        c.user_id, c.case_id, c.case_date, c.patient_first, c.patient_last, 
                        c.ins_provider, c.surgeon_id, c.facility_id, c.case_status, 
                        csl.case_status_desc,
                        c.demo_file, c.note_file, c.misc_file, c.pay_amount,
                        CONCAT(s.first_name, ' ', s.last_name) as surgeon_name,
                        f.facility_name,
                        up.first_name as provider_first_name,
                        up.last_name as provider_last_name
                    FROM cases c
                    LEFT JOIN surgeon_list s ON c.surgeon_id = s.surgeon_id
                    LEFT JOIN facility_list f ON c.facility_id = f.facility_id
                    LEFT JOIN case_status_list csl ON c.case_status = csl.case_status
                    LEFT JOIN user_profile up ON c.user_id = up.user_id
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
                    
                    # fetch procedure codes with descriptions - JOIN with procedure_codes table
                    cursor.execute("""
                        SELECT cpc.procedure_code, pc.procedure_desc 
                        FROM case_procedure_codes cpc 
                        LEFT JOIN procedure_codes_desc pc ON cpc.procedure_code = pc.procedure_code 
                        WHERE cpc.case_id = %s
                    """, (case_data["case_id"],))
                    procedure_data = [{'procedure_code': row['procedure_code'], 'procedure_desc': row['procedure_desc']} for row in cursor.fetchall()]
                    case_data['procedure_codes'] = procedure_data
                    result.append(case_data)

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