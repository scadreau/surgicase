# Created: 2025-08-26 23:50:11
# Last Modified: 2025-10-20 14:13:26
# Author: Scott Cadreau

# endpoints/case/group_cases.py
from fastapi import APIRouter, HTTPException, Query, Request
import pymysql.cursors
from core.database import get_db_connection, close_db_connection
from utils.monitoring import track_business_operation, business_metrics
import time
import json
import logging

router = APIRouter()

def _validate_group_admin_access(requesting_user_id: str, target_user_id: str, cursor) -> bool:
    """
    Validate if requesting user can access cases for target user through group admin privileges.
    
    Args:
        requesting_user_id (str): User making the request
        target_user_id (str): User whose cases are being accessed
        cursor: Database cursor for queries
    
    Returns:
        bool: True if access is allowed, False otherwise
    """
    # Users can always access their own cases
    if requesting_user_id == target_user_id:
        return True
    
    # Check if requesting user is a group admin for any group containing target user
    cursor.execute("""
        SELECT 1 FROM user_groups ug1
        JOIN user_groups ug2 ON ug1.group_id = ug2.group_id
        WHERE ug1.user_id = %s AND ug1.group_admin = 1
        AND ug2.user_id = %s
        LIMIT 1
    """, (requesting_user_id, target_user_id))
    
    return cursor.fetchone() is not None

def _get_group_users(requesting_user_id: str, cursor) -> list:
    """
    Get all users that the requesting user can access through group admin privileges.
    
    Args:
        requesting_user_id (str): User making the request
        cursor: Database cursor for queries
    
    Returns:
        list: List of user_ids that the requesting user can access
    """
    # Get all users in groups where requesting user is an admin
    cursor.execute("""
        SELECT DISTINCT ug2.user_id
        FROM user_groups ug1
        JOIN user_groups ug2 ON ug1.group_id = ug2.group_id
        WHERE ug1.user_id = %s AND ug1.group_admin = 1
    """, (requesting_user_id,))
    
    group_users = [row["user_id"] for row in cursor.fetchall()]
    
    # Always include the requesting user themselves
    if requesting_user_id not in group_users:
        group_users.append(requesting_user_id)
    
    return group_users

