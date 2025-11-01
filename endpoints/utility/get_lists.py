# Created: 2025-08-05 22:15:27
# Last Modified: 2025-11-01 02:52:38
# Author: Scott Cadreau

# endpoints/utility/get_lists.py
from fastapi import APIRouter, HTTPException, Request, Query
import pymysql.cursors
from core.database import get_db_connection, close_db_connection
from utils.monitoring import track_business_operation, business_metrics
import time

router = APIRouter()

def validate_user_access(user_id: str, conn) -> bool:
    """
    Validate that the user has user_type >= 100 to access list endpoints.
    Returns True if authorized, raises HTTPException if not.
    """
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute(
                "SELECT user_type FROM user_profile WHERE user_id = %s AND active = 1",
                (user_id,)
            )
            user = cursor.fetchone()
            
            if not user:
                raise HTTPException(status_code=404, detail={"error": "User not found or inactive"})
            
            if user['user_type'] < 100:
                raise HTTPException(status_code=403, detail={"error": "Insufficient privileges. User type must be >= 100"})
            
            return True
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail={"error": f"Error validating user access: {str(e)}"})

def validate_tiers_summary_access(user_id: str, conn) -> bool:
    """
    Validate that the user has user_type >= 20 to access tiers summary endpoint.
    Returns True if authorized, raises HTTPException if not.
    """
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute(
                "SELECT user_type FROM user_profile WHERE user_id = %s AND active = 1",
                (user_id,)
            )
            user = cursor.fetchone()
            
            if not user:
                raise HTTPException(status_code=404, detail={"error": "User not found or inactive"})
            
            if user['user_type'] < 20:
                raise HTTPException(status_code=403, detail={"error": "Insufficient privileges. User type must be >= 20"})
            
            return True
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail={"error": f"Error validating user access: {str(e)}"})

def validate_user_exists(user_id: str, conn) -> bool:
    """
    Validate that the user exists and is active.
    Returns True if user is valid, raises HTTPException if not.
    No user_type restrictions - all active users are allowed.
    """
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute(
                "SELECT user_id FROM user_profile WHERE user_id = %s AND active = 1",
                (user_id,)
            )
            user = cursor.fetchone()
            
            if not user:
                raise HTTPException(status_code=404, detail={"error": "User not found or inactive"})
            
            return True
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail={"error": f"Error validating user: {str(e)}"})

