# Created: 2025-07-15 09:20:13
# Last Modified: 2025-08-07 19:12:18
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
def get_case(request: Request, case_id: str = Query(..., description="The case ID to retrieve")):
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
        - Retrieves case owner's max_case_status from user_profile (default: 20)
        - If actual case_status > max_case_status, caps display at max_case_status
        - This ensures users only see case status information they're authorized to view
        - Permission restrictions are applied transparently to the API consumer
    
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
        - The endpoint automatically handles missing user profiles with default permissions
    """
    conn = None
    start_time = time.time()
    response_status = 200
    response_data = None
    error_message = None
    user_id = None
    
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
                cursor.execute("""
                    SELECT max_case_status, first_name, last_name 
                    FROM user_profile 
                    WHERE user_id = %s AND active = 1
                """, (user_id,))
                user_profile = cursor.fetchone()
                
                if not user_profile:
                    # If user profile not found, use default max_case_status of 20
                    max_case_status = 20
                    user_name = None
                else:
                    max_case_status = user_profile["max_case_status"] or 20
                    # Combine first_name and last_name to create user_name
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
        log_request_from_endpoint(
            request=request,
            execution_time_ms=execution_time_ms,
            response_status=response_status,
            user_id=user_id,
            response_data=response_data,
            error_message=error_message
        )