def _get_group_cases_optimized(cursor, requesting_user_id: str, target_user_id: str, status_list, max_case_status):
    """
    Optimized query implementation for group admin case filtering.
    Based on the original _get_user_cases_optimized but adapted for group access.
    """
    # Validate access permission
    if not _validate_group_admin_access(requesting_user_id, target_user_id, cursor):
        raise HTTPException(status_code=403, detail="Access denied: User not authorized to view these cases")
    
    # Build optimized single query with JSON aggregation and provider name
    sql = """
        SELECT 
            c.user_id, c.case_id, c.case_date, c.patient_first, c.patient_last, 
            c.ins_provider, c.surgeon_id, c.facility_id, c.case_status, 
            csl.case_status_desc,
            c.demo_file, c.note_file, c.misc_file, c.pay_amount, c.phi_encrypted,
            CONCAT(COALESCE(up.first_name, ''), ' ', COALESCE(up.last_name, '')) as provider_name,
            COALESCE(
                JSON_ARRAYAGG(
                    CASE 
                        WHEN cpc.procedure_code IS NOT NULL 
                        THEN JSON_OBJECT(
                            'procedure_code', cpc.procedure_code,
                            'procedure_desc', COALESCE(cpc.procedure_desc, '')
                        )
                        ELSE NULL
                    END
                ), 
                JSON_ARRAY()
            ) as procedure_codes_json
        FROM cases c
        LEFT JOIN case_status_list csl ON c.case_status = csl.case_status
        LEFT JOIN case_procedure_codes cpc ON c.case_id = cpc.case_id
#        LEFT JOIN procedure_codes_desc pc ON cpc.procedure_code = pc.procedure_code
        LEFT JOIN user_profile up ON c.user_id = up.user_id AND up.active = 1
        WHERE c.user_id = %s AND c.active = 1
    """
    params = [target_user_id]
    
    # Add status filtering logic (same as original)
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
    
    # Group by and order
    sql += """
        GROUP BY 
            c.case_id, c.user_id, c.case_date, c.patient_first, c.patient_last,
            c.ins_provider, c.surgeon_id, c.facility_id, c.case_status,
            csl.case_status_desc, c.demo_file, c.note_file, c.misc_file, c.pay_amount, c.phi_encrypted,
            up.first_name, up.last_name
        ORDER BY c.case_id DESC
    """
    
    cursor.execute(sql, params)
    cases = cursor.fetchall()

    # Pre-fetch all case status descriptions to avoid N+1 queries
    cursor.execute("SELECT case_status, case_status_desc FROM case_status_list")
    status_descriptions = {row["case_status"]: row["case_status_desc"] for row in cursor.fetchall()}

    # Get database connection for decryption operations
    conn = cursor.connection
    
    # TEST USER DECRYPTION: Only decrypt for test user
    TEST_USER_ID = '54d8e448-0091-7031-86bb-d66da5e8f7e0'
    needs_decryption = (target_user_id == TEST_USER_ID)

    result = []
    for case_data in cases:
        # Decrypt PHI fields if needed (only patient names for list view)
        if needs_decryption and case_data.get('phi_encrypted') == 1:
            try:
                from utils.phi_encryption import PHIEncryption, get_user_dek
                
                # Get user's DEK for decryption
                dek = get_user_dek(target_user_id, conn)
                phi_crypto = PHIEncryption()
                
                # Only decrypt first and last name for list view
                for field in ['patient_first', 'patient_last']:
                    if field in case_data and case_data[field] is not None:
                        field_value = str(case_data[field])
                        # Skip if too short to be encrypted
                        if len(field_value) >= 28:
                            try:
                                case_data[field] = phi_crypto.decrypt_field(case_data[field], dek)
                            except Exception as field_error:
                                logging.warning(f"[DECRYPT] Could not decrypt {field} for case {case_data.get('case_id')}, leaving as-is")
                                pass
            except Exception as decrypt_error:
                logging.error(f"[DECRYPT] Failed to decrypt case {case_data.get('case_id')}: {str(decrypt_error)}")
                # Continue processing - return encrypted data rather than failing
        
        # Apply case status visibility restriction
        original_case_status = case_data["case_status"]
        if original_case_status > max_case_status:
            case_data["case_status"] = max_case_status
            # Update case_status_desc using pre-fetched lookup (no additional query needed)
            case_data["case_status_desc"] = status_descriptions.get(max_case_status, case_data["case_status_desc"])
        
        # Convert datetime to ISO format
        if case_data["case_date"]:
            case_data["case_date"] = case_data["case_date"].isoformat()
        
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
            procedure_codes = procedure_codes_json if procedure_codes_json else []
        
        # Filter out null entries and ensure proper format
        case_data['procedure_codes'] = [
            pc for pc in procedure_codes 
            if pc is not None and isinstance(pc, dict) and pc.get('procedure_code')
        ]
        
        result.append(case_data)
    
    return result

