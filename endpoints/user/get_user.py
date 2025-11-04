# Created: 2025-07-15 09:20:13
# Last Modified: 2025-10-03 18:49:22
# Author: Scott Cadreau

# endpoints/user/get_user.py
from fastapi import APIRouter, HTTPException, Query, Request
import pymysql.cursors
from core.database import get_db_connection, close_db_connection
from utils.monitoring import track_business_operation, business_metrics
import time

router = APIRouter()

@router.get("/user")
@track_business_operation("read", "user")
def get_user(request: Request, user_id: str = Query(..., description="The user ID to retrieve")):
    """
    Retrieve comprehensive user profile information including personal details and associated documents.
    
    This endpoint fetches complete user profile data from the user_profile table along with all
    associated documents from the user_documents table. Only active users are returned,
    ensuring soft-deleted users are properly excluded from system access.
    
    Key Features:
    - Complete user profile retrieval with validation
    - Associated document metadata inclusion
    - Active user filtering (soft-delete protection)
    - Comprehensive error handling and monitoring
    - Professional information access (NPI, licensing, etc.)
    - Contact and address information retrieval
    - User type and preference information
    
    Args:
        request (Request): FastAPI request object for logging and monitoring
        user_id (str): Unique identifier of the user to retrieve (required query parameter)
    
    Returns:
        dict: Response containing:
            - user (dict): Complete user profile object with:
                - user_id (str): Unique user identifier
                - user_email (str): User's email address
                - first_name (str): User's first name
                - last_name (str): User's last name
                - addr1 (str): Primary address line
                - addr2 (str): Secondary address line
                - city (str): City of residence
                - state (str): State/province of residence
                - zipcode (str): Postal/ZIP code
                - telephone (str): Primary phone number
                - user_npi (str): National Provider Identifier for healthcare professionals
                - referred_by_user (str): ID of referring user
                - user_type (str): User classification/role type
                - user_type_desc (str): Human-readable description of the user type
                - message_pref (str): Communication preference settings
                - states_licensed (str): States where user holds professional licenses
                - user_tier (int): User tier classification for billing/permissions
                - credentials (str): User's professional credentials (e.g., MD, DO, PA, NP, CSA, PA-C)
                - ins_exp_date (str): Malpractice insurance expiration date in ISO format (YYYY-MM-DD)
                - create_ts (timestamp): Timestamp when the user account was created
                - last_updated_ts (timestamp): Timestamp when the user account was last updated
                - last_login_dt (timestamp): Date and time of the user's last login
                - documents (List[dict]): Array of user documents:
                    - document_type (str): Type/category of document
                    - document_name (str): Name/path of the document file
            - user_id (str): The user ID that was requested (for convenience)
    
    Raises:
        HTTPException:
            - 400 Bad Request: Missing user_id parameter
            - 404 Not Found: User does not exist or is inactive (soft-deleted)
            - 500 Internal Server Error: Database connection or query errors
    
    Database Operations:
        1. Validates user_id parameter presence
        2. Queries user_profile table for active user data
        3. Fetches associated documents from user_documents table
        4. Combines profile and document data into unified response
        5. Ensures only active users (active=1) are accessible
    
    Active User Filtering:
        - Only users with active=1 status are returned
        - Soft-deleted users (active=0) return 404 Not Found
        - This ensures deactivated users cannot access the system
        - Maintains data integrity while preserving audit trails
    
    Document Integration:
        - Fetches all documents associated with the user
        - Documents include type classification and file references
        - Empty documents array returned if no documents exist
        - Document metadata only (actual files stored separately)
    
    Professional Information:
        - NPI (National Provider Identifier) for healthcare professionals
        - State licensing information for regulatory compliance
        - User type classification for role-based access control
        - Referral chain information for business relationships
    
    Monitoring & Logging:
        - Business metrics tracking for user read operations
        - Prometheus monitoring via @track_business_operation decorator
        - Execution time tracking and detailed response logging
        - Error categorization for different failure types:
            * not_found: User doesn't exist or is inactive
            * success: User data retrieved successfully
            * error: General database or connection errors
    
    Security Features:
        - Only active users can be retrieved
        - Soft-deleted users properly excluded
        - All database queries use parameterized statements
        - No sensitive authentication data included in response
    
    Performance Optimizations:
        - Single database connection for all operations
        - Efficient JOIN-like operations with separate queries
        - Proper connection management with automatic cleanup
        - Minimal database round trips
    
    Data Integrity:
        - Consistent user data retrieval
        - Document associations properly maintained
        - Active status validation prevents access to deactivated accounts
        - Transactional data consistency
    
    Example Usage:
        GET /user?user_id=USER123
    
    Example Response:
        {
            "user": {
                "user_id": "USER123",
                "user_email": "doctor@example.com",
                "first_name": "Dr. Jane",
                "last_name": "Smith",
                "addr1": "123 Medical Center Dr",
                "addr2": "Suite 456",
                "city": "Healthcare City",
                "state": "CA",
                "zipcode": "90210",
                "telephone": "+1-555-0123",
                "user_npi": "1234567890",
                "referred_by_user": "ADMIN001",
                "user_type": "physician",
                "user_type_desc": "Licensed Physician",
                "message_pref": "email",
                "states_licensed": "CA,NY,TX",
                "user_tier": 1,
                "credentials": "MD",
                "ins_exp_date": "2025-12-31",
                "create_ts": "2024-01-15T09:30:00",
                "last_updated_ts": "2024-08-10T14:22:33",
                "last_login_dt": "2024-08-10T08:45:12",
                "documents": [
                    {
                        "document_type": "medical_license",
                        "document_name": "ca_medical_license.pdf"
                    },
                    {
                        "document_type": "malpractice_insurance", 
                        "document_name": "insurance_cert_2024.pdf"
                    }
                ]
            },
            "user_id": "USER123"
        }
    
    Example Error Response (Not Found):
        {
            "error": "User not found",
            "user_id": "INVALID_USER"
        }
    
    Note:
        - Only active users (active=1) are accessible through this endpoint
        - Soft-deleted users return 404 to maintain security
        - Documents array will be empty if no documents are associated
        - All user profile fields may be null depending on data completeness
        - NPI and licensing information only relevant for healthcare professionals
        - User type determines available system functionality
        - Document files are stored separately; only metadata is returned
        - Timezone information affects user experience but not core functionality
        - Communication preferences control system notification behavior
    """
    conn = None
    start_time = time.time()
    response_status = 200
    response_data = None
    error_message = None
    
    try:
        if not user_id:
            response_status = 400
            error_message = "Missing user_id parameter"
            raise HTTPException(status_code=400, detail="Missing user_id parameter")

        conn = get_db_connection()

        try:
            with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                # fetch from users table with user type description
                cursor.execute("""select up.user_id, up.user_email, up.first_name, up.last_name, up.addr1, up.addr2, up.city, up.state, up.zipcode, up.telephone, up.user_npi, 
                    up.referred_by_user, up.user_type, utl.user_type_desc, up.message_pref, up.states_licensed, up.user_tier, up.create_ts, up.last_updated_ts, up.last_login_dt, 
                    up.max_case_status, up.credentials, up.ins_exp_date
                    from user_profile up
                    left join user_type_list utl on up.user_type = utl.user_type
                    where up.user_id = %s and up.active = 1""", (user_id))
                user_data = cursor.fetchone()

                if not user_data:
                    # Record failed user read operation
                    business_metrics.record_user_operation("read", "not_found", user_id)
                    response_status = 404
                    error_message = "User not found"
                    raise HTTPException(
                        status_code=404, 
                        detail={"error": "User not found", "user_id": user_id}
                    )

                # fetch user documents
                cursor.execute("""SELECT document_type, document_name FROM user_documents WHERE user_id = %s""", (user_id,))
                docs = [{"document_type": row['document_type'], "document_name": row['document_name']} for row in cursor.fetchall()]
                user_data['documents'] = docs

            # Record successful user read operation
            business_metrics.record_user_operation("read", "success", user_id)

        finally:
            close_db_connection(conn)

        response_data = {
            "user": user_data,
            "user_id": user_data["user_id"]
        }
        return response_data

    except HTTPException as http_error:
        # Re-raise HTTP exceptions and capture error details
        response_status = http_error.status_code
        error_message = str(http_error.detail)
        raise
    except Exception as e:
        # Record failed user read operation
        response_status = 500
        error_message = str(e)
        business_metrics.record_user_operation("read", "error", user_id)
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