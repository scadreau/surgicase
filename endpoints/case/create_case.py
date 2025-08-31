# Created: 2025-07-15 09:20:13
# Last Modified: 2025-08-31 00:09:50
# Author: Scott Cadreau

# endpoints/case/create_case.py
from fastapi import APIRouter, HTTPException, Request
from fastapi import Depends
import pymysql.cursors
from core.database import get_db_connection, close_db_connection, is_connection_valid
from core.models import CaseCreate
from utils.case_status import update_case_status
from utils.pay_amount_calculator import update_case_pay_amount
from utils.monitoring import track_business_operation, business_metrics
from utils.text_formatting import capitalize_name_field
import logging
import time
import threading

logger = logging.getLogger(__name__)

router = APIRouter()

def get_db():
    conn = get_db_connection()
    try:
        yield conn
    finally:
        close_db_connection(conn)

def case_exists(case_id: str, conn) -> bool:
    """Check if a case already exists in the database"""
    with conn.cursor(pymysql.cursors.DictCursor) as cursor:
        cursor.execute("SELECT case_id FROM cases WHERE case_id = %s", (case_id,))
        return cursor.fetchone() is not None

def create_case_with_procedures(case: CaseCreate, conn) -> dict:
    """
    Handles the actual database operations for case creation.
    This function assumes it's running within a transaction.
    """
    logger.info(f"Creating case with ID: {case.case_id}")
    logger.info(f"Case data: {case}")
    
    # Format patient names for proper capitalization
    formatted_patient_first = capitalize_name_field(case.patient.first)
    formatted_patient_last = capitalize_name_field(case.patient.last)
    
    with conn.cursor(pymysql.cursors.DictCursor) as cursor:
        # Insert into cases table
        cursor.execute("""
            INSERT INTO cases (
                case_id, user_id, case_date, patient_first, patient_last, 
                ins_provider, surgeon_id, facility_id, demo_file, note_file, misc_file
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            case.case_id, case.user_id, case.case_date, formatted_patient_first, 
            formatted_patient_last, case.patient.ins_provider, case.surgeon_id, 
            case.facility_id, case.demo_file, case.note_file, case.misc_file
        ))

        # Insert procedure codes with descriptions using batch operation if any exist
        if case.procedure_codes:
            # Insert procedure codes with descriptions looked up from procedure_codes table
            for code in case.procedure_codes:
                cursor.execute("""
                    INSERT INTO case_procedure_codes (case_id, procedure_code, procedure_desc)
                    SELECT %s, %s, COALESCE(pc.procedure_desc, '')
                    FROM procedure_codes pc 
                    WHERE pc.procedure_code = %s 
                    LIMIT 1
                """, (case.case_id, code, code))

        # Calculate and update pay amount if procedure codes exist
        pay_amount_result = update_case_pay_amount(case.case_id, case.user_id, conn)
        if not pay_amount_result["success"]:
            logger.error(f"Pay amount calculation failed for case {case.case_id}: {pay_amount_result['message']}")
            # Don't fail the entire operation, but log the error
        
        # Update case status if conditions are met (within the same transaction)
        status_update_result = update_case_status(case.case_id, conn)
        
        return {
            "status_update": status_update_result,
            "pay_amount_update": pay_amount_result
        }



@router.post("/case")
@track_business_operation("create", "case")
def add_case(case: CaseCreate, request: Request):
    """
    Create a new surgical case with associated procedure codes, automatic processing, and intelligent cache management.
    
    This endpoint provides comprehensive case creation functionality including:
    - Case validation and duplicate prevention
    - Transactional database operations for data integrity
    - Automatic procedure code association
    - Pay amount calculation based on procedure codes
    - Case status updates when applicable
    - Intelligent cache invalidation and rewarming
    - Full monitoring and logging integration
    - Prometheus metrics tracking
    
    Args:
        case (CaseCreate): The case data model containing:
            - case_id (str): Unique identifier for the case
            - user_id (str): ID of the user creating the case
            - case_date (date): Date when the surgery/case occurred
            - patient (Patient): Patient information including:
                - first (str): Patient's first name
                - last (str): Patient's last name
                - ins_provider (str): Insurance provider information
            - surgeon_id (str): Identifier for the operating surgeon
            - facility_id (str): Identifier for the surgical facility
            - procedure_codes (List[str], optional): List of medical procedure codes
            - demo_file (str, optional): Path to demonstration file
            - note_file (str, optional): Path to notes file
            - misc_file (str, optional): Path to miscellaneous file
        request (Request): FastAPI request object for logging and monitoring
    
    Returns:
        dict: Response containing:
            - message (str): Success confirmation message
            - user_id (str): The user ID who created the case
            - case_id (str): The created case identifier
            - procedure_codes (List[str]): Associated procedure codes
            - status_update (dict): Results of automatic status update process
            - pay_amount_update (dict): Results of pay amount calculation
    
    Raises:
        HTTPException: 
            - 409 Conflict: Case with the same case_id already exists
            - 500 Internal Server Error: Database or processing errors
    
    Database Operations:
        - Inserts record into 'cases' table with patient and case details
        - Batch inserts procedure codes into 'case_procedure_codes' table
        - Triggers automatic pay amount calculation via update_case_pay_amount()
        - Triggers automatic case status update via update_case_status()
        - All operations wrapped in a database transaction for atomicity
    
    Monitoring & Logging:
        - Business metrics tracking for case creation operations
        - Prometheus monitoring via @track_business_operation decorator
        - Comprehensive request logging with execution time tracking
        - Error logging with full exception details
    
    Transaction Handling:
        - Explicit transaction begin/commit for data consistency
        - Automatic rollback on any operation failure
        - Connection validation and proper cleanup in finally block
    
    Cache Management:
        - Automatically clears global cases cache (get_cases_by_status) after successful creation
        - Spawns background thread to re-warm global cache with common filter combinations
        - Invalidates and re-warms user-specific case cache (filter_cases) for the case owner
        - Cache operations are non-blocking and won't fail the main operation if they encounter errors
        - Ensures both admin dashboard and user dashboard show the new case immediately
        - Comprehensive logging of all cache operations for monitoring and debugging
    
    Example:
        POST /case
        {
            "case_id": "CASE-2024-001",
            "user_id": "USER123",
            "case_date": "2024-01-15",
            "patient": {
                "first": "John",
                "last": "Doe", 
                "ins_provider": "Blue Cross"
            },
            "surgeon_id": "SURG456",
            "facility_id": "FAC789",
            "procedure_codes": ["12345", "67890"]
        }
    
    Note:
        - Case creation triggers automatic pay amount calculation if procedure codes are provided
        - Case status may be automatically updated based on business rules
        - All file paths (demo_file, note_file, misc_file) are optional
        - Procedure codes list is optional but recommended for accurate pay calculations
    """
    conn = None
    start_time = time.time()
    response_status = 200
    response_data = None
    error_message = None
    
    try:
        logger.info(f"Creating case with ID: {case.case_id}")
        logger.info(f"Case data: {case}")
        
        conn = get_db_connection()
        
        # Check if case already exists before starting transaction
        if case_exists(case.case_id, conn):
            response_status = 409
            error_message = "Case already exists"
            business_metrics.record_case_operation("create", "duplicate", case.case_id)
            raise HTTPException(
                status_code=409, 
                detail={"error": "Case already exists", "case_id": case.case_id}
            )
        
        # Start explicit transaction
        conn.begin()
        
        # Perform all database operations
        status_update_result = create_case_with_procedures(case, conn)
        
        # Record successful case creation before commit
        business_metrics.record_case_operation("create", "success", case.case_id)
        
        # Clear caches BEFORE commit to prevent race conditions
        logger.info(f"🔄 STARTING cache invalidation for case creation: {case.case_id}")
        try:
            # 1. Clear global cases cache (affects admin dashboard) - but don't re-warm yet
            from endpoints.backoffice.get_cases_by_status import clear_cases_cache
            clear_cases_cache()  # Clear all cached data
            logger.info(f"✅ CLEARED global cases cache before commit for case creation: {case.case_id}")
            
            # 2. Clear user cases cache - but don't re-warm yet
            from endpoints.case.filter_cases import clear_user_cases_cache
            clear_user_cases_cache(case.user_id)  # Clear all cache entries for this user
            logger.info(f"✅ CLEARED user cases cache for user: {case.user_id}")
            
        except Exception as e:
            # Don't fail the main operation if cache invalidation fails
            logger.error(f"❌ Failed to invalidate caches before commit for case creation {case.case_id}: {str(e)}", exc_info=True)
        
        # Commit all changes at once
        conn.commit()
        logger.info(f"✅ COMMITTED database changes for case creation: {case.case_id}")
        
        # Re-warm caches after successful commit
        try:
            # Re-warm global cases cache in background
            from endpoints.backoffice.get_cases_by_status import warm_cases_cache
            threading.Thread(
                target=warm_cases_cache,
                daemon=True,
                name="create_case_cache_rewarm_global"
            ).start()
            logger.info(f"🔄 Started background re-warming of global cases cache after case creation: {case.case_id}")
            
            # Re-warm user cache
            from endpoints.case.filter_cases import _rewarm_user_cases_cache_background
            threading.Thread(
                target=_rewarm_user_cases_cache_background,
                args=(case.user_id,),
                daemon=True,
                name=f"create_case_cache_rewarm_user_{case.user_id}"
            ).start()
            logger.info(f"🔄 Started background re-warming of user cases cache for user: {case.user_id}")
            
        except Exception as e:
            # Don't fail the main operation if cache re-warming fails
            logger.error(f"❌ Failed to re-warm caches after case creation {case.case_id}: {str(e)}", exc_info=True)
        
        response_status = 201
        response_data = {
            "message": "Case and procedure codes created successfully",
            "user_id": case.user_id,
            "case_id": case.case_id,
            "procedure_codes": case.procedure_codes,
            "status_update": status_update_result["status_update"],
            "pay_amount_update": status_update_result["pay_amount_update"]
        }
        
        return response_data

    except HTTPException as http_error:
        # Re-raise HTTP exceptions and capture error details
        error_message = str(http_error.detail)
        raise
        
    except Exception as e:
        # Record failed case creation
        response_status = 500
        error_message = str(e)
        business_metrics.record_case_operation("create", "error", case.case_id)
        if conn and is_connection_valid(conn):
            try:
                conn.rollback()
            except (pymysql.err.InterfaceError, pymysql.err.OperationalError) as rollback_error:
                logger.error(f"Rollback failed for case {case.case_id}: {rollback_error}", exc_info=True)
                
        logger.error(f"Error creating case {case.case_id}: {e}", exc_info=True)
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
            user_id=case.user_id,
            response_data=response_data,
            error_message=error_message
        )
        
        # Always close the connection
        if conn:
            close_db_connection(conn)