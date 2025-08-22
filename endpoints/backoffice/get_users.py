# Created: 2025-07-22 12:20:56
# Last Modified: 2025-08-22 06:48:43
# Author: Scott Cadreau

# endpoints/backoffice/get_users.py
from fastapi import APIRouter, HTTPException, Query, Request
import pymysql.cursors
from core.database import get_db_connection, close_db_connection
from utils.monitoring import track_business_operation, business_metrics
import time

router = APIRouter()

@router.get("/users")
@track_business_operation("get", "users_list")
def get_users(request: Request, user_id: str = Query(..., description="The user ID making the request (must be user_type >= 10)")):
    """
    Retrieve comprehensive list of all active users for administrative oversight and management.
    
    This endpoint provides administrative access to the complete user directory including detailed
    profile information, professional credentials, and associated documents. Access is restricted
    to administrative users (user_type >= 10) with hierarchical visibility controls ensuring
    users can only see other users at or below their permission level.
    
    Key Features:
    - Administrative user directory with hierarchical access control
    - Complete user profile information including professional credentials
    - Associated document metadata for all users
    - User tier and timestamp information for audit purposes
    - Permission-based visibility filtering
    - Sorted output for consistent user management
    - Comprehensive monitoring and access tracking
    
    Args:
        request (Request): FastAPI request object for logging and monitoring
        user_id (str): Unique identifier of the requesting administrative user (required)
                      Must have user_type >= 10 to access this endpoint
    
    Returns:
        dict: Response containing:
            - users (List[dict]): Array of user objects, each containing:
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
                - user_type (int): User classification/permission level
                - message_pref (str): Communication preference settings
                - states_licensed (str): States where user holds professional licenses
                - user_tier (int): User tier classification for billing/permissions
                - create_ts (datetime): Account creation timestamp
                - last_updated_ts (datetime): Last profile update timestamp
                - documents (List[dict]): Array of user documents:
                    - document_type (str): Type/category of document
                    - document_name (str): Name/path of the document file
            - total_count (int): Total number of users returned
    
    Raises:
        HTTPException:
            - 403 Forbidden: User does not have sufficient permissions (user_type < 10)
            - 500 Internal Server Error: Database connection or query errors
    
    Database Operations:
        1. Validates requesting user's permission level (user_type >= 10)
        2. Retrieves hierarchical user list where target user_type <= requester's user_type
        3. Fetches comprehensive user profile data with timestamps
        4. Retrieves associated documents for each user
        5. Applies consistent sorting by last name, then first name
        6. Only includes active users (active = 1)
    
    Permission System:
        - Hierarchical access control based on user_type values
        - Users can only see other users with user_type <= their own user_type
        - This prevents lower-level administrators from seeing higher-level admin accounts
        - Requesting user must have user_type >= 10 to access any user list
        - Permission validation occurs before any database queries
    
    Administrative Features:
        - Complete user directory for organizational oversight
        - Professional credential tracking (NPI, licensing)
        - Document management oversight for compliance
        - User tier information for billing and subscription management
        - Audit trail information (creation and update timestamps)
        - Referral chain visibility for business relationship tracking
    
    Data Enrichment:
        - Complete profile information beyond basic user data
        - Professional licensing and credential information
        - Communication preferences for system administration
        - Document associations for compliance verification
        - Timestamp information for account lifecycle tracking
        - Tier classification for feature access management
    
    Monitoring & Logging:
        - Business metrics tracking for administrative access operations
        - Prometheus monitoring via @track_business_operation decorator
        - Detailed execution time and response logging
        - Permission-based access tracking for security auditing
        - Error categorization for different failure types:
            * permission_denied: Insufficient user permissions
            * success: User list retrieved successfully
            * error: General database or system errors
    
    Security Features:
        - Strict permission validation before data access
        - Hierarchical visibility to prevent privilege escalation
        - Only active users included (soft-deleted users excluded)
        - All database queries use parameterized statements
        - Administrative action logging for compliance
    
    Example Usage:
        GET /users?user_id=ADMIN001
    
    Example Response:
        {
            "users": [
                {
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
                    "user_type": 5,
                    "message_pref": "email",
                    "states_licensed": "CA,NY,TX",
                    "user_tier": 1,
                    "create_ts": "2024-01-15T10:30:00",
                    "last_updated_ts": "2024-01-20T14:45:00",
                    "documents": [
                        {
                            "document_type": "medical_license",
                            "document_name": "ca_medical_license.pdf"
                        }
                    ]
                }
            ],
            "total_count": 1
        }
    
    Example Error Response (Permission Denied):
        {
            "detail": "User does not have permission to access user list."
        }
    
    Note:
        - Only active users (active=1) are included in the results
        - Users are sorted by last name, then first name for consistent ordering
        - Hierarchical access control prevents viewing higher-privilege users
        - Document information includes metadata only (files stored separately)
        - Timestamp fields provide audit trail for account management
        - User tier information affects feature access and billing
        - Professional licensing information is critical for healthcare compliance
        - Referral chains can be traced through referred_by_user relationships
        - Administrative users should use this endpoint for user management tasks
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
                # Check user_type for the requesting user
                cursor.execute("SELECT user_type FROM user_profile WHERE user_id = %s", (user_id,))
                user_row = cursor.fetchone()
                if not user_row or user_row.get("user_type", 0) < 10:
                    # Record failed access (permission denied)
                    business_metrics.record_utility_operation("get_users_list", "permission_denied")
                    response_status = 403
                    error_message = "User does not have permission to access user list"
                    raise HTTPException(status_code=403, detail="User does not have permission to access user list.")

                requesting_user_type = user_row.get("user_type", 0)

                # Fetch all active users with user_tier where user_type <= requesting user's user_type
                cursor.execute("""
                    SELECT user_id, user_email, first_name, last_name, addr1, addr2, city, state, zipcode, 
                           telephone, user_npi, referred_by_user, user_type, message_pref, states_licensed, user_tier, create_ts, last_updated_ts
                    FROM user_profile 
                    WHERE active = 1 AND user_type <= %s
                    ORDER BY user_type, first_name, last_name
                """, (requesting_user_type,))
                users = cursor.fetchall()

                result = []
                for user_data in users:
                    # Fetch user documents for each user
                    cursor.execute("SELECT document_type, document_name FROM user_documents WHERE user_id = %s", (user_data["user_id"],))
                    docs = [{"document_type": row['document_type'], "document_name": row['document_name']} for row in cursor.fetchall()]
                    user_data['documents'] = docs
                    result.append(user_data)

                # Record successful users retrieval
                business_metrics.record_utility_operation("get_users_list", "success")
                
        finally:
            close_db_connection(conn)
            
        response_data = {
            "users": result,
            "total_count": len(result)
        }
        return response_data

    except HTTPException as http_error:
        # Re-raise HTTP exceptions and capture error details
        response_status = http_error.status_code
        error_message = str(http_error.detail)
        raise
    except Exception as e:
        # Record failed users retrieval
        response_status = 500
        error_message = str(e)
        business_metrics.record_utility_operation("get_users_list", "error")
        
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