def _get_all_group_cases_optimized(cursor, requesting_user_id: str, status_list, max_case_status):
    """
    Get cases for all users in groups where requesting user is an admin.
    """
    # Get all accessible users
    accessible_users = _get_group_users(requesting_user_id, cursor)
    
    if not accessible_users:
        return []
    
    # Build optimized single query for all accessible users with provider names
    sql = """
        SELECT 
            c.user_id, c.case_id, c.case_date, c.patient_first, c.patient_last, 
            c.ins_provider, c.surgeon_id, c.facility_id, c.case_status, 
            csl.case_status_desc,
            c.demo_file, c.note_file, c.misc_file, c.pay_amount, c.phi_encrypted,
            CONCAT(COALESCE(up.first_name, ''), ' ', COALESCE(up.last_name, '')) as provider_name,
            COALESCE(
                JSON_ARRAYAGG(
                    CASE 
                        WHEN cpc.procedure_code IS NOT NULL 
                        THEN JSON_OBJECT(
                            'procedure_code', cpc.procedure_code,
                            'procedure_desc', COALESCE(cpc.procedure_desc, '')
                        )
                        ELSE NULL
                    END
                ), 
                JSON_ARRAY()
            ) as procedure_codes_json
        FROM cases c
        LEFT JOIN case_status_list csl ON c.case_status = csl.case_status
        LEFT JOIN case_procedure_codes cpc ON c.case_id = cpc.case_id
#        LEFT JOIN procedure_codes_desc pc ON cpc.procedure_code = pc.procedure_code
        LEFT JOIN user_profile up ON c.user_id = up.user_id AND up.active = 1
        WHERE c.user_id IN (%s) AND c.active = 1
    """ % (",".join(["%s"] * len(accessible_users)))
    
    params = accessible_users[:]
    
    # Add status filtering logic (same as original)
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
    
    # Group by and order
    sql += """
        GROUP BY 
            c.case_id, c.user_id, c.case_date, c.patient_first, c.patient_last,
            c.ins_provider, c.surgeon_id, c.facility_id, c.case_status,
            csl.case_status_desc, c.demo_file, c.note_file, c.misc_file, c.pay_amount, c.phi_encrypted,
            up.first_name, up.last_name
        ORDER BY c.case_id DESC
    """
    
    cursor.execute(sql, params)
    cases = cursor.fetchall()

    # Pre-fetch all case status descriptions to avoid N+1 queries
    cursor.execute("SELECT case_status, case_status_desc FROM case_status_list")
    status_descriptions = {row["case_status"]: row["case_status_desc"] for row in cursor.fetchall()}

    # Get database connection for decryption operations
    conn = cursor.connection
    
    # TEST USER DECRYPTION: Only decrypt for test user
    TEST_USER_ID = '54d8e448-0091-7031-86bb-d66da5e8f7e0'
    
    # Cache to track which user DEKs we've already loaded
    decryption_attempted_users = set()

    result = []
    for case_data in cases:
        # Decrypt PHI fields if needed (check each case's owner user_id)
        case_owner_user_id = case_data.get('user_id')
        if case_data.get('phi_encrypted') == 1 and case_owner_user_id == TEST_USER_ID:
            try:
                from utils.phi_encryption import PHIEncryption, get_user_dek
                
                # Get the case owner's DEK for decryption (cached if we've seen this user before)
                dek = get_user_dek(case_owner_user_id, conn)
                phi_crypto = PHIEncryption()
                
                # Only decrypt first and last name for group list view
                for field in ['patient_first', 'patient_last']:
                    if field in case_data and case_data[field] is not None:
                        field_value = str(case_data[field])
                        # Skip if too short to be encrypted
                        if len(field_value) >= 28:
                            try:
                                case_data[field] = phi_crypto.decrypt_field(case_data[field], dek)
                            except Exception as field_error:
                                logging.warning(f"[DECRYPT] Could not decrypt {field} for case {case_data.get('case_id')}, leaving as-is")
                                pass
                
                # Track that we've attempted decryption for this user
                if case_owner_user_id not in decryption_attempted_users:
                    decryption_attempted_users.add(case_owner_user_id)
                    logging.info(f"[DECRYPT] Decrypting group cases for user: {case_owner_user_id}")
                    
            except Exception as decrypt_error:
                logging.error(f"[DECRYPT] Failed to decrypt case {case_data.get('case_id')} for user {case_owner_user_id}: {str(decrypt_error)}")
                # Continue processing - return encrypted data rather than failing
        
        # Apply case status visibility restriction
        original_case_status = case_data["case_status"]
        if original_case_status > max_case_status:
            case_data["case_status"] = max_case_status
            # Update case_status_desc using pre-fetched lookup (no additional query needed)
            case_data["case_status_desc"] = status_descriptions.get(max_case_status, case_data["case_status_desc"])
        
        # Convert datetime to ISO format
        if case_data["case_date"]:
            case_data["case_date"] = case_data["case_date"].isoformat()
        
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
            procedure_codes = procedure_codes_json if procedure_codes_json else []
        
        # Filter out null entries and ensure proper format
        case_data['procedure_codes'] = [
            pc for pc in procedure_codes 
            if pc is not None and isinstance(pc, dict) and pc.get('procedure_code')
        ]
        
        result.append(case_data)
    
    return result