@router.get("/user_types")
@track_business_operation("get", "user_types")
def get_user_types(request: Request, user_id: str = Query(..., description="User ID for authorization")):
    """
    Retrieve all user types below administrative level for role management and assignment.
    
    This endpoint provides access to the user type hierarchy used throughout the application
    for role-based access control, permission management, and user categorization. It returns
    all user types with type value less than 1000, excluding high-level administrative roles
    that are restricted from general visibility.
    
    Args:
        request (Request): FastAPI request object for logging and monitoring
        user_id (str): User ID for authorization validation.
                      Must have user_type >= 100 for access to this administrative data.
    
    Returns:
        dict: Response containing:
            - user_types (List[dict]): Array of user type objects, each containing:
                - user_type (int): Numeric user type identifier/level
                - user_type_desc (str): Human-readable description of the user type
                - user_max_case_status (int): Maximum case status this user type can access
    
    Raises:
        HTTPException:
            - 404 Not Found: User not found or inactive in user_profile table
            - 403 Forbidden: User has insufficient privileges (user_type < 100)
            - 500 Internal Server Error: Database connection or query execution errors
    
    Authorization:
        - Requires user_type >= 100 for access to user type management data
        - Uses validate_user_access() helper function for consistent authorization
        - Validates user exists and is active in user_profile table
    
    Database Operations:
        - Queries 'user_type_list' table for types where user_type < 1000
        - Filters out high-level administrative roles (>= 1000)
        - Returns role hierarchy information for permission calculations
        - Read-only operation with automatic connection management
    
    Monitoring & Logging:
        - Business metrics tracking for user type retrieval operations
        - Prometheus monitoring via @track_business_operation decorator
        - Comprehensive request logging with user ID tracking
        - Authorization failure tracking for security monitoring
    
    Example Response:
        {
            "user_types": [
                {
                    "user_type": 100,
                    "user_type_desc": "Basic User",
                    "user_max_case_status": 3
                },
                {
                    "user_type": 200,
                    "user_type_desc": "Advanced User", 
                    "user_max_case_status": 5
                },
                {
                    "user_type": 500,
                    "user_type_desc": "Manager",
                    "user_max_case_status": 8
                }
            ]
        }
    
    Usage:
        GET /user_types?user_id=USER123
        
    Notes:
        - Excludes super-administrative roles (user_type >= 1000) for security
        - user_max_case_status determines case visibility and access permissions
        - Used for populating user type dropdown lists in administrative interfaces
        - Essential for role-based access control throughout the application
        - Authorization required to prevent unauthorized access to user hierarchy information
    """
    conn = None
    start_time = time.time()
    response_status = 200
    response_data = None
    error_message = None
    
    try:
        conn = get_db_connection()
        
        # Validate user access
        validate_user_access(user_id, conn)
        
        try:
            with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                cursor.execute(
                    "SELECT user_type, user_type_desc, user_max_case_status FROM user_type_list WHERE user_type < 1000"
                )
                user_types = cursor.fetchall()

                # Record successful user types retrieval
                business_metrics.record_utility_operation("get_user_types", "success")
                
        finally:
            close_db_connection(conn)
            
        response_data = {
            "user_types": user_types
        }
        return response_data
        
    except HTTPException as http_error:
        # Re-raise HTTP exceptions and capture error details
        response_status = http_error.status_code
        error_message = str(http_error.detail)
        raise
    except Exception as e:
        # Record failed user types retrieval
        response_status = 500
        error_message = str(e)
        business_metrics.record_utility_operation("get_user_types", "error")
        
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

@router.get("/case_statuses")
@track_business_operation("get", "case_statuses")
def get_case_statuses(request: Request, user_id: str = Query(..., description="User ID for authorization")):
    """
    Retrieve all available case status levels for case management and workflow control.
    
    This endpoint provides access to the complete case status hierarchy used throughout
    the application for case lifecycle management, workflow automation, and access control.
    Case statuses define the progression of surgical cases from initial creation through
    completion and payment processing.
    
    Args:
        request (Request): FastAPI request object for logging and monitoring
        user_id (str): User ID for authorization validation.
                      Must have user_type >= 100 for access to case management data.
    
    Returns:
        dict: Response containing:
            - case_statuses (List[dict]): Array of case status objects, each containing:
                - case_status (int): Numeric case status identifier/level
                - case_status_desc (str): Human-readable description of the case status
    
    Raises:
        HTTPException:
            - 404 Not Found: User not found or inactive in user_profile table
            - 403 Forbidden: User has insufficient privileges (user_type < 100)
            - 500 Internal Server Error: Database connection or query execution errors
    
    Authorization:
        - Requires user_type >= 100 for access to case status management data
        - Uses validate_user_access() helper function for consistent authorization
        - Validates user exists and is active in user_profile table
    
    Database Operations:
        - Queries 'case_status_list' table for all available case statuses
        - Returns complete status hierarchy for workflow management
        - Read-only operation with automatic connection management
        - Results may be ordered by case_status value (database default)
    
    Monitoring & Logging:
        - Business metrics tracking for case status retrieval operations
        - Prometheus monitoring via @track_business_operation decorator
        - Comprehensive request logging with user ID tracking
        - Authorization failure tracking for security monitoring
    
    Example Response:
        {
            "case_statuses": [
                {
                    "case_status": 1,
                    "case_status_desc": "Draft"
                },
                {
                    "case_status": 2,
                    "case_status_desc": "Submitted"
                },
                {
                    "case_status": 3,
                    "case_status_desc": "In Review"
                },
                {
                    "case_status": 4,
                    "case_status_desc": "Approved"
                },
                {
                    "case_status": 5,
                    "case_status_desc": "Completed"
                }
            ]
        }
    
    Usage:
        GET /case_statuses?user_id=USER123
        
    Notes:
        - Case status levels determine user access permissions and workflow progression
        - Used for populating case status dropdown lists in case management interfaces
        - Essential for case lifecycle management and automated status transitions
        - Authorization required to prevent unauthorized access to case workflow information
        - Integrates with user_max_case_status for role-based case access control
    """
    conn = None
    start_time = time.time()
    response_status = 200
    response_data = None
    error_message = None
    
    try:
        conn = get_db_connection()
        
        # Validate user access
        validate_user_access(user_id, conn)
        
        try:
            with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                cursor.execute(
                    "SELECT case_status, case_status_desc FROM case_status_list"
                )
                case_statuses = cursor.fetchall()

                # Record successful case statuses retrieval
                business_metrics.record_utility_operation("get_case_statuses", "success")
                
        finally:
            close_db_connection(conn)
            
        response_data = {
            "case_statuses": case_statuses
        }
        return response_data
        
    except HTTPException as http_error:
        # Re-raise HTTP exceptions and capture error details
        response_status = http_error.status_code
        error_message = str(http_error.detail)
        raise
    except Exception as e:
        # Record failed case statuses retrieval
        response_status = 500
        error_message = str(e)
        business_metrics.record_utility_operation("get_case_statuses", "error")
        
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

