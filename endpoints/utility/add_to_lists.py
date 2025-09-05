# Created: 2025-08-12 17:16:24
# Last Modified: 2025-09-05 22:19:07
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
                conn.commit()
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
                conn.commit()
                
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
                conn.commit()

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
                conn.commit()

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
    Create a new payment tier configuration and update procedure codes with complex multi-step process.
    
    This endpoint performs a complex multi-step operation to add new payment tier configurations:
    1. Adds records to procedure_code_buckets2 table with tier, bucket, and pay_amount
    2. Updates procedure_codes_temp table with the new tier for all records
    3. Updates pay amounts in procedure_codes_temp by joining with procedure_code_buckets2
    4. Creates a backup table procedure_codes_backup<datetime>
    5. Inserts updated data from procedure_codes_temp into procedure_codes table
    
    Only users with administrative privileges (user_type >= 100) can perform this operation.
    
    Args:
        request (Request): FastAPI request object for logging and monitoring
        pay_tier_data (PayTierCreate): The payment tier creation model containing:
            - tier (int): Payment tier level determining reimbursement amount
            - bucket (str): Grouping bucket for related procedure codes (maps to code_bucket)
            - pay_amount (float): Associated payment amount for this tier/bucket combination
            - user_id (str): ID of the user creating the payment tier (for authorization)
    
    Returns:
        dict: Response containing:
            - message (str): Success confirmation message
            - tier (int): Created payment tier level
            - bucket (str): Created procedure code bucket
            - pay_amount (float): Associated payment amount
            - backup_table (str): Name of the created backup table
            - records_updated (int): Number of procedure code records updated
            - created_by (str): User ID who created the payment tier
    
    Raises:
        HTTPException:
            - 404 Not Found: Creating user not found or inactive in user_profile table
            - 403 Forbidden: Creating user has insufficient privileges (user_type < 100)
            - 409 Conflict: Payment tier with same bucket/tier combination already exists
            - 500 Internal Server Error: Database connection or operation errors
    
    Authorization:
        - Requires user_type >= 100 for access to payment tier management operations
        - Uses validate_user_access() helper function for consistent authorization
        - Validates creating user exists and is active in user_profile table
    
    Database Operations:
        - Multi-step transaction with rollback on any failure
        - Creates backup table before making changes
        - Updates multiple tables in coordinated fashion
        - Maintains data consistency throughout complex operation
    
    Business Logic:
        - Complex workflow for updating payment tier structures
        - Joins procedure codes with payment buckets for accurate billing
        - Creates timestamped backups for data recovery
        - Updates all related procedure codes with new tier information
    
    Example Request:
        POST /pay_tiers
        {
            "tier": 2,
            "bucket": "IMAGING_ADVANCED",
            "pay_amount": 750.00,
            "user_id": "ADMIN001"
        }
    
    Example Response (Success):
        {
            "message": "Payment tier created and procedure codes updated successfully",
            "tier": 2,
            "bucket": "IMAGING_ADVANCED", 
            "pay_amount": 750.00,
            "backup_table": "procedure_codes_backup20250905_223045",
            "records_updated": 1250,
            "created_by": "ADMIN001"
        }
    """
    import datetime
    
    conn = None
    start_time = time.time()
    response_status = 201
    response_data = None
    error_message = None
    backup_table_name = None
    records_updated = 0
    
    try:
        conn = get_db_connection()
        
        # Validate user access
        validate_user_access(pay_tier_data.user_id, conn)
        
        try:
            with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                # Step 1: Check if payment tier configuration already exists in procedure_code_buckets2
                cursor.execute(
                    "SELECT code_bucket, tier FROM procedure_code_buckets2 WHERE code_bucket = %s AND tier = %s",
                    (pay_tier_data.bucket, pay_tier_data.tier)
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
                            "bucket": pay_tier_data.bucket,
                            "tier": pay_tier_data.tier
                        }
                    )
                
                # Step 2: Insert new payment tier into procedure_code_buckets2
                cursor.execute(
                    "INSERT INTO procedure_code_buckets2 (code_bucket, tier, pay_amount) VALUES (%s, %s, %s)",
                    (pay_tier_data.bucket, pay_tier_data.tier, pay_tier_data.pay_amount)
                )
                
                # Step 3: Update procedure_codes_temp with new tier for all records
                cursor.execute(
                    "UPDATE procedure_codes_temp SET tier = %s WHERE TRUE",
                    (pay_tier_data.tier,)
                )
                
                # Step 4: Update pay amounts in procedure_codes_temp by joining with procedure_code_buckets2
                # Join on code_category (from procedure_codes_temp) = code_bucket (from procedure_code_buckets2) and tier = tier
                cursor.execute("""
                    UPDATE procedure_codes_temp pct 
                    JOIN procedure_code_buckets2 pcb2 ON pct.code_category = pcb2.code_bucket AND pct.tier = pcb2.tier 
                    SET pct.code_pay_amount = pcb2.pay_amount
                """)
                
                # Step 5: Create backup table with datetime stamp
                current_datetime = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                backup_table_name = f"procedure_codes_backup{current_datetime}"
                
                cursor.execute(f"""
                    CREATE TABLE {backup_table_name} AS 
                    SELECT * FROM procedure_codes
                """)
                
                # Step 6: Clear procedure_codes table and insert from procedure_codes_temp
                cursor.execute("DELETE FROM procedure_codes")
                
                cursor.execute("""
                    INSERT INTO procedure_codes (procedure_code, procedure_desc, code_category, code_status, code_pay_amount, tier)
                    SELECT procedure_code, procedure_desc, code_category, code_status, code_pay_amount, tier
                    FROM procedure_codes_temp
                """)
                
                # Get count of records updated
                records_updated = cursor.rowcount
                
                # Commit all changes
                conn.commit()

                # Record successful payment tier creation
                business_metrics.record_utility_operation("add_pay_tier", "success")
                
        finally:
            close_db_connection(conn)
            
        response_data = {
            "message": "Payment tier created and procedure codes updated successfully",
            "tier": pay_tier_data.tier,
            "bucket": pay_tier_data.bucket,
            "pay_amount": pay_tier_data.pay_amount,
            "backup_table": backup_table_name,
            "records_updated": records_updated,
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
