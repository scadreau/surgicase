# Created: 2025-07-15 09:20:13
# Last Modified: 2025-08-06 15:18:59
# Author: Scott Cadreau

# endpoints/user/create_user.py
from fastapi import APIRouter, HTTPException, Request
import pymysql.cursors
from core.database import get_db_connection, close_db_connection, is_connection_valid
from core.models import UserCreate
from utils.monitoring import track_business_operation, business_metrics
import time

router = APIRouter()

@router.post("/user")
@track_business_operation("create", "user")
def add_user(request: Request, user: UserCreate):
    """
    Create a new user profile with comprehensive personal and professional information.
    
    This endpoint creates a complete user profile including personal information, contact details,
    professional credentials, and associated documents. The operation includes duplicate prevention,
    transactional data integrity, and comprehensive monitoring for the surgical case management system.
    
    Key Features:
    - Complete user profile creation with validation
    - Duplicate user prevention with meaningful error responses
    - Optional document management for user credentials
    - Transactional operations ensuring data consistency
    - Comprehensive monitoring and business metrics tracking
    - Professional information tracking (NPI, licensing, etc.)
    - Referral tracking and user type management
    
    Args:
        request (Request): FastAPI request object for logging and monitoring
        user (UserCreate): User creation model containing:
            - user_id (str): Unique identifier for the user (required)
            - user_email (str): User's email address
            - first_name (str): User's first name
            - last_name (str): User's last name
            - addr1 (str): Primary address line
            - addr2 (str, optional): Secondary address line
            - city (str): City of residence
            - state (str): State/province of residence
            - zipcode (str): Postal/ZIP code
            - telephone (str): Primary phone number
            - user_npi (str, optional): National Provider Identifier for healthcare professionals
            - referred_by_user (str, optional): ID of referring user
            - message_pref (str, optional): Communication preference settings
            - states_licensed (str, optional): States where user holds professional licenses
            - timezone (str, optional): User's timezone preference
            - documents (List[UserDocument], optional): List of user documents:
                - document_type (str): Type/category of document
                - document_name (str): Name/path of the document file
    
    Returns:
        dict: Response containing:
            - statusCode (int): HTTP status code (201 for success)
            - body (dict): Response body with:
                - message (str): Success confirmation message
                - user_id (str): The created user identifier
    
    Raises:
        HTTPException:
            - 400 Bad Request: User with the same user_id already exists
            - 500 Internal Server Error: Database errors or transaction failures
    
    Database Operations:
        1. Validates user_id uniqueness in user_profile table
        2. Inserts comprehensive user profile data into user_profile table
        3. Optionally inserts user documents into user_documents table
        4. All operations performed within a single transaction
        5. Automatic rollback on any operation failure
    
    Business Logic:
        - Enforces unique user_id constraint across the system
        - Supports flexible document attachment for credentials/certifications
        - Professional information tracking for healthcare provider verification
        - Referral chain tracking for business intelligence
        - User type classification for role-based access control
        - Timezone and communication preference management
    
    Document Management:
        - Optional document attachment during user creation
        - Multiple document types supported per user
        - Document metadata stored in separate user_documents table
        - Batch document insertion with transactional integrity
        - Document type categorization for organized storage
    
    Professional Information:
        - NPI (National Provider Identifier) storage for healthcare professionals
        - State licensing information for regulatory compliance
        - Referral tracking for business relationship management
        - User type classification for system permissions
    
    Monitoring & Logging:
        - Business metrics tracking for user creation operations
        - Prometheus monitoring via @track_business_operation decorator
        - Detailed execution time and response logging
        - Error categorization for different failure types:
            * duplicate: User already exists with same ID
            * success: User created successfully
            * error: General database or system errors
    
    Transaction Management:
        - Explicit transaction control for data consistency
        - Automatic rollback on any operation failure
        - Connection state validation before rollback attempts
        - Proper database connection cleanup
    
    Validation & Security:
        - Duplicate user_id prevention at database level
        - All database queries use parameterized statements
        - Comprehensive input validation via UserCreate model
        - Transaction-based operations prevent partial data states
    
    Example Request:
        POST /user
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
            "message_pref": "email",
            "states_licensed": "CA,NY,TX",
            "timezone": "America/Los_Angeles",
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
        }
    
    Example Response (Success):
        {
            "statusCode": 201,
            "body": {
                "message": "User created successfully",
                "user_id": "USER123"
            }
        }
    
    Example Response (Duplicate User):
        {
            "error": "User already exists",
            "user_id": "USER123"
        }
    
    Note:
        - All fields except user_id can be null/optional based on business requirements
        - Documents array is completely optional and can be empty
        - User creation automatically sets active=1 (default database behavior)
        - NPI validation should be performed at the application level if required
        - State licensing format is flexible but typically comma-separated state codes
        - Document files should be uploaded to appropriate storage before user creation
        - Referral chains can be tracked through the referred_by_user field
        - User type defaults are handled by database constraints/triggers
    """
    conn = None
    start_time = time.time()
    response_status = 201
    response_data = None
    error_message = None
    
    try:
        conn = get_db_connection()
        
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            # Check if user already exists
            cursor.execute("SELECT user_id FROM user_profile WHERE user_id = %s", (user.user_id,))
            if cursor.fetchone():
                # Record failed user creation (duplicate)
                business_metrics.record_user_operation("create", "duplicate", user.user_id)
                response_status = 400
                error_message = "User already exists"
                raise HTTPException(status_code=400, detail={"error": "User already exists", "user_id": user.user_id})

            # Insert new user
            cursor.execute("""
                INSERT INTO user_profile (
                    user_id, user_email, first_name, last_name, addr1, addr2, city, state, zipcode, telephone, user_npi, referred_by_user, message_pref, states_licensed, timezone
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                user.user_id, user.user_email, user.first_name, user.last_name, user.addr1, user.addr2,
                user.city, user.state, user.zipcode, user.telephone, user.user_npi, user.referred_by_user, user.message_pref, user.states_licensed, user.timezone
            ))
            # Insert user documents if provided
            if user.documents:
                for doc in user.documents:
                    cursor.execute(
                        """
                        INSERT INTO user_documents (user_id, document_type, document_name)
                        VALUES (%s, %s, %s)
                        """,
                        (user.user_id, doc.document_type, doc.document_name)
                    )
            conn.commit()
            
            # Record successful user creation
            business_metrics.record_user_operation("create", "success", user.user_id)
            
        response_data = {
            "statusCode": 201,
            "body": {
                "message": "User created successfully",
                "user_id": user.user_id
            }
        }
        return response_data

    except HTTPException as http_error:
        # Re-raise HTTP exceptions and capture error details
        response_status = http_error.status_code
        error_message = str(http_error.detail)
        raise
    except Exception as e:
        # Record failed user creation
        response_status = 500
        error_message = str(e)
        business_metrics.record_user_operation("create", "error", user.user_id)
        
        # Safe rollback with connection state check
        if conn and is_connection_valid(conn):
            try:
                conn.rollback()
            except (pymysql.err.InterfaceError, pymysql.err.OperationalError) as rollback_error:
                # Log rollback error but don't raise it
                print(f"Rollback failed: {rollback_error}")
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
            user_id=user.user_id,
            response_data=response_data,
            error_message=error_message
        )
        
        # Always close the connection
        if conn:
            close_db_connection(conn)