@router.get("/user_doc_types")
@track_business_operation("get", "user_doc_types")
def get_user_doc_types(request: Request, user_id: str = Query(..., description="User ID for authorization")):
    """
    Retrieve all available user document types for document management and categorization.
    
    This endpoint provides access to the document type categories used for organizing
    and classifying user-uploaded documents such as licenses, certifications, insurance
    documents, and other professional credentials. The document types include both
    the display name and file naming prefix for systematic document organization.
    
    Args:
        request (Request): FastAPI request object for logging and monitoring
        user_id (str): User ID for authorization validation.
                      All active users can access this endpoint.
    
    Returns:
        dict: Response containing:
            - user_doc_types (List[dict]): Array of document type objects, each containing:
                - doc_type (str): Human-readable document type category name
                - doc_prefix (str): File naming prefix used for systematic document organization
    
    Raises:
        HTTPException:
            - 404 Not Found: User not found or inactive in user_profile table
            - 500 Internal Server Error: Database connection or query execution errors
    
    Authorization:
        - All active users can access this endpoint
        - Uses validate_user_exists() helper function for user validation
        - Validates user exists and is active in user_profile table
    
    Database Operations:
        - Queries 'user_doc_type_list' table for all available document types
        - Returns document categorization and file naming information
        - Read-only operation with automatic connection management
        - Results may be ordered by doc_type (database default)
    
    Monitoring & Logging:
        - Business metrics tracking for user document type retrieval operations
        - Prometheus monitoring via @track_business_operation decorator
        - Comprehensive request logging with user ID tracking
        - Authorization failure tracking for security monitoring
    
    Example Response:
        {
            "user_doc_types": [
                {
                    "doc_type": "Medical License",
                    "doc_prefix": "LIC"
                },
                {
                    "doc_type": "Board Certification",
                    "doc_prefix": "CERT"
                },
                {
                    "doc_type": "DEA Registration",
                    "doc_prefix": "DEA"
                },
                {
                    "doc_type": "Malpractice Insurance",
                    "doc_prefix": "INS"
                }
            ]
        }
    
    Usage:
        GET /user_doc_types?user_id=USER123
        
    Notes:
        - doc_prefix is used for systematic file naming and organization in document storage
        - Used for populating document type dropdown lists in document upload interfaces
        - Essential for document categorization and retrieval systems
        - Available to all users for document upload and management workflows
    """
    conn = None
    start_time = time.time()
    response_status = 200
    response_data = None
    error_message = None
    
    try:
        conn = get_db_connection()
        
        # Validate user exists
        validate_user_exists(user_id, conn)
        
        try:
            with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                cursor.execute(
                    "SELECT doc_type, doc_prefix FROM user_doc_type_list"
                )
                user_doc_types = cursor.fetchall()

                # Record successful user doc types retrieval
                business_metrics.record_utility_operation("get_user_doc_types", "success")
                
        finally:
            close_db_connection(conn)
            
        response_data = {
            "user_doc_types": user_doc_types
        }
        return response_data
        
    except HTTPException as http_error:
        # Re-raise HTTP exceptions and capture error details
        response_status = http_error.status_code
        error_message = str(http_error.detail)
        raise
    except Exception as e:
        # Record failed user doc types retrieval
        response_status = 500
        error_message = str(e)
        business_metrics.record_utility_operation("get_user_doc_types", "error")
        
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

