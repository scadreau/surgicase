# Created: 2025-08-12 17:16:24
# Last Modified: 2025-08-12 17:17:11
# Author: Scott Cadreau

# endpoints/utility/add_to_lists.py
from fastapi import APIRouter, HTTPException, Request
import pymysql.cursors
from core.database import get_db_connection, close_db_connection
from core.models import UserTypeCreate, CaseStatusCreate, UserDocTypeCreate, FaqCreate, PayTierCreate
from utils.monitoring import track_business_operation, business_metrics
import time

router = APIRouter()

def validate_user_access(user_id: str, conn) -> bool:
    """
    Validate that the user has user_type >= 100 to access list management endpoints.
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

@router.post("/user_types")
@track_business_operation("create", "user_types")
def add_user_type(request: Request, user_type_data: UserTypeCreate):
    """
    Create a new user type in the system for role-based access control and permission management.
    
    This endpoint enables creation of new user type classifications used throughout the application
    for role-based access control, permission management, and user categorization. User types define
    hierarchical access levels, maximum case status permissions, and system-wide authorization boundaries.
    Only users with administrative privileges (user_type >= 100) can create new user types.
    
    Args:
        request (Request): FastAPI request object for logging and monitoring
        user_type_data (UserTypeCreate): The user type creation model containing:
            - user_type (int): Numeric user type identifier/level (must be unique)
            - user_type_desc (str): Human-readable description of the user type role
            - user_max_case_status (int): Maximum case status this user type can access/modify
            - user_id (str): ID of the user creating the user type (for authorization)
    
    Returns:
        dict: Response containing:
            - message (str): Success confirmation message
            - user_type (int): The created user type identifier
            - user_type_desc (str): Description of the created user type
            - user_max_case_status (int): Maximum case status for this user type
            - created_by (str): User ID who created the user type
    
    Raises:
        HTTPException:
            - 404 Not Found: Creating user not found or inactive in user_profile table
            - 403 Forbidden: Creating user has insufficient privileges (user_type < 100)
            - 409 Conflict: User type with the same user_type number already exists
            - 500 Internal Server Error: Database connection or insertion errors
    
    Authorization:
        - Requires user_type >= 100 for access to user type management operations
        - Uses validate_user_access() helper function for consistent authorization
        - Validates creating user exists and is active in user_profile table
    
    Database Operations:
        - Checks for duplicate user_type values in 'user_type_list' table
        - Inserts new record into 'user_type_list' table with all provided data
        - Commits transaction immediately after successful insertion
        - Automatic rollback on any operation failure for data consistency
    
    Business Logic:
        - Enforces unique user_type constraint to prevent role conflicts
        - User type numbers determine hierarchical access levels in the system
        - user_max_case_status controls maximum case visibility and modification rights
        - Lower user_type numbers typically indicate higher privilege levels
        - New user types become immediately available for user assignment
    
    Monitoring & Logging:
        - Business metrics tracking for user type creation operations
        - Prometheus monitoring via @track_business_operation decorator
        - Comprehensive request logging with execution time tracking
        - Success/error/duplicate metrics via business_metrics.record_utility_operation()
        - Authorization failure tracking for security monitoring
    
    Transaction Handling:
        - Explicit transaction control for data consistency
        - Duplicate check performed before insertion to prevent conflicts
        - Automatic rollback on any operation failure
        - Proper database connection cleanup in finally block
    
    Example Request:
        POST /user_types
        {
            "user_type": 150,
            "user_type_desc": "Senior Technician",
            "user_max_case_status": 6,
            "user_id": "ADMIN001"
        }
    
    Example Response (Success):
        {
            "message": "User type created successfully",
            "user_type": 150,
            "user_type_desc": "Senior Technician",
            "user_max_case_status": 6,
            "created_by": "ADMIN001"
        }
    
    Example Response (Duplicate):
        {
            "error": "User type already exists",
            "user_type": 150
        }
    
    Usage:
        POST /user_types
        
    Notes:
        - User type creation affects system-wide role-based access control
        - New user types should be carefully planned to maintain security hierarchy
        - user_max_case_status determines case workflow visibility for assigned users
        - Consider existing user type numbering conventions when creating new types
        - Authorization required to prevent unauthorized creation of privileged roles
        - Changes take effect immediately for role assignment and access control
    """
    conn = None
    start_time = time.time()
    response_status = 201
    response_data = None
    error_message = None
    
    try:
        conn = get_db_connection()
        
        # Validate user access
        validate_user_access(user_type_data.user_id, conn)
        
        try:
            with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                # Check if user type already exists
                cursor.execute(
                    "SELECT user_type FROM user_type_list WHERE user_type = %s",
                    (user_type_data.user_type,)
                )
                existing_user_type = cursor.fetchone()
                
                if existing_user_type:
                    # Record duplicate user type creation attempt
                    business_metrics.record_utility_operation("add_user_type", "duplicate")
                    response_status = 409
                    error_message = "User type already exists"
                    raise HTTPException(
                        status_code=409, 
                        detail={"error": "User type already exists", "user_type": user_type_data.user_type}
                    )
                
                # Insert new user type
                cursor.execute(
                    "INSERT INTO user_type_list (user_type, user_type_desc, user_max_case_status) VALUES (%s, %s, %s)",
                    (user_type_data.user_type, user_type_data.user_type_desc, user_type_data.user_max_case_status)
                )
                
                # Record successful user type creation
                business_metrics.record_utility_operation("add_user_type", "success")
                
        finally:
            close_db_connection(conn)
            
        response_data = {
            "message": "User type created successfully",
            "user_type": user_type_data.user_type,
            "user_type_desc": user_type_data.user_type_desc,
            "user_max_case_status": user_type_data.user_max_case_status,
            "created_by": user_type_data.user_id
        }
        return response_data
        
    except HTTPException as http_error:
        # Re-raise HTTP exceptions and capture error details
        response_status = http_error.status_code
        error_message = str(http_error.detail)
        raise
    except Exception as e:
        # Record failed user type creation
        response_status = 500
        error_message = str(e)
        business_metrics.record_utility_operation("add_user_type", "error")
        
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
            user_id=user_type_data.user_id,
            response_data=response_data,
            error_message=error_message
        )

@router.post("/case_statuses")
@track_business_operation("create", "case_statuses")
def add_case_status(request: Request, case_status_data: CaseStatusCreate):
    """
    Create a new case status in the system for case lifecycle management and workflow control.
    
    This endpoint enables creation of new case status levels used throughout the application
    for case lifecycle management, workflow automation, and access control. Case statuses define
    the progression of surgical cases from initial creation through completion and payment processing.
    Only users with administrative privileges (user_type >= 100) can create new case statuses.
    
    Args:
        request (Request): FastAPI request object for logging and monitoring
        case_status_data (CaseStatusCreate): The case status creation model containing:
            - case_status (int): Numeric case status identifier/level (must be unique)
            - case_status_desc (str): Human-readable description of the case status
            - user_id (str): ID of the user creating the case status (for authorization)
    
    Returns:
        dict: Response containing:
            - message (str): Success confirmation message
            - case_status (int): The created case status identifier
            - case_status_desc (str): Description of the created case status
            - created_by (str): User ID who created the case status
    
    Raises:
        HTTPException:
            - 404 Not Found: Creating user not found or inactive in user_profile table
            - 403 Forbidden: Creating user has insufficient privileges (user_type < 100)
            - 409 Conflict: Case status with the same case_status number already exists
            - 500 Internal Server Error: Database connection or insertion errors
    
    Authorization:
        - Requires user_type >= 100 for access to case status management operations
        - Uses validate_user_access() helper function for consistent authorization
        - Validates creating user exists and is active in user_profile table
    
    Database Operations:
        - Checks for duplicate case_status values in 'case_status_list' table
        - Inserts new record into 'case_status_list' table with provided data
        - Commits transaction immediately after successful insertion
        - Automatic rollback on any operation failure for data consistency
    
    Business Logic:
        - Enforces unique case_status constraint to prevent workflow conflicts
        - Case status numbers determine progression order in case lifecycle
        - New case statuses become immediately available for case assignment
        - Status levels integrate with user permissions and access control
        - Higher status numbers typically indicate later stages in case workflow
    
    Monitoring & Logging:
        - Business metrics tracking for case status creation operations
        - Prometheus monitoring via @track_business_operation decorator
        - Comprehensive request logging with execution time tracking
        - Success/error/duplicate metrics via business_metrics.record_utility_operation()
        - Authorization failure tracking for security monitoring
    
    Transaction Handling:
        - Explicit transaction control for data consistency
        - Duplicate check performed before insertion to prevent conflicts
        - Automatic rollback on any operation failure
        - Proper database connection cleanup in finally block
    
    Example Request:
        POST /case_statuses
        {
            "case_status": 6,
            "case_status_desc": "Payment Processing",
            "user_id": "ADMIN001"
        }
    
    Example Response (Success):
        {
            "message": "Case status created successfully",
            "case_status": 6,
            "case_status_desc": "Payment Processing",
            "created_by": "ADMIN001"
        }
    
    Example Response (Duplicate):
        {
            "error": "Case status already exists",
            "case_status": 6
        }
    
    Usage:
        POST /case_statuses
        
    Notes:
        - Case status creation affects case workflow management throughout the system
        - New case statuses should be carefully planned to maintain workflow integrity
        - Status levels integrate with user_max_case_status for role-based access control
        - Consider existing case status numbering conventions when creating new statuses
        - Authorization required to prevent unauthorized modification of case workflows
        - Changes take effect immediately for case status transitions and access control
    """
    conn = None
    start_time = time.time()
    response_status = 201
    response_data = None
    error_message = None
    
    try:
        conn = get_db_connection()
        
        # Validate user access
        validate_user_access(case_status_data.user_id, conn)
        
        try:
            with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                # Check if case status already exists
                cursor.execute(
                    "SELECT case_status FROM case_status_list WHERE case_status = %s",
                    (case_status_data.case_status,)
                )
                existing_case_status = cursor.fetchone()
                
                if existing_case_status:
                    # Record duplicate case status creation attempt
                    business_metrics.record_utility_operation("add_case_status", "duplicate")
                    response_status = 409
                    error_message = "Case status already exists"
                    raise HTTPException(
                        status_code=409, 
                        detail={"error": "Case status already exists", "case_status": case_status_data.case_status}
                    )
                
                # Insert new case status
                cursor.execute(
                    "INSERT INTO case_status_list (case_status, case_status_desc) VALUES (%s, %s)",
                    (case_status_data.case_status, case_status_data.case_status_desc)
                )
                
                # Record successful case status creation
                business_metrics.record_utility_operation("add_case_status", "success")
                
        finally:
            close_db_connection(conn)
            
        response_data = {
            "message": "Case status created successfully",
            "case_status": case_status_data.case_status,
            "case_status_desc": case_status_data.case_status_desc,
            "created_by": case_status_data.user_id
        }
        return response_data
        
    except HTTPException as http_error:
        # Re-raise HTTP exceptions and capture error details
        response_status = http_error.status_code
        error_message = str(http_error.detail)
        raise
    except Exception as e:
        # Record failed case status creation
        response_status = 500
        error_message = str(e)
        business_metrics.record_utility_operation("add_case_status", "error")
        
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
            user_id=case_status_data.user_id,
            response_data=response_data,
            error_message=error_message
        )

@router.post("/user_doc_types")
@track_business_operation("create", "user_doc_types")
def add_user_doc_type(request: Request, user_doc_type_data: UserDocTypeCreate):
    """
    Create a new user document type for document management and categorization systems.
    
    This endpoint enables creation of new document type categories used for organizing
    and classifying user-uploaded documents such as licenses, certifications, insurance
    documents, and other professional credentials. Document types include both display
    name and file naming prefix for systematic document organization and retrieval.
    Only users with administrative privileges (user_type >= 100) can create new document types.
    
    Args:
        request (Request): FastAPI request object for logging and monitoring
        user_doc_type_data (UserDocTypeCreate): The document type creation model containing:
            - doc_type (str): Human-readable document type category name
            - doc_prefix (str): File naming prefix for systematic document organization
            - user_id (str): ID of the user creating the document type (for authorization)
    
    Returns:
        dict: Response containing:
            - message (str): Success confirmation message
            - doc_type (str): The created document type name
            - doc_prefix (str): File naming prefix for the document type
            - created_by (str): User ID who created the document type
    
    Raises:
        HTTPException:
            - 404 Not Found: Creating user not found or inactive in user_profile table
            - 403 Forbidden: Creating user has insufficient privileges (user_type < 100)
            - 409 Conflict: Document type with the same doc_type name already exists
            - 500 Internal Server Error: Database connection or insertion errors
    
    Authorization:
        - Requires user_type >= 100 for access to document type management operations
        - Uses validate_user_access() helper function for consistent authorization
        - Validates creating user exists and is active in user_profile table
    
    Database Operations:
        - Checks for duplicate doc_type values in 'user_doc_type_list' table
        - Inserts new record into 'user_doc_type_list' table with provided data
        - Commits transaction immediately after successful insertion
        - Automatic rollback on any operation failure for data consistency
    
    Business Logic:
        - Enforces unique doc_type constraint to prevent categorization conflicts
        - doc_prefix used for systematic file naming and organization in document storage
        - New document types become immediately available for document upload interfaces
        - Document types integrate with user document upload and management workflows
        - Prefixes should be short, descriptive codes for file organization
    
    Monitoring & Logging:
        - Business metrics tracking for document type creation operations
        - Prometheus monitoring via @track_business_operation decorator
        - Comprehensive request logging with execution time tracking
        - Success/error/duplicate metrics via business_metrics.record_utility_operation()
        - Authorization failure tracking for security monitoring
    
    Transaction Handling:
        - Explicit transaction control for data consistency
        - Duplicate check performed before insertion to prevent conflicts
        - Automatic rollback on any operation failure
        - Proper database connection cleanup in finally block
    
    Example Request:
        POST /user_doc_types
        {
            "doc_type": "Continuing Education Certificate",
            "doc_prefix": "CEC",
            "user_id": "ADMIN001"
        }
    
    Example Response (Success):
        {
            "message": "User document type created successfully",
            "doc_type": "Continuing Education Certificate",
            "doc_prefix": "CEC",
            "created_by": "ADMIN001"
        }
    
    Example Response (Duplicate):
        {
            "error": "User document type already exists",
            "doc_type": "Continuing Education Certificate"
        }
    
    Usage:
        POST /user_doc_types
        
    Notes:
        - Document type creation affects document categorization throughout the system
        - New document types should follow established naming and prefix conventions
        - doc_prefix should be unique and meaningful for file organization systems
        - Consider existing document type categories when creating new types
        - Authorization required to prevent unauthorized modification of document management
        - Changes take effect immediately for document upload and categorization workflows
    """
    conn = None
    start_time = time.time()
    response_status = 201
    response_data = None
    error_message = None
    
    try:
        conn = get_db_connection()
        
        # Validate user access
        validate_user_access(user_doc_type_data.user_id, conn)
        
        try:
            with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                # Check if user doc type already exists
                cursor.execute(
                    "SELECT doc_type FROM user_doc_type_list WHERE doc_type = %s",
                    (user_doc_type_data.doc_type,)
                )
                existing_doc_type = cursor.fetchone()
                
                if existing_doc_type:
                    # Record duplicate user doc type creation attempt
                    business_metrics.record_utility_operation("add_user_doc_type", "duplicate")
                    response_status = 409
                    error_message = "User document type already exists"
                    raise HTTPException(
                        status_code=409, 
                        detail={"error": "User document type already exists", "doc_type": user_doc_type_data.doc_type}
                    )
                
                # Insert new user doc type
                cursor.execute(
                    "INSERT INTO user_doc_type_list (doc_type, doc_prefix) VALUES (%s, %s)",
                    (user_doc_type_data.doc_type, user_doc_type_data.doc_prefix)
                )
                
                # Record successful user doc type creation
                business_metrics.record_utility_operation("add_user_doc_type", "success")
                
        finally:
            close_db_connection(conn)
            
        response_data = {
            "message": "User document type created successfully",
            "doc_type": user_doc_type_data.doc_type,
            "doc_prefix": user_doc_type_data.doc_prefix,
            "created_by": user_doc_type_data.user_id
        }
        return response_data
        
    except HTTPException as http_error:
        # Re-raise HTTP exceptions and capture error details
        response_status = http_error.status_code
        error_message = str(http_error.detail)
        raise
    except Exception as e:
        # Record failed user doc type creation
        response_status = 500
        error_message = str(e)
        business_metrics.record_utility_operation("add_user_doc_type", "error")
        
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
            user_id=user_doc_type_data.user_id,
            response_data=response_data,
            error_message=error_message
        )

@router.post("/faqs")
@track_business_operation("create", "faqs")
def add_faq(request: Request, faq_data: FaqCreate):
    """
    Create a new FAQ entry for role-specific user help and support documentation.
    
    This endpoint enables creation of new FAQ entries tailored to specific user types
    to provide contextual help information and reduce support requests. FAQs are organized
    by user type and display order to deliver optimal user experience with relevant
    information for each role and permission level in the system.
    Only users with administrative privileges (user_type >= 100) can create new FAQs.
    
    Args:
        request (Request): FastAPI request object for logging and monitoring
        faq_data (FaqCreate): The FAQ creation model containing:
            - user_type (int): Target user type for this FAQ entry
            - faq_header (str): Question or topic title for the FAQ entry
            - faq_text (str): Detailed answer or explanation content
            - display_order (int): Order for presenting FAQs (lower numbers display first)
            - user_id (str): ID of the user creating the FAQ (for authorization)
    
    Returns:
        dict: Response containing:
            - message (str): Success confirmation message
            - user_type (int): Target user type for the FAQ
            - faq_header (str): Question/title of the created FAQ
            - faq_text (str): Answer content of the created FAQ
            - display_order (int): Display order of the FAQ entry
            - created_by (str): User ID who created the FAQ
    
    Raises:
        HTTPException:
            - 404 Not Found: Creating user not found or inactive in user_profile table
            - 403 Forbidden: Creating user has insufficient privileges (user_type < 100)
            - 500 Internal Server Error: Database connection or insertion errors
    
    Authorization:
        - Requires user_type >= 100 for access to FAQ management operations
        - Uses validate_user_access() helper function for consistent authorization
        - Validates creating user exists and is active in user_profile table
    
    Database Operations:
        - Inserts new record into 'faq_list' table with all provided data
        - No duplicate checking (multiple FAQs with same content allowed)
        - Commits transaction immediately after successful insertion
        - Automatic rollback on any operation failure for data consistency
    
    Business Logic:
        - FAQs are filtered by user_type when displayed to users
        - display_order determines presentation sequence for optimal information flow
        - Lower display_order numbers appear first in FAQ lists
        - Multiple FAQs can target the same user_type with different display orders
        - Content can include detailed explanations with formatting guidance
    
    Monitoring & Logging:
        - Business metrics tracking for FAQ creation operations
        - Prometheus monitoring via @track_business_operation decorator
        - Comprehensive request logging with execution time tracking
        - Success/error metrics via business_metrics.record_utility_operation()
        - Authorization failure tracking for security monitoring
    
    Transaction Handling:
        - Explicit transaction control for data consistency
        - Direct insertion without duplicate checking (FAQs can be similar)
        - Automatic rollback on any operation failure
        - Proper database connection cleanup in finally block
    
    Example Request:
        POST /faqs
        {
            "user_type": 200,
            "faq_header": "How do I bulk update case statuses?",
            "faq_text": "Advanced users can bulk update case statuses by selecting multiple cases in the case management interface and using the 'Bulk Update Status' button. Choose the new status and confirm the changes.",
            "display_order": 5,
            "user_id": "ADMIN001"
        }
    
    Example Response (Success):
        {
            "message": "FAQ created successfully",
            "user_type": 200,
            "faq_header": "How do I bulk update case statuses?",
            "faq_text": "Advanced users can bulk update case statuses by selecting multiple cases in the case management interface and using the 'Bulk Update Status' button. Choose the new status and confirm the changes.",
            "display_order": 5,
            "created_by": "ADMIN001"
        }
    
    Usage:
        POST /faqs
        
    Notes:
        - FAQ creation provides immediate help content for specified user types
        - display_order should be planned to create logical information flow
        - FAQ content should be clear, concise, and role-appropriate
        - Consider existing FAQ topics when creating new entries to avoid duplication
        - Authorization required to prevent unauthorized modification of help content
        - Changes take effect immediately for contextual help systems and user onboarding
    """
    conn = None
    start_time = time.time()
    response_status = 201
    response_data = None
    error_message = None
    
    try:
        conn = get_db_connection()
        
        # Validate user access
        validate_user_access(faq_data.user_id, conn)
        
        try:
            with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                # Insert new FAQ (no duplicate checking for FAQs)
                cursor.execute(
                    "INSERT INTO faq_list (user_type, faq_header, faq_text, display_order) VALUES (%s, %s, %s, %s)",
                    (faq_data.user_type, faq_data.faq_header, faq_data.faq_text, faq_data.display_order)
                )
                
                # Record successful FAQ creation
                business_metrics.record_utility_operation("add_faq", "success")
                
        finally:
            close_db_connection(conn)
            
        response_data = {
            "message": "FAQ created successfully",
            "user_type": faq_data.user_type,
            "faq_header": faq_data.faq_header,
            "faq_text": faq_data.faq_text,
            "display_order": faq_data.display_order,
            "created_by": faq_data.user_id
        }
        return response_data
        
    except HTTPException as http_error:
        # Re-raise HTTP exceptions and capture error details
        response_status = http_error.status_code
        error_message = str(http_error.detail)
        raise
    except Exception as e:
        # Record failed FAQ creation
        response_status = 500
        error_message = str(e)
        business_metrics.record_utility_operation("add_faq", "error")
        
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
            user_id=faq_data.user_id,
            response_data=response_data,
            error_message=error_message
        )

@router.post("/pay_tiers")
@track_business_operation("create", "pay_tiers")
def add_pay_tier(request: Request, pay_tier_data: PayTierCreate):
    """
    Create a new payment tier configuration for medical billing and reimbursement management.
    
    This endpoint enables creation of new procedure code payment tier buckets used throughout
    the application for medical billing calculations, reimbursement analysis, and financial reporting.
    Payment tiers organize procedure codes into buckets with associated payment amounts based on
    tier levels, code categories, and bucket classifications for systematic billing and revenue management.
    Only users with administrative privileges (user_type >= 100) can create new payment tiers.
    
    Args:
        request (Request): FastAPI request object for logging and monitoring
        pay_tier_data (PayTierCreate): The payment tier creation model containing:
            - code_category (str): Medical procedure code category classification
            - code_bucket (str): Grouping bucket for related procedure codes
            - tier (int): Payment tier level determining reimbursement amount
            - pay_amount (float): Associated payment amount for this tier/bucket combination
            - user_id (str): ID of the user creating the payment tier (for authorization)
    
    Returns:
        dict: Response containing:
            - message (str): Success confirmation message
            - code_category (str): Created procedure code category
            - code_bucket (str): Created procedure code bucket
            - tier (int): Created payment tier level
            - pay_amount (float): Associated payment amount
            - created_by (str): User ID who created the payment tier
    
    Raises:
        HTTPException:
            - 404 Not Found: Creating user not found or inactive in user_profile table
            - 403 Forbidden: Creating user has insufficient privileges (user_type < 100)
            - 409 Conflict: Payment tier with same category/bucket/tier combination already exists
            - 500 Internal Server Error: Database connection or insertion errors
    
    Authorization:
        - Requires user_type >= 100 for access to payment tier management operations
        - Uses validate_user_access() helper function for consistent authorization
        - Validates creating user exists and is active in user_profile table
    
    Database Operations:
        - Checks for duplicate combinations of code_category, code_bucket, and tier
        - Inserts new record into 'procedure_code_buckets' table with provided data
        - Commits transaction immediately after successful insertion
        - Automatic rollback on any operation failure for data consistency
    
    Business Logic:
        - Enforces unique combination constraint (category + bucket + tier) to prevent conflicts
        - Payment tiers are organized hierarchically with tier levels determining base reimbursement
        - Code buckets group related procedures for standardized billing calculations
        - Code categories provide high-level classification of medical procedure types
        - New payment tiers become immediately available for billing calculations
    
    Monitoring & Logging:
        - Business metrics tracking for payment tier creation operations
        - Prometheus monitoring via @track_business_operation decorator
        - Comprehensive request logging with execution time tracking
        - Success/error/duplicate metrics via business_metrics.record_utility_operation()
        - Authorization failure tracking for security monitoring
    
    Transaction Handling:
        - Explicit transaction control for data consistency
        - Duplicate check performed before insertion to prevent billing conflicts
        - Automatic rollback on any operation failure
        - Proper database connection cleanup in finally block
    
    Example Request:
        POST /pay_tiers
        {
            "code_category": "DIAGNOSTIC",
            "code_bucket": "IMAGING_ADVANCED",
            "tier": 2,
            "pay_amount": 750.00,
            "user_id": "ADMIN001"
        }
    
    Example Response (Success):
        {
            "message": "Payment tier created successfully",
            "code_category": "DIAGNOSTIC",
            "code_bucket": "IMAGING_ADVANCED",
            "tier": 2,
            "pay_amount": 750.00,
            "created_by": "ADMIN001"
        }
    
    Example Response (Duplicate):
        {
            "error": "Payment tier configuration already exists",
            "code_category": "DIAGNOSTIC",
            "code_bucket": "IMAGING_ADVANCED",
            "tier": 2
        }
    
    Usage:
        POST /pay_tiers
        
    Notes:
        - Payment tier creation affects billing calculations throughout the system
        - New payment tiers should follow established category and bucket naming conventions
        - Tier levels should align with existing payment structure hierarchy
        - Consider existing payment configurations when creating new tiers
        - Authorization required to prevent unauthorized modification of billing systems
        - Changes take effect immediately for case payment calculations and provider reimbursements
    """
    conn = None
    start_time = time.time()
    response_status = 201
    response_data = None
    error_message = None
    
    try:
        conn = get_db_connection()
        
        # Validate user access
        validate_user_access(pay_tier_data.user_id, conn)
        
        try:
            with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                # Check if payment tier configuration already exists
                cursor.execute(
                    "SELECT code_category, code_bucket, tier FROM procedure_code_buckets WHERE code_category = %s AND code_bucket = %s AND tier = %s",
                    (pay_tier_data.code_category, pay_tier_data.code_bucket, pay_tier_data.tier)
                )
                existing_pay_tier = cursor.fetchone()
                
                if existing_pay_tier:
                    # Record duplicate payment tier creation attempt
                    business_metrics.record_utility_operation("add_pay_tier", "duplicate")
                    response_status = 409
                    error_message = "Payment tier configuration already exists"
                    raise HTTPException(
                        status_code=409, 
                        detail={
                            "error": "Payment tier configuration already exists", 
                            "code_category": pay_tier_data.code_category,
                            "code_bucket": pay_tier_data.code_bucket,
                            "tier": pay_tier_data.tier
                        }
                    )
                
                # Insert new payment tier
                cursor.execute(
                    "INSERT INTO procedure_code_buckets (code_category, code_bucket, tier, pay_amount) VALUES (%s, %s, %s, %s)",
                    (pay_tier_data.code_category, pay_tier_data.code_bucket, pay_tier_data.tier, pay_tier_data.pay_amount)
                )
                
                # Record successful payment tier creation
                business_metrics.record_utility_operation("add_pay_tier", "success")
                
        finally:
            close_db_connection(conn)
            
        response_data = {
            "message": "Payment tier created successfully",
            "code_category": pay_tier_data.code_category,
            "code_bucket": pay_tier_data.code_bucket,
            "tier": pay_tier_data.tier,
            "pay_amount": pay_tier_data.pay_amount,
            "created_by": pay_tier_data.user_id
        }
        return response_data
        
    except HTTPException as http_error:
        # Re-raise HTTP exceptions and capture error details
        response_status = http_error.status_code
        error_message = str(http_error.detail)
        raise
    except Exception as e:
        # Record failed payment tier creation
        response_status = 500
        error_message = str(e)
        business_metrics.record_utility_operation("add_pay_tier", "error")
        
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
            user_id=pay_tier_data.user_id,
            response_data=response_data,
            error_message=error_message
        )
