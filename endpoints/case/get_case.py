# Created: 2025-07-15 09:20:13
# Last Modified: 2025-08-12 17:02:34
# Author: Scott Cadreau

# endpoints/case/get_case.py
from fastapi import APIRouter, HTTPException, Query, Request
import pymysql.cursors
from core.database import get_db_connection, close_db_connection
from utils.monitoring import track_business_operation, business_metrics
import time

router = APIRouter()

@router.get("/case")
@track_business_operation("read", "case")
def get_case(request: Request, case_id: str = Query(..., description="The case ID to retrieve"), calling_user_id: str = Query(None, description="Optional user ID to check max_case_status against (for permission-based visibility)")):
    """
    Retrieve comprehensive surgical case information with user permission-based visibility controls.
    
    This endpoint fetches detailed case information including patient data, surgeon and facility details,
    procedure codes with descriptions, and automatically applies user-specific case status visibility
    restrictions based on the case owner's profile permissions.
    
    Key Features:
    - Complete case data retrieval with related entity information
    - User permission-based case status visibility controls
    - Enriched data with surgeon names and facility information
    - Procedure codes with detailed descriptions
    - Automatic case status capping for unauthorized status levels
    - Comprehensive monitoring and error tracking
    - Active case validation (soft-deleted cases return 404)
    
    Args:
        request (Request): FastAPI request object for logging and monitoring
        case_id (str): Unique identifier of the case to retrieve (required query parameter)
        calling_user_id (str, optional): User ID to check max_case_status against for permission-based 
                                        case status visibility. When provided, this user's max_case_status 
                                        determines the maximum case status level that will be returned. 
                                        If not provided, defaults to using the case owner's max_case_status.
    
    Returns:
        dict: Response containing:
            - case (dict): Complete case object with:
                - user_id (str): Owner of the case
                - case_id (str): Unique case identifier
                - case_date (str): ISO formatted case date
                - patient_first (str): Patient's first name
                - patient_last (str): Patient's last name
                - ins_provider (str): Insurance provider information
                - surgeon_id (str): Surgeon identifier
                - facility_id (str): Facility identifier
                - case_status (int): Current case status (may be capped at max_case_status)
                - demo_file (str): Path to demonstration file
                - note_file (str): Path to notes file
                - misc_file (str): Path to miscellaneous file
                - pay_amount (decimal): Calculated payment amount
                - user_name (str): Full name of the case owner (first_name + last_name)
                - surgeon_name (str): Full name of the operating surgeon
                - facility_name (str): Name of the surgical facility
                - procedure_codes (List[dict]): Array of procedure information:
                    - procedure_code (str): Medical procedure code
                    - procedure_desc (str): Description of the procedure
            - user_id (str): The user ID who owns the case
            - case_id (str): The case ID that was requested
    
    Raises:
        HTTPException:
            - 400 Bad Request: Missing case_id parameter
            - 404 Not Found: Case does not exist or is inactive (soft-deleted)
            - 500 Internal Server Error: Database connection or query errors
    
    Database Operations:
        1. Validates case existence and active status
        2. Joins with surgeon_list for surgeon name information
        3. Joins with facility_list for facility name information
        4. Retrieves user's max_case_status from user_profile
        5. Applies case status visibility restrictions
        6. Fetches associated procedure codes with descriptions
        7. Formats response data for API consumption
    
    User Permission Logic:
        - If calling_user_id is provided, uses that user's max_case_status from user_profile
        - If calling_user_id is not provided, uses case owner's max_case_status from user_profile  
        - Default max_case_status is 20 if user profile not found or max_case_status is null
        - If actual case_status > max_case_status, caps display at max_case_status
        - This ensures users only see case status information they're authorized to view
        - Permission restrictions are applied transparently to the API consumer
        - Calling user permissions override case owner permissions when calling_user_id is specified
    
    Data Enrichment:
        - Surgeon information: Combines first_name and last_name from surgeon_list
        - Facility information: Retrieves facility_name from facility_list
        - Procedure details: Includes both procedure codes and their descriptions
        - Date formatting: Converts database datetime to ISO format strings
        - File paths: Returns complete paths to associated case files
    
    Monitoring & Logging:
        - Business metrics tracking for case read operations
        - Prometheus monitoring via @track_business_operation decorator
        - Execution time tracking and detailed response logging
        - Error categorization (not_found vs. general errors)
        - User identification for audit trails
    
    Security Features:
        - Only active cases (active=1) are accessible
        - Soft-deleted cases return 404 Not Found
        - Case status visibility enforced by user permissions
        - All database queries use parameterized statements
    
    Performance Optimizations:
        - Single transaction for all database operations
        - Efficient JOIN operations for related data
        - Proper connection management with automatic cleanup
        - Minimal database round trips
    
    Example Usage:
        GET /case?case_id=CASE-2024-001
        GET /case?case_id=CASE-2024-001&calling_user_id=USER456
    
    Example Response:
        {
            "case": {
                "user_id": "USER123",
                "case_id": "CASE-2024-001",
                "case_date": "2024-01-15T00:00:00",
                "patient_first": "John",
                "patient_last": "Doe",
                "ins_provider": "Blue Cross Blue Shield",
                "surgeon_id": "SURG456",
                "facility_id": "FAC789",
                "case_status": 2,
                "demo_file": "/files/demo_CASE-2024-001.mp4",
                "note_file": "/files/notes_CASE-2024-001.pdf",
                "misc_file": null,
                "pay_amount": 1500.00,
                "user_name": "John Smith",
                "surgeon_name": "Dr. Jane Smith",
                "facility_name": "Metro Surgical Center",
                "procedure_codes": [
                    {
                        "procedure_code": "47562",
                        "procedure_desc": "Laparoscopic Cholecystectomy"
                    },
                    {
                        "procedure_code": "76705",
                        "procedure_desc": "Ultrasound, Abdominal"
                    }
                ]
            },
            "user_id": "USER123",
            "case_id": "CASE-2024-001"
        }
    
    Example Error Response (Not Found):
        {
            "error": "Case not found",
            "case_id": "INVALID-CASE"
        }
    
    Note:
        - Only active cases are returned; soft-deleted cases return 404
        - Case status may be different from actual database value due to user permissions
        - All date/time fields are converted to ISO format for consistency
        - Procedure codes array will be empty if no procedures are associated
        - File paths may be null if files haven't been uploaded
        - User profile permissions are automatically applied without explicit authorization
        - The endpoint automatically handles missing user profiles with default permissions (max_case_status=20)
        - When calling_user_id is provided, it takes precedence over case owner's permissions
        - Usage of calling_user_id parameter is tracked in response logging for monitoring
    """
    conn = None
    start_time = time.time()
    response_status = 200
    response_data = None
    error_message = None
    user_id = None
    using_calling_user_id = calling_user_id is not None
    
    try:
        if not case_id:
            response_status = 400
            error_message = "Missing case_id parameter"
            raise HTTPException(status_code=400, detail="Missing case_id parameter")

        conn = get_db_connection()

        try:
            with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                # fetch from cases table with surgeon and facility names
                cursor.execute("""
                    SELECT 
                        c.user_id, c.case_id, c.case_date, c.patient_first, c.patient_last, 
                        c.ins_provider, c.surgeon_id, c.facility_id, c.case_status, 
                        c.demo_file, c.note_file, c.misc_file, c.pay_amount,
                        CONCAT(s.first_name, ' ', s.last_name) as surgeon_name,
                        f.facility_name
                    FROM cases c
                    LEFT JOIN surgeon_list s ON c.surgeon_id = s.surgeon_id
                    LEFT JOIN facility_list f ON c.facility_id = f.facility_id
                    WHERE c.case_id = %s and c.active = 1
                """, (case_id,))
                case_data = cursor.fetchone()

                if not case_data:
                    # Record failed case read operation
                    business_metrics.record_case_operation("read", "not_found", case_id)
                    response_status = 404
                    error_message = "Case not found"
                    raise HTTPException(
                        status_code=404,
                        detail={"error": "Case not found", "case_id": case_id}
                    )
                
                # Get user's max_case_status and name from user_profile
                user_id = case_data["user_id"]
                
                # Determine which user ID to use for max_case_status check
                permission_user_id = calling_user_id if calling_user_id else user_id
                
                # Get case owner's profile for user_name
                cursor.execute("""
                    SELECT max_case_status, first_name, last_name 
                    FROM user_profile 
                    WHERE user_id = %s AND active = 1
                """, (user_id,))
                user_profile = cursor.fetchone()
                
                # Get permission user's max_case_status if different from case owner
                if calling_user_id and calling_user_id != user_id:
                    cursor.execute("""
                        SELECT max_case_status 
                        FROM user_profile 
                        WHERE user_id = %s AND active = 1
                    """, (calling_user_id,))
                    permission_profile = cursor.fetchone()
                    permission_max_case_status = permission_profile["max_case_status"] if permission_profile else 20
                else:
                    permission_max_case_status = None
                
                if not user_profile:
                    # If user profile not found, use default max_case_status of 20
                    max_case_status = 20
                    user_name = None
                else:
                    # Use calling_user's max_case_status if provided, otherwise use case owner's
                    if permission_max_case_status is not None:
                        max_case_status = permission_max_case_status or 20
                    else:
                        max_case_status = user_profile["max_case_status"] or 20
                    
                    # Combine first_name and last_name to create user_name (always from case owner)
                    first_name = user_profile.get("first_name", "")
                    last_name = user_profile.get("last_name", "")
                    user_name = f"{first_name} {last_name}".strip() if first_name or last_name else None
                
                # Apply case status visibility restriction
                original_case_status = case_data["case_status"]
                if original_case_status > max_case_status:
                    case_data["case_status"] = max_case_status
                
                # Add user name to case data
                case_data["user_name"] = user_name
                
                # Convert datetime to ISO format
                if case_data["case_date"]:
                    case_data["case_date"] = case_data["case_date"].isoformat()

                # fetch procedure codes with descriptions - JOIN with procedure_codes table
                cursor.execute("""
                    SELECT cpc.procedure_code, pc.procedure_desc 
                    FROM case_procedure_codes cpc 
                    LEFT JOIN procedure_codes_desc pc ON cpc.procedure_code = pc.procedure_code 
                    WHERE cpc.case_id = %s
                """, (case_id,))
                procedure_data = [{'procedure_code': row['procedure_code'], 'procedure_desc': row['procedure_desc']} for row in cursor.fetchall()]
                case_data['procedure_codes'] = procedure_data

            # Record successful case read operation
            business_metrics.record_case_operation("read", "success", case_id)

        finally:
            close_db_connection(conn)

        response_data = {
            "case": case_data,
            "user_id": case_data["user_id"],
            "case_id": case_id
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
        
        # Add calling_user_id usage information to response_data for logging
        if response_data and using_calling_user_id:
            response_data["calling_user_id_used"] = calling_user_id
        
        log_request_from_endpoint(
            request=request,
            execution_time_ms=execution_time_ms,
            response_status=response_status,
            user_id=user_id,
            response_data=response_data,
            error_message=error_message
        )