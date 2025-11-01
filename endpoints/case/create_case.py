# Created: 2025-07-15 09:20:13
# Last Modified: 2025-11-01 02:47:34
# Author: Scott Cadreau

# endpoints/case/create_case.py
from fastapi import APIRouter, HTTPException, Request
from fastapi import Depends
import pymysql.cursors
from core.database import get_db_connection, close_db_connection, is_connection_valid
from core.models import CaseCreate
from utils.case_status import update_case_status
from utils.pay_amount_calculator import update_case_pay_amount_v2
from utils.procedure_code_auto_fix import auto_fix_procedure_codes, format_corrections_for_response
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

def check_duplicate_case(user_id: str, case_date: str, patient_first: str, patient_last: str, conn) -> dict:
    """
    Check if a case with the same user_id, date and patient name already exists.
    Returns dict with 'is_duplicate' boolean and 'existing_case_id' if found.
    
    Note: For encrypted cases, this function decrypts patient names before returning them.
    """
    with conn.cursor(pymysql.cursors.DictCursor) as cursor:
        cursor.execute("""
            SELECT case_id, patient_first, patient_last, case_date, user_id, phi_encrypted
            FROM cases 
            WHERE user_id = %s
            AND case_date = %s 
            AND LOWER(TRIM(patient_first)) = LOWER(TRIM(%s))
            AND LOWER(TRIM(patient_last)) = LOWER(TRIM(%s))
            AND active = 1
            LIMIT 1
        """, (user_id, case_date, patient_first, patient_last))
        
        result = cursor.fetchone()
        if result:
            # Decrypt patient names if needed (for duplicate check response)
            TEST_USER_ID = '54d8e448-0091-7031-86bb-d66da5e8f7e0'
            if result.get('phi_encrypted') == 1 and result['user_id'] == TEST_USER_ID:
                try:
                    from utils.phi_encryption import PHIEncryption, get_user_dek
                    
                    # Get user's DEK for decryption
                    dek = get_user_dek(result['user_id'], conn)
                    phi_crypto = PHIEncryption()
                    
                    # Decrypt patient names for the duplicate check response
                    for field in ['patient_first', 'patient_last']:
                        if field in result and result[field]:
                            field_value = str(result[field])
                            # Skip if too short to be encrypted
                            if len(field_value) >= 28:
                                try:
                                    result[field] = phi_crypto.decrypt_field(result[field], dek)
                                except Exception as field_error:
                                    logger.warning(f"[DECRYPT] Could not decrypt {field} for duplicate check, leaving as-is")
                                    pass
                except Exception as decrypt_error:
                    logger.error(f"[DECRYPT] Failed to decrypt duplicate case data: {str(decrypt_error)}")
                    # Continue with encrypted names rather than failing
            
            return {
                "is_duplicate": True,
                "existing_case_id": result["case_id"],
                "existing_case_date": result["case_date"],
                "existing_patient_first": result["patient_first"],
                "existing_patient_last": result["patient_last"],
                "existing_user_id": result["user_id"]
            }
        else:
            return {"is_duplicate": False}

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
    
    # Determine dupe_flag value based on force_duplicate parameter
    dupe_flag = 1 if case.force_duplicate else 0
    
    # TEST USER ENCRYPTION: Only encrypt for test user 54d8e448-0091-7031-86bb-d66da5e8f7e0
    # TODO: Remove this check once encryption is validated for all users
    TEST_USER_ID = '54d8e448-0091-7031-86bb-d66da5e8f7e0'
    use_encryption = (case.user_id == TEST_USER_ID)
    
    if use_encryption:
        logger.info(f"[ENCRYPTION TEST] Encrypting PHI for test user: {case.user_id}")
        from utils.phi_encryption import encrypt_patient_data
        
        # Prepare patient data for encryption (names and insurance only, not DOB)
        patient_data = {
            'patient_first': formatted_patient_first,
            'patient_last': formatted_patient_last,
            'ins_provider': case.patient.ins_provider
        }
        
        # Encrypt the data
        encrypt_patient_data(patient_data, case.user_id, conn)
        
        # Use encrypted values for names/insurance, unencrypted for DOB
        formatted_patient_first = patient_data['patient_first']
        formatted_patient_last = patient_data['patient_last']
        encrypted_ins_provider = patient_data['ins_provider']
        encrypted_patient_dob = case.patient_dob  # DOB stays unencrypted (DATE column)
        phi_encrypted_flag = 1
        
        logger.info(f"[ENCRYPTION TEST] PHI encrypted successfully for case: {case.case_id}")
    else:
        # Use unencrypted values for non-test users
        encrypted_patient_dob = case.patient_dob
        encrypted_ins_provider = case.patient.ins_provider
        phi_encrypted_flag = 0
    
    with conn.cursor(pymysql.cursors.DictCursor) as cursor:
        # Insert into cases table
        cursor.execute("""
            INSERT INTO cases (
                case_id, user_id, case_date, patient_first, patient_last, 
                ins_provider, surgeon_id, facility_id, demo_file, note_file, misc_file, dupe_flag, patient_dob, phi_encrypted
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            case.case_id, case.user_id, case.case_date, formatted_patient_first, 
            formatted_patient_last, encrypted_ins_provider, case.surgeon_id, 
            case.facility_id, case.demo_file, case.note_file, case.misc_file, dupe_flag, encrypted_patient_dob, phi_encrypted_flag
        ))

        # Auto-fix variables already initialized at function level
        
        # Insert procedure codes with descriptions using batch operation if any exist
        if case.procedure_codes:
            # Apply auto-fixes for common procedure code issues (function imported at top level)
            corrected_codes, corrections_made = auto_fix_procedure_codes(conn, case.procedure_codes, case.case_id)
            
            # Insert procedure codes with descriptions looked up from procedure_codes table
            for code in corrected_codes:
                cursor.execute("""
                    INSERT INTO case_procedure_codes (case_id, procedure_code, procedure_desc, asst_surg)
                    VALUES (%s, %s, (
                        SELECT COALESCE(pc.procedure_desc, '')
                        FROM procedure_codes pc 
                        WHERE pc.procedure_code = %s 
                        LIMIT 1
                    ), (
                        SELECT COALESCE(pc.asst_surg, 0)
                        FROM procedure_codes pc 
                        WHERE pc.procedure_code = %s 
                        LIMIT 1
                    ))
                """, (case.case_id, code, code, code))

        # Calculate and update pay amount if procedure codes exist
        pay_amount_result = update_case_pay_amount_v2(case.case_id, case.user_id, conn)
        if not pay_amount_result["success"]:
            logger.error(f"Pay amount calculation failed for case {case.case_id}: {pay_amount_result['message']}")
            # Don't fail the entire operation, but log the error
        
        # Check if Medicare is in insurance - if so, override case_status to 7
        if case.patient.ins_provider and "medicare" in case.patient.ins_provider.lower():
            logger.info(f"Medicare detected in insurance for case {case.case_id}, setting case_status to 7")
            cursor.execute("""
                UPDATE cases 
                SET case_status = 7
                WHERE case_id = %s
            """, (case.case_id,))
            status_update_result = {
                "success": True,
                "message": "Case status set to 7 (Medicare)",
                "new_status": 7,
                "previous_status": None
            }
        else:
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
    - Case validation and duplicate prevention (case_id and patient+date combinations)
    - Optional duplicate case forcing with dupe_flag tracking
    - Transactional database operations for data integrity
    - Automatic procedure code association
    - Pay amount calculation based on procedure codes
    - Case status updates when applicable
    - Automatic file validation for uploaded documents (PDF/JPEG)
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
            - force_duplicate (bool, optional): Allow creation of duplicate cases (same patient+date)
        request (Request): FastAPI request object for logging and monitoring
    
    Returns:
        dict: Response containing:
            - message (str): Success confirmation message
            - user_id (str): The user ID who created the case
            - case_id (str): The created case identifier
            - procedure_codes (List[str]): Associated procedure codes
            - status_update (dict): Results of automatic status update process
            - pay_amount_update (dict): Results of pay amount calculation
            - forced_duplicate (bool): Whether this case was created as a forced duplicate
            - dupe_flag (int): Database flag indicating duplicate status (1 if forced, 0 if not)
            - file_validation_errors (List[dict], optional): File validation errors if any files were invalid
    
    Raises:
        HTTPException: 
            - 409 Conflict: Case with the same case_id already exists
            - 409 Conflict: Duplicate case detected (same patient name and date) when force_duplicate=False
            - 500 Internal Server Error: Database or processing errors
    
    Database Operations:
        - Inserts record into 'cases' table with patient and case details
        - Batch inserts procedure codes into 'case_procedure_codes' table
        - Triggers automatic pay amount calculation via update_case_pay_amount_v2()
        - Triggers automatic case status update via update_case_status()
        - All operations wrapped in a database transaction for atomicity
        - Validates uploaded files (demo_file, note_file, misc_file) after successful commit:
            - Downloads files from S3 and validates format (PDF/JPEG only)
            - Removes invalid files from S3 and sets filename to NULL in database
            - Reports validation errors in response
    
    Monitoring & Logging:
        - Business metrics tracking for case creation operations
        - Prometheus monitoring via @track_business_operation decorator
        - Comprehensive request logging with execution time tracking
        - Error logging with full exception details
    
    Transaction Handling:
        - Explicit transaction begin/commit for data consistency
        - Automatic rollback on any operation failure
        - Connection validation and proper cleanup in finally block
    
    File Validation:
        - Triggered automatically when demo_file, note_file, or misc_file are provided
        - Downloads files from S3 and validates format using appropriate libraries
        - Supported formats: PDF (using pypdf), JPEG/JPG (using PIL/Pillow)
        - Unsupported formats (PNG, etc.) are passed through without validation
        - Invalid files are automatically deleted from S3 and filename set to NULL
        - Validation errors included in response but do not fail the entire operation
        - Typical validation time: ~120ms for 4MB files (includes S3 download)
    
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
            "procedure_codes": ["12345", "67890"],
            "demo_file": "surgical_demo.pdf",
            "force_duplicate": false
        }
    
    Example Response with File Validation Errors:
        {
            "message": "Case created successfully, but some files were invalid and removed",
            "user_id": "USER123",
            "case_id": "CASE-2024-001",
            "procedure_codes": ["12345", "67890"],
            "status_update": {"success": true, "message": "Status updated to In Progress"},
            "pay_amount_update": {"success": true, "new_amount": 1500.00},
            "forced_duplicate": false,
            "dupe_flag": 0,
            "file_validation_errors": [
                {
                    "field": "demo_file",
                    "filename": "corrupted_demo.pdf",
                    "error": "File corrupted_demo.pdf is not readable and has been removed. Please upload a new file."
                }
            ]
        }
    
    Note:
        - Case creation triggers automatic pay amount calculation if procedure codes are provided
        - Case status may be automatically updated based on business rules
        - All file paths (demo_file, note_file, misc_file) are optional
        - File validation is triggered automatically for any provided file paths
        - Invalid files are removed from S3 and their database references are set to NULL
        - File validation errors do not cause the entire creation operation to fail
        - Only PDF and JPEG/JPG files are validated; other formats pass through unchanged
        - Procedure codes list is optional but recommended for accurate pay calculations
        - Duplicate detection checks for same user_id, patient name (first+last) and case date
        - Set force_duplicate=true to allow legitimate duplicate cases (sets dupe_flag=1)
    """
    conn = None
    start_time = time.time()
    response_status = 200
    response_data = None
    error_message = None
    
    # Initialize auto-fix variables at function level
    corrected_codes = []
    corrections_made = []
    
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
        
        # Check for duplicate cases based on user_id, date and patient name
        formatted_patient_first = capitalize_name_field(case.patient.first)
        formatted_patient_last = capitalize_name_field(case.patient.last)
        duplicate_check = check_duplicate_case(case.user_id, case.case_date, formatted_patient_first, formatted_patient_last, conn)
        
        if duplicate_check["is_duplicate"] and not case.force_duplicate:
            response_status = 409
            error_message = "Duplicate case detected"
            business_metrics.record_case_operation("create", "duplicate_patient", case.case_id)
            raise HTTPException(
                status_code=409,
                detail={
                    "error": "Duplicate case detected",
                    "message": f"A case for patient {formatted_patient_first} {formatted_patient_last} on {case.case_date} already exists for this user",
                    "existing_case_id": duplicate_check["existing_case_id"],
                    "existing_case_date": str(duplicate_check["existing_case_date"]),
                    "existing_patient_first": duplicate_check["existing_patient_first"],
                    "existing_patient_last": duplicate_check["existing_patient_last"],
                    "existing_user_id": duplicate_check["existing_user_id"],
                    "suggestion": "Set 'force_duplicate: true' in your request if this is a legitimate duplicate case"
                }
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
        
        # INPUT VALIDATION -- Validate uploaded files after successful DB commit
        file_validation_errors = []
        file_fields_to_validate = []
        
        # Check which file fields have values
        if case.demo_file:
            file_fields_to_validate.append(('demo_file', case.demo_file))
        if case.note_file:
            file_fields_to_validate.append(('note_file', case.note_file))
        if case.misc_file:
            file_fields_to_validate.append(('misc_file', case.misc_file))
        
        if file_fields_to_validate:
            from utils.validate_case_file import validate_case_file
            
            for field_name, filename in file_fields_to_validate:
                logger.info(f"🔍 Validating {field_name}: {filename} for case {case.case_id}")
                validation_result = validate_case_file(case.user_id, filename)
                
                if not validation_result["valid"]:
                    # File validation failed - update database to remove filename
                    try:
                        # TRANSACTION -- Update case to remove invalid filename
                        with conn.cursor(pymysql.cursors.DictCursor) as validation_cursor:
                            conn.begin()
                            validation_cursor.execute(
                                f"UPDATE cases SET {field_name} = NULL WHERE case_id = %s",
                                (case.case_id,)
                            )
                            conn.commit()
                            logger.info(f"🗑️ Removed invalid filename {filename} from {field_name} for case {case.case_id}")
                            
                            # Add to validation errors for response
                            file_validation_errors.append({
                                "field": field_name,
                                "filename": filename,
                                "error": validation_result.get("user_error", f"File {filename} is not readable")
                            })
                            
                    except Exception as db_error:
                        logger.error(f"❌ Failed to update database after file validation failure: {str(db_error)}")
                        conn.rollback()
                        # Still add to errors even if DB update failed
                        file_validation_errors.append({
                            "field": field_name,
                            "filename": filename,
                            "error": f"File {filename} validation failed and could not be removed from database"
                        })
                else:
                    logger.info(f"✅ File validation successful for {field_name}: {filename}")
        
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
            "procedure_codes": corrected_codes if corrected_codes else (case.procedure_codes if case.procedure_codes else []),
            "status_update": status_update_result["status_update"],
            "pay_amount_update": status_update_result["pay_amount_update"],
            "forced_duplicate": case.force_duplicate,
            "dupe_flag": 1 if case.force_duplicate else 0
        }
        
        # Add file validation results if any files were validated
        if file_validation_errors:
            response_data["file_validation_errors"] = file_validation_errors
            # Update message to indicate some files had issues
            response_data["message"] = "Case created successfully, but some files were invalid and removed"
        
        # Add auto-fix information if corrections were made
        if case.procedure_codes and corrections_made:
            response_data["procedure_code_corrections"] = format_corrections_for_response(corrections_made)
            response_data["original_procedure_codes"] = case.procedure_codes
        
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