@router.get("/faqs")
@track_business_operation("get", "faqs")
def get_faqs(request: Request, user_id: str = Query(..., description="User ID for authorization")):
    """
    Retrieve frequently asked questions tailored to the user's type and access level.
    
    This endpoint provides role-specific FAQ content to help users understand
    functionality and procedures relevant to their user type and permissions level.
    The FAQ system delivers contextual help information organized by display order
    to provide optimal user experience and reduce support requests.
    
    Args:
        request (Request): FastAPI request object for logging and monitoring
        user_id (str): User ID for authorization and user type determination.
                      Must exist in user_profile table as an active user.
    
    Returns:
        dict: Response containing:
            - faqs (List[dict]): Array of FAQ objects relevant to user's type, each containing:
                - faq_header (str): Question or topic title for the FAQ entry
                - faq_text (str): Detailed answer or explanation content
    
    Raises:
        HTTPException:
            - 404 Not Found: User not found or inactive in user_profile table
            - 500 Internal Server Error: Database connection or query execution errors
    
    User Type Filtering:
        - Automatically determines user's user_type from user_profile table
        - Returns only FAQ entries matching the user's specific user_type
        - Ensures users see relevant content appropriate to their access level
        - No manual user_type >= 100 validation (uses individual user's type)
    
    Database Operations:
        - First queries 'user_profile' table to determine user's type and validate existence
        - Then queries 'faq_list' table for FAQs matching the user's user_type
        - Results ordered by display_order for optimal presentation sequence
        - Read-only operations with automatic connection management
    
    Monitoring & Logging:
        - Business metrics tracking for FAQ retrieval operations:
          - "success": FAQs successfully retrieved for user type
          - "user_not_found": User validation failed
          - "error": Database or processing errors
        - Prometheus monitoring via @track_business_operation decorator
        - Comprehensive request logging with user ID tracking
        - User validation failure tracking for security monitoring
    
    Example Response:
        {
            "faqs": [
                {
                    "faq_header": "How do I create a new case?",
                    "faq_text": "To create a new case, navigate to the Cases section and click 'Add New Case'. Fill in the required patient and procedure information, then save."
                },
                {
                    "faq_header": "What documents can I upload?",
                    "faq_text": "You can upload medical licenses, board certifications, DEA registrations, and malpractice insurance documents in PDF format."
                },
                {
                    "faq_header": "How do I update my profile information?",
                    "faq_text": "Go to the Profile section in the main menu. You can update your contact information, address, and professional details there."
                }
            ]
        }
    
    Usage:
        GET /faqs?user_id=USER123
        
    Notes:
        - FAQ content is automatically filtered by user type for relevance
        - Results are ordered by display_order to provide logical information flow
        - Used for contextual help systems and user onboarding processes
        - No authorization level requirement (individual user validation only)
        - Content varies based on user's role and permission level in the system
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
                # Get user_type from user_profile
                cursor.execute(
                    "SELECT user_type FROM user_profile WHERE user_id = %s AND active = 1",
                    (user_id,)
                )
                user = cursor.fetchone()
                
                if not user:
                    # Record failed FAQs retrieval - user not found
                    business_metrics.record_utility_operation("get_faqs", "user_not_found")
                    response_status = 404
                    error_message = "User not found or inactive"
                    raise HTTPException(status_code=404, detail={"error": "User not found or inactive"})
                
                user_type = user['user_type']
                
                # Query FAQ list for the user's type, sorted by display_order
                cursor.execute(
                    "SELECT faq_header, faq_text FROM faq_list WHERE user_type = %s ORDER BY display_order",
                    (user_type,)
                )
                faqs = cursor.fetchall()

                # Record successful FAQs retrieval
                business_metrics.record_utility_operation("get_faqs", "success")
                
        finally:
            close_db_connection(conn)
            
        response_data = {
            "faqs": faqs,
            "user_type": user_type
        }
        return response_data
        
    except HTTPException as http_error:
        # Re-raise HTTP exceptions and capture error details
        response_status = http_error.status_code
        error_message = str(http_error.detail)
        raise
    except Exception as e:
        # Record failed FAQs retrieval
        response_status = 500
        error_message = str(e)
        business_metrics.record_utility_operation("get_faqs", "error")
        
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

@router.get("/pay_tiers")
@track_business_operation("get", "pay_tiers")
def get_pay_tiers(request: Request, user_id: str = Query(..., description="User ID for authorization")):
    """
    Retrieve all procedure code payment tier buckets for billing and reimbursement management.
    
    This endpoint provides access to the complete procedure code payment tier structure used
    throughout the application for medical billing calculations, reimbursement analysis, and
    financial reporting. The payment tiers organize procedure codes into buckets with associated
    payment amounts based on tier levels, code categories, and bucket classifications for
    systematic billing and revenue management.
    
    Args:
        request (Request): FastAPI request object for logging and monitoring
        user_id (str): User ID for authorization validation.
                      Must have user_type >= 100 for access to payment tier data.
    
    Returns:
        dict: Response containing:
            - pay_tiers (List[dict]): Array of payment tier bucket objects, each containing:
                - code_category (str): Medical procedure code category classification
                - code_bucket (str): Grouping bucket for related procedure codes
                - tier (int): Payment tier level determining reimbursement amount
                - pay_amount (decimal): Associated payment amount for this tier/bucket combination
    
    Raises:
        HTTPException:
            - 404 Not Found: User not found or inactive in user_profile table
            - 403 Forbidden: User has insufficient privileges (user_type < 100)
            - 500 Internal Server Error: Database connection or query execution errors
    
    Authorization:
        - Requires user_type >= 100 for access to payment tier management data
        - Uses validate_user_access() helper function for consistent authorization
        - Validates user exists and is active in user_profile table
    
    Database Operations:
        - Queries 'procedure_code_buckets' table for all payment tier configurations
        - Results ordered by tier, code_bucket, code_category for logical presentation
        - Returns complete payment structure for billing system integration
        - Read-only operation with automatic connection management
    
    Monitoring & Logging:
        - Business metrics tracking for payment tier retrieval operations
        - Prometheus monitoring via @track_business_operation decorator
        - Comprehensive request logging with user ID tracking
        - Authorization failure tracking for security monitoring
    
    Example Response:
        {
            "pay_tiers": [
                {
                    "code_category": "SURGERY",
                    "code_bucket": "BASIC_PROCEDURES",
                    "tier": 1,
                    "pay_amount": 250.00
                },
                {
                    "code_category": "SURGERY", 
                    "code_bucket": "COMPLEX_PROCEDURES",
                    "tier": 1,
                    "pay_amount": 500.00
                },
                {
                    "code_category": "CONSULTATION",
                    "code_bucket": "INITIAL_CONSULT",
                    "tier": 2,
                    "pay_amount": 150.00
                },
                {
                    "code_category": "SURGERY",
                    "code_bucket": "BASIC_PROCEDURES", 
                    "tier": 2,
                    "pay_amount": 300.00
                }
            ]
        }
    
    Usage:
        GET /pay_tiers?user_id=USER123
        
    Notes:
        - Payment tiers are organized hierarchically with tier levels determining base reimbursement
        - Code buckets group related procedures for standardized billing calculations
        - Code categories provide high-level classification of medical procedure types
        - Used for automated billing calculations and reimbursement processing
        - Essential for revenue management and financial reporting systems
        - Authorization required to prevent unauthorized access to sensitive payment information
        - Integrates with case payment calculations and provider reimbursement workflows
    """
    conn = None
    start_time = time.time()
    response_status = 200
    response_data = None
    error_message = None
    
    try:
        conn = get_db_connection()
        
        # Validate user access
        validate_user_access(user_id, conn)
        
        try:
            with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                cursor.execute(
                    "SELECT code_bucket, tier, pay_amount FROM procedure_code_buckets2 ORDER BY tier, pay_amount"
                )
                pay_tiers = cursor.fetchall()

                # Record successful pay tiers retrieval
                business_metrics.record_utility_operation("get_pay_tiers", "success")
                
        finally:
            close_db_connection(conn)
            
        response_data = {
            "pay_tiers": pay_tiers
        }
        return response_data
        
    except HTTPException as http_error:
        # Re-raise HTTP exceptions and capture error details
        response_status = http_error.status_code
        error_message = str(http_error.detail)
        raise
    except Exception as e:
        # Record failed pay tiers retrieval
        response_status = 500
        error_message = str(e)
        business_metrics.record_utility_operation("get_pay_tiers", "error")
        
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
@router.get("/tiers_summary")
@track_business_operation("get", "tiers_summary")
def get_tiers_summary(request: Request, user_id: str = Query(..., description="User ID for authorization")):
    """
    Retrieve procedure code payment tier summary organized by tier with amounts grouped by specialty.
    
    This endpoint provides a consolidated view of the payment tier structure by organizing
    procedure code payment amounts into tiers with specialty-grouped payment amounts. The
    summary aggregates payment data from the procedure_code_buckets table and formats
    it into a tier-based structure showing payment amounts across medical specialties
    in a standardized order for consistent reporting and billing reference.
    
    Args:
        request (Request): FastAPI request object for logging and monitoring
        user_id (str): User ID for authorization validation.
                      Must have user_type >= 20 for access to payment tier summary data.
    
    Returns:
        dict: Response containing:
            - buckets (str): Order of specialties for frontend display: "OB-Gyn/General/Other/Orthopedic/Plastic/Spine"
            - tiers_summary (List[dict]): Array of tier summary objects, each containing:
                - tier (str): Payment tier level identifier
                - amounts (str): Formatted payment amounts string in specialty order:
                  "(OB-Gyn/General/Other/Orthopedic/Plastic/Spine)"
                  Shows payment amount for each specialty, or "0" if not available
    
    Raises:
        HTTPException:
            - 404 Not Found: User not found or inactive in user_profile table
            - 403 Forbidden: User has insufficient privileges (user_type < 20)
            - 500 Internal Server Error: Database connection or query execution errors
    
    Authorization:
        - Requires user_type >= 20 for access to payment tier summary data
        - Uses validate_tiers_summary_access() helper function for consistent authorization
        - Validates user exists and is active in user_profile table
    
    Database Operations:
        - Queries 'procedure_code_buckets' table with grouped aggregation:
          SELECT tier, code_bucket, pay_amount FROM procedure_code_buckets 
          GROUP BY tier, code_bucket, pay_amount ORDER BY tier, pay_amount, code_bucket
        - Aggregates data by tier level and specialty bucket
        - Read-only operation with automatic connection management
        - Results processed for specialty-ordered formatting
    
    Data Processing:
        - Groups payment amounts by tier level across medical specialties
        - Organizes specialty amounts in fixed order: OB-Gyn, General, Other, Orthopedic, Plastic, Spine
        - Formats amounts as parenthetical string with forward slash separation
        - Handles missing specialty data by substituting "0" for unavailable amounts
        - Preserves tier ordering for consistent reporting structure
    
    Monitoring & Logging:
        - Business metrics tracking for tiers summary retrieval operations
        - Prometheus monitoring via @track_business_operation decorator
        - Comprehensive request logging with user ID tracking
        - Authorization failure tracking for security monitoring
    
    Example Response:
        {
            "buckets": "OB-Gyn/General/Other/Orthopedic/Plastic/Spine",
            "tiers_summary": [
                {
                    "tier": "1",
                    "amounts": "(250/400/550/550/1050/0)"
                },
                {
                    "tier": "2", 
                    "amounts": "(300/450/600/600/1150/800)"
                },
                {
                    "tier": "3",
                    "amounts": "(350/500/650/650/1250/900)"
                }
            ]
        }
    
    Usage:
        GET /tiers_summary?user_id=USER123
        
    Notes:
        - Payment amounts are organized by medical specialty in standardized order
        - Tier levels determine base reimbursement structure across specialties
        - Used for quick reference of payment structures across different procedure types
        - Authorization required to prevent unauthorized access to sensitive payment information
        - Integrates with billing systems and reimbursement calculation workflows
        - Specialty order follows standard medical practice categorization system
    """
    conn = None
    start_time = time.time()
    response_status = 200
    response_data = None
    error_message = None
    
    try:
        conn = get_db_connection()
        
        # Validate user access
        validate_tiers_summary_access(user_id, conn)
        
        try:
            with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                # Execute the exact query as specified
                cursor.execute(
                    "SELECT tier, code_bucket, pay_amount FROM procedure_code_buckets2 GROUP BY tier, code_bucket, pay_amount ORDER BY tier, pay_amount, code_bucket"
                )
                raw_data = cursor.fetchall()

                # Process the data to create tier summary
                # Define the specialty order as requested: (OB-Gyn/General/Other/Orthopedic/Plastic/Spine)
                specialty_order = ["OB-Gyn", "General", "Orthopedic", "Plastic", "Spine"]
                
                # Group data by tier
                tiers_data = {}
                for row in raw_data:
                    tier = str(row['tier'])
                    code_bucket = row['code_bucket']
                    pay_amount = int(row['pay_amount'])  # Convert to integer to remove decimal places
                    
                    if tier not in tiers_data:
                        tiers_data[tier] = {}
                    
                    tiers_data[tier][code_bucket] = pay_amount
                
                # Format the response
                tiers_summary = []
                for tier in sorted(tiers_data.keys(), key=int):  # Sort tiers numerically
                    amounts = []
                    for specialty in specialty_order:
                        amount = tiers_data[tier].get(specialty, 0)
                        amounts.append(str(amount))
                    
                    formatted_amounts = f"({'/'.join(amounts)})"
                    
                    tiers_summary.append({
                        "tier": tier,
                        "amounts": formatted_amounts
                    })

                # Record successful tiers summary retrieval
                business_metrics.record_utility_operation("get_tiers_summary", "success")
                
        finally:
            close_db_connection(conn)
            
        response_data = {
            "buckets": "OB-Gyn/General/Orthopedic/Plastic/Spine",
            "tiers_summary": tiers_summary
        }
        return response_data
        
    except HTTPException as http_error:
        # Re-raise HTTP exceptions and capture error details
        response_status = http_error.status_code
        error_message = str(http_error.detail)
        raise
    except Exception as e:
        # Record failed tiers summary retrieval
        response_status = 500
        error_message = str(e)
        business_metrics.record_utility_operation("get_tiers_summary", "error")
        
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