@router.get("/group_cases")
@track_business_operation("filter", "group_cases")
def get_group_cases(
    request: Request, 
    requesting_user_id: str = Query(..., description="The user ID making the request (must be group admin)"), 
    target_user_id: str = Query(None, description="Specific user ID to retrieve cases for (optional - if not provided, returns all group cases)"), 
    filter: str = Query("", description="Comma-separated list of case_status values (e.g. 0,1,2) or 'all' for all statuses"), 
):
    """
    Retrieve and filter surgical cases for group admin users with comprehensive access control.
    
    This endpoint enables group administrators to view cases belonging to users within their
    managed groups. It provides the same filtering capabilities as the standard case filter
    but with expanded access permissions based on group membership and admin privileges.
    
    Key Features:
    - Group admin permission validation with database-backed access control
    - Flexible case retrieval: specific user or all group users
    - Smart case status filtering with max_case_status support
    - Enriched case data with surgeon and facility information
    - Procedure codes with descriptions included
    - Automatic case status capping based on user permissions
    - Comprehensive monitoring and performance tracking
    - Optimized single-query implementation for performance
    - JSON aggregation for procedure codes to eliminate N+1 queries
    
    Access Control:
    - Users can always access their own cases
    - Group admins can access cases for users in their managed groups
    - Access validation performed via user_groups table lookup
    - 403 Forbidden returned for unauthorized access attempts
    
    Args:
        request (Request): FastAPI request object for logging and monitoring
        requesting_user_id (str): Unique identifier of the user making the request (required)
            - Must be a group admin to access other users' cases
            - Always has access to their own cases regardless of group admin status
        target_user_id (str, optional): Specific user whose cases to retrieve
            - If provided: Returns cases only for this user (subject to access validation)
            - If not provided: Returns cases for all users in requesting user's managed groups
        filter (str, optional): Case status filter specification:
            - "all": Returns all cases regardless of status
            - "": Empty string returns all cases (same as "all")
            - "1,2,3": Comma-separated list of specific status values
            - "20": Single status value (supports max_case_status logic)
    
    Returns:
        dict: Response containing:
            - cases (List[dict]): Array of case objects, each containing:
                - user_id (str): Owner of the case (important for group admin context)
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
                - provider_name (str): Full name of the case owner/provider (first_name last_name from user_profile)
                - surgeon_name (str): Full name of the operating surgeon (null in list view)
                - facility_name (str): Name of the surgical facility (null in list view)
                - procedure_codes (List[dict]): Array of procedure information:
                    - procedure_code (str): Medical procedure code
                    - procedure_desc (str): Description of the procedure
            - requesting_user_id (str): The user ID that made the request
            - target_user_id (str): The specific user ID queried (if provided)
            - accessible_users (List[str]): All user IDs the requesting user can access
            - filter (List): Processed filter criteria used
    
    Raises:
        HTTPException:
            - 403 Forbidden: Requesting user not authorized to access target user's cases
            - 500 Internal Server Error: Database connection or query errors
    
    Database Operations:
        1. Validates group admin permissions via user_groups table joins
        2. Retrieves requesting user's max_case_status from user_profile table
        3. Executes optimized single query with JSON aggregation for procedure codes
        4. Joins with case_status_list for status descriptions in single operation
        5. Joins with user_profile table to fetch provider names (first_name + last_name)
        6. Applies case status visibility restrictions per user permissions
        7. Eliminates N+1 queries through JSON_ARRAYAGG for procedure codes
    
    Group Admin Logic:
        - Requesting user must have group_admin = 1 in user_groups table
        - Access granted to users sharing any group with the requesting admin
        - Self-access always permitted regardless of group admin status
        - Multiple group memberships supported (user can admin multiple groups)
    
    User Permission Logic:
        - Each user has a max_case_status value in their profile (default: 20)
        - Cases with status > max_case_status are capped at max_case_status
        - Status descriptions are updated to match the capped status
        - Ensures users only see case statuses they're authorized to view
    
    Filter Logic:
        - "all" or empty: Returns all active cases for accessible users
        - Specific statuses: Returns cases matching those exact statuses
        - max_case_status handling: If max_case_status is in filter list:
            * Returns cases with that status OR higher (>= max_case_status)
            * Other specific statuses are handled normally
            * Combines both conditions with OR logic
    
    Monitoring & Logging:
        - Business metrics tracking for group case filter operations
        - Prometheus monitoring via @track_business_operation decorator
        - Execution time tracking and response logging
        - Success/failure metrics with user identification
        - Access control violation logging for security monitoring
    
    Performance Features:
        - Optimized queries with proper JOIN usage
        - Batch procedure code fetching with JSON aggregation
        - Efficient duplicate removal for procedure codes
        - Cases ordered by case_id DESC for most recent first
        - Only active cases retrieved (active = 1)
        - Single query for multiple user access when target_user_id not specified
    
    Example Usage:
        # Get all cases for users in requesting user's managed groups
        GET /group_cases?requesting_user_id=ADMIN123&filter=1,2,20
        
        # Get specific user's cases (if admin has access)
        GET /group_cases?requesting_user_id=ADMIN123&target_user_id=USER456&filter=all
        
        # Get all cases with no status filter
        GET /group_cases?requesting_user_id=ADMIN123
    
    Example Response:
        {
            "cases": [
                {
                    "user_id": "USER456",
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
                    "provider_name": "Dr. Jane Smith",
                    "surgeon_name": null,
                    "facility_name": null,
                    "procedure_codes": [
                        {
                            "procedure_code": "12345",
                            "procedure_desc": "Laparoscopic Cholecystectomy"
                        }
                    ]
                }
            ],
            "requesting_user_id": "ADMIN123",
            "target_user_id": "USER456",
            "accessible_users": ["ADMIN123", "USER456", "USER789"],
            "filter": [1, 2, 20]
        }
    
    Security Considerations:
        - All access is validated through database-backed group membership
        - No case data returned without explicit permission validation
        - Group admin privileges are checked on every request
        - Audit trail maintained through comprehensive logging
        - Case status visibility restricted based on user profile permissions
    
    Note:
        - Only active cases (active=1) are returned
        - Case statuses are automatically restricted based on user permissions
        - Procedure codes include both code and description for UI display
        - Cases are ordered by case_id in descending order (newest first)
        - Empty procedure_codes array is included if no procedures exist
        - Date fields are converted to ISO format for consistent API responses
        - User ownership clearly indicated in response for group admin context
        - Provider names are fetched from user_profile table for easy identification
        - Surgeon and facility names are null in list view for performance
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
                # Get requesting user's max_case_status from user_profile
                cursor.execute("""
                    SELECT max_case_status 
                    FROM user_profile 
                    WHERE user_id = %s AND active = 1
                """, (requesting_user_id,))
                user_profile = cursor.fetchone()
                
                if not user_profile:
                    # If user profile not found, use default max_case_status of 20
                    max_case_status = 20
                else:
                    max_case_status = user_profile["max_case_status"] or 20
                
                # Determine which cases to retrieve
                if target_user_id:
                    # Get cases for specific user (with permission validation)
                    result = _get_group_cases_optimized(cursor, requesting_user_id, target_user_id, status_list, max_case_status)
                    accessible_users = _get_group_users(requesting_user_id, cursor)
                else:
                    # Get cases for all users in requesting user's managed groups
                    result = _get_all_group_cases_optimized(cursor, requesting_user_id, status_list, max_case_status)
                    accessible_users = _get_group_users(requesting_user_id, cursor)
                
                # Record successful group case filtering
                business_metrics.record_case_operation("group_filter", "success", f"requesting_user_{requesting_user_id}")
            
        finally:
            close_db_connection(conn)
            
        response_data = {
            "cases": result,
            "requesting_user_id": requesting_user_id,
            "target_user_id": target_user_id,
            "accessible_users": accessible_users,
            "filter": status_list
        }
        return response_data

    except HTTPException as http_error:
        # Re-raise HTTP exceptions and capture error details
        response_status = http_error.status_code
        error_message = str(http_error.detail)
        business_metrics.record_case_operation("group_filter", "access_denied", f"requesting_user_{requesting_user_id}")
        raise
    except Exception as e:
        response_status = 500
        error_message = str(e)
        business_metrics.record_case_operation("group_filter", "error", f"requesting_user_{requesting_user_id}")
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
            user_id=requesting_user_id,
            response_data=response_data,
            error_message=error_message
        )
