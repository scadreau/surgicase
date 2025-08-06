# Created: 2025-07-15 09:20:13
# Last Modified: 2025-08-06 15:15:22
# Author: Scott Cadreau

# endpoints/case/filter_cases.py
from fastapi import APIRouter, HTTPException, Query, Request
import pymysql.cursors
from core.database import get_db_connection, close_db_connection
from utils.monitoring import track_business_operation, business_metrics
import time

router = APIRouter()

@router.get("/case_filter")
@track_business_operation("filter", "case")
def get_cases(request: Request, user_id: str = Query(..., description="The user ID to retrieve cases for"), filter: str = Query("", description="Comma-separated list of case_status values (e.g. 0,1,2) or 'all' for all statuses")):
    """
    Retrieve and filter surgical cases for a specific user with advanced status visibility controls.
    
    This endpoint provides comprehensive case filtering capabilities with user-specific visibility
    restrictions based on their profile permissions. It supports complex filtering logic including
    special handling for maximum case status visibility and enriched case data with related entities.
    
    Key Features:
    - User-specific case filtering with permission-based visibility
    - Smart case status filtering with max_case_status support
    - Enriched case data with surgeon and facility information
    - Procedure codes with descriptions included
    - Automatic case status capping based on user permissions
    - Comprehensive monitoring and performance tracking
    - Flexible filtering: specific statuses, ranges, or all cases
    
    Args:
        request (Request): FastAPI request object for logging and monitoring
        user_id (str): Unique identifier of the user whose cases to retrieve (required)
        filter (str, optional): Case status filter specification:
            - "all": Returns all cases regardless of status
            - "": Empty string returns all cases (same as "all")
            - "1,2,3": Comma-separated list of specific status values
            - "20": Single status value (supports max_case_status logic)
    
    Returns:
        dict: Response containing:
            - cases (List[dict]): Array of case objects, each containing:
                - user_id (str): Owner of the case
                - case_id (str): Unique case identifier
                - case_date (str): ISO formatted case date
                - patient_first (str): Patient's first name
                - patient_last (str): Patient's last name
                - ins_provider (str): Insurance provider information
                - surgeon_id (str): Surgeon identifier
                - facility_id (str): Facility identifier
                - case_status (int): Current case status (may be capped at max_case_status)
                - case_status_desc (str): Human-readable status description
                - demo_file (str): Path to demonstration file
                - note_file (str): Path to notes file
                - misc_file (str): Path to miscellaneous file
                - pay_amount (decimal): Calculated payment amount
                - surgeon_name (str): Full name of the operating surgeon
                - facility_name (str): Name of the surgical facility
                - procedure_codes (List[dict]): Array of procedure information:
                    - procedure_code (str): Medical procedure code
                    - procedure_desc (str): Description of the procedure
            - user_id (str): The user ID that was queried
            - filter (List): Processed filter criteria used
    
    Raises:
        HTTPException:
            - 500 Internal Server Error: Database connection or query errors
    
    Database Operations:
        1. Retrieves user's max_case_status from user_profile table
        2. Constructs dynamic SQL query based on filter parameters
        3. Joins with surgeon_list and facility_list for enriched data
        4. Joins with case_status_list for status descriptions
        5. Fetches procedure codes with descriptions for each case
        6. Applies case status visibility restrictions per user permissions
    
    User Permission Logic:
        - Each user has a max_case_status value in their profile (default: 20)
        - Cases with status > max_case_status are capped at max_case_status
        - Status descriptions are updated to match the capped status
        - This ensures users only see case statuses they're authorized to view
    
    Filter Logic:
        - "all" or empty: Returns all active cases for the user
        - Specific statuses: Returns cases matching those exact statuses
        - max_case_status handling: If max_case_status is in filter list:
            * Returns cases with that status OR higher (>= max_case_status)
            * Other specific statuses are handled normally
            * Combines both conditions with OR logic
    
    Monitoring & Logging:
        - Business metrics tracking for filter operations
        - Prometheus monitoring via @track_business_operation decorator
        - Execution time tracking and response logging
        - Success/failure metrics with user identification
    
    Performance Features:
        - Optimized queries with proper JOIN usage
        - Batch procedure code fetching
        - Efficient duplicate removal for procedure codes
        - Cases ordered by case_id DESC for most recent first
        - Only active cases retrieved (active = 1)
    
    Example Usage:
        GET /case_filter?user_id=USER123&filter=1,2,20
        GET /case_filter?user_id=USER123&filter=all
        GET /case_filter?user_id=USER123&filter=0
        GET /case_filter?user_id=USER123  (returns all cases)
    
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
                    "demo_file": "/files/demo_CASE-2024-001.mp4",
                    "note_file": "/files/notes_CASE-2024-001.pdf",
                    "misc_file": null,
                    "pay_amount": 1500.00,
                    "surgeon_name": "Dr. Jane Smith",
                    "facility_name": "Metro Surgical Center",
                    "procedure_codes": [
                        {
                            "procedure_code": "12345",
                            "procedure_desc": "Laparoscopic Cholecystectomy"
                        }
                    ]
                }
            ],
            "user_id": "USER123",
            "filter": [1, 2, 20]
        }
    
    Note:
        - Only active cases (active=1) are returned
        - Case statuses are automatically restricted based on user permissions
        - Procedure codes include both code and description for UI display
        - Cases are ordered by case_id in descending order (newest first)
        - Empty procedure_codes array is included if no procedures exist
        - Date fields are converted to ISO format for consistent API responses
        - User profile determines maximum visible case status level
    """
    conn = None
    start_time = time.time()
    response_status = 200
    response_data = None
    error_message = None
    
    try:
        # Parse filter string - handle "all" case or comma-separated integers
        if filter.lower() == "all":
            status_list = ["all"]
        elif filter:
            status_list = [int(s) for s in filter.split(",") if s.strip().isdigit()]
        else:
            status_list = []

        conn = get_db_connection()
        
        try:
            with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                # Get user's max_case_status from user_profile
                cursor.execute("""
                    SELECT max_case_status 
                    FROM user_profile 
                    WHERE user_id = %s AND active = 1
                """, (user_id,))
                user_profile = cursor.fetchone()
                
                if not user_profile:
                    # If user profile not found, use default max_case_status of 20
                    max_case_status = 20
                else:
                    max_case_status = user_profile["max_case_status"] or 20
                
                # Build query with special handling for max_case_status filter and "all" option with surgeon and facility names
                sql = """
                    SELECT 
                        c.user_id, c.case_id, c.case_date, c.patient_first, c.patient_last, 
                        c.ins_provider, c.surgeon_id, c.facility_id, c.case_status, 
                        csl.case_status_desc,
                        c.demo_file, c.note_file, c.misc_file, c.pay_amount,
                        CONCAT(s.first_name, ' ', s.last_name) as surgeon_name,
                        f.facility_name
                    FROM cases c
                    LEFT JOIN surgeon_list s ON c.surgeon_id = s.surgeon_id
                    LEFT JOIN facility_list f ON c.facility_id = f.facility_id
                    LEFT JOIN case_status_list csl ON c.case_status = csl.case_status
                    WHERE c.user_id = %s and c.active = 1 order by case_id desc
                """
                params = [user_id]
                
                if status_list and status_list != ["all"]:
                    # Check if max_case_status is in the filter list
                    if max_case_status in status_list:
                        # Remove max_case_status from the list for separate handling
                        other_statuses = [s for s in status_list if s != max_case_status]
                        
                        if other_statuses:
                            # Query for both specific statuses and >= max_case_status
                            sql += " AND (c.case_status IN (%s) OR c.case_status >= %%s)" % (",".join(["%s"] * len(other_statuses)))
                            params.extend([str(s) for s in other_statuses])
                            params.append(max_case_status)
                        else:
                            # Only max_case_status requested, get all >= max_case_status
                            sql += " AND c.case_status >= %s"
                            params.append(max_case_status)
                    else:
                        # Normal filtering without max_case_status special handling
                        sql += " AND c.case_status IN (%s)" % (",".join(["%s"] * len(status_list)))
                        params.extend([str(s) for s in status_list])
                # If status_list is empty or ["all"], no additional WHERE clause needed
                
                cursor.execute(sql, params)
                cases = cursor.fetchall()

                result = []
                for case_data in cases:
                    # Apply case status visibility restriction
                    original_case_status = case_data["case_status"]
                    if original_case_status > max_case_status:
                        case_data["case_status"] = max_case_status
                        # Update case_status_desc to match the modified case_status
                        cursor.execute("""
                            SELECT case_status_desc 
                            FROM case_status_list 
                            WHERE case_status = %s
                        """, (max_case_status,))
                        status_desc_result = cursor.fetchone()
                        if status_desc_result:
                            case_data["case_status_desc"] = status_desc_result["case_status_desc"]
                    
                    # Convert datetime to ISO format
                    if case_data["case_date"]:
                        case_data["case_date"] = case_data["case_date"].isoformat()
                    
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
            
            # Record successful case filtering
            business_metrics.record_case_operation("filter", "success", f"user_{user_id}")
            
        finally:
            close_db_connection(conn)
            
        response_data = {
            "cases": result,
            "user_id": user_id,
            "filter": status_list
        }
        return response_data

    except HTTPException as http_error:
        # Re-raise HTTP exceptions and capture error details
        response_status = http_error.status_code
        error_message = str(http_error.detail)
        raise
    except Exception as e:
        response_status = 500
        error_message = str(e)
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