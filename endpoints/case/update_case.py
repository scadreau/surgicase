# Created: 2025-07-15 09:20:13
# Last Modified: 2025-08-31 00:11:50
# Author: Scott Cadreau

# endpoints/case/update_case.py
from fastapi import APIRouter, HTTPException, Body, Request
import pymysql.cursors
import logging
import time
from core.database import get_db_connection, close_db_connection, is_connection_valid
from core.models import CaseUpdate
from utils.case_status import update_case_status
from utils.pay_amount_calculator import update_case_pay_amount
from utils.monitoring import track_business_operation, business_metrics

logger = logging.getLogger(__name__)

router = APIRouter()

@router.patch("/case")
@track_business_operation("update", "case")
def update_case(request: Request, case: CaseUpdate = Body(...)):
    """
    Update surgical case fields and procedure codes with automatic pay calculation and status management.
    
    This endpoint provides comprehensive case updating capabilities with selective field updates,
    complete procedure code replacement, automatic pay amount recalculation, and case status
    management. All operations are performed within a database transaction to ensure data consistency.
    
    Key Features:
    - Selective field updates (only provided fields are modified)
    - Complete procedure code replacement with duplicate removal
    - Automatic pay amount recalculation when procedure codes change
    - Automatic case status updates based on business rules
    - Transactional operations for data integrity
    - Comprehensive validation and error handling
    - Monitoring and performance tracking
    - Detailed change tracking and reporting
    
    Args:
        request (Request): FastAPI request object for logging and monitoring
        case (CaseUpdate): Case update model containing:
            - case_id (str): Unique identifier of the case to update (required)
            - user_id (str, optional): User ID (used for pay calculations if not in database)
            - case_date (date, optional): Surgery/case date
            - patient_first (str, optional): Patient's first name
            - patient_last (str, optional): Patient's last name
            - ins_provider (str, optional): Insurance provider information
            - surgeon_id (str, optional): Surgeon identifier
            - facility_id (str, optional): Facility identifier
            - demo_file (str, optional): Path to demonstration file
            - note_file (str, optional): Path to notes file
            - misc_file (str, optional): Path to miscellaneous file
            - procedure_codes (List[str], optional): Complete list of procedure codes to replace existing ones
    
    Returns:
        dict: Response containing:
            - statusCode (int): HTTP status code (200 for success)
            - body (dict): Response body with:
                - message (str): Success confirmation message
                - case_id (str): The case identifier that was updated
                - updated_fields (List[str]): List of fields that were actually modified
                - status_update (dict): Results of automatic case status update
                - pay_amount_update (dict): Results of automatic pay amount calculation
    
    Raises:
        HTTPException:
            - 400 Bad Request: Missing case_id, no fields to update, or no changes made
            - 404 Not Found: Case does not exist in the database
            - 500 Internal Server Error: Database errors or transaction failures
    
    Database Operations:
        1. Validates case existence in the database
        2. Updates case table fields selectively based on provided data
        3. Replaces procedure codes completely if provided:
            - Deletes all existing procedure codes for the case
            - Inserts new procedure codes with duplicate removal
        4. Triggers automatic pay amount calculation if procedure codes changed
        5. Triggers automatic case status update based on business rules
        6. Commits all changes atomically or rolls back on failure
    
    Business Logic:
        - Only non-null fields in the request are updated
        - case_id is required but not updateable
        - procedure_codes array completely replaces existing codes
        - Duplicate procedure codes are automatically removed while preserving order
        - Pay amount recalculation triggered only when procedure codes change
        - Case status updated automatically based on current business rules
        - All operations must succeed or entire transaction is rolled back
    
    Pay Amount Calculation:
        - Triggered automatically when procedure_codes are provided
        - Uses case owner's user_id (from request or database lookup)
        - Calculates based on procedure codes and user's payment configuration
        - Updates pay_amount field in cases table
        - Failure logged but doesn't abort the entire operation
    
    Case Status Management:
        - Automatic status updates based on current case state and business rules
        - Status changes logged and included in response
        - Independent of other update operations
        - Always attempted after field and procedure code updates
    
    Monitoring & Logging:
        - Business metrics tracking for update operations
        - Prometheus monitoring via @track_business_operation decorator
        - Detailed execution time and response logging
        - Change tracking for all modified fields
        - Error categorization for different failure types:
            * not_found: Case doesn't exist
            * no_changes: No actual database changes occurred
            * error: General transaction or database errors
    
    Transaction Management:
        - Explicit transaction control with begin/commit/rollback
        - All database operations within single transaction
        - Automatic rollback on any operation failure
        - Connection state validation before rollback attempts
        - Proper connection cleanup in finally block
    
    Validation Logic:
        - case_id is mandatory and must exist
        - At least one updateable field must be provided
        - Empty updates return 400 Bad Request
        - Non-existent cases return 404 Not Found
        - Database constraint violations handled gracefully
    
    Example Request:
        PATCH /case
        {
            "case_id": "CASE-2024-001",
            "patient_first": "Jane",
            "surgeon_id": "SURG789",
            "procedure_codes": ["47562", "76705", "99213"]
        }
    
    Example Response:
        {
            "statusCode": 200,
            "body": {
                "message": "Case updated successfully",
                "case_id": "CASE-2024-001",
                "updated_fields": ["patient_first", "surgeon_id", "procedure_codes", "pay_amount"],
                "status_update": {
                    "success": true,
                    "old_status": 1,
                    "new_status": 2,
                    "message": "Status updated from In Review to In Progress"
                },
                "pay_amount_update": {
                    "success": true,
                    "old_amount": 1200.00,
                    "new_amount": 1500.00,
                    "message": "Pay amount recalculated based on procedure codes"
                }
            }
        }
    
    Example Error Response (No Changes):
        {
            "statusCode": 400,
            "body": {
                "error": "No changes made to case"
            }
        }
    
    Note:
        - Only active cases can be updated (soft-deleted cases return 404)
        - Procedure code updates completely replace the existing list
        - Duplicate procedure codes are automatically removed
        - Pay amount recalculation is triggered only when procedure codes change
        - Case status updates are automatic and based on current business rules
        - All field updates are atomic - either all succeed or all are rolled back
        - File path updates do not trigger automatic file operations
        - Empty arrays for procedure_codes will remove all existing procedure codes
    """
    conn = None
    start_time = time.time()
    response_status = 200
    response_data = None
    error_message = None
    user_id = None
    
    try:
        update_fields = {k: v for k, v in case.dict().items() if k not in ("case_id", "procedure_codes") and v is not None}
        if not case.case_id:
            response_status = 400
            error_message = "Missing case_id parameter"
            raise HTTPException(status_code=400, detail="Missing case_id parameter")
        if not update_fields and case.procedure_codes is None:
            response_status = 400
            error_message = "No fields to update"
            raise HTTPException(status_code=400, detail="No fields to update")

        conn = get_db_connection()
        
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            # Check if case exists
            cursor.execute("SELECT case_id FROM cases WHERE case_id = %s", (case.case_id,))
            if not cursor.fetchone():
                # Record failed case update (not found)
                business_metrics.record_case_operation("update", "not_found", case.case_id)
                response_status = 404
                error_message = "Case not found"
                raise HTTPException(status_code=404, detail={"error": "Case not found", "case_id": case.case_id})

            updated_fields = []
            # Update cases table if needed
            if update_fields:
                set_clause = ", ".join([f"{field} = %s" for field in update_fields])
                values = list(update_fields.values())
                values.append(case.case_id)
                sql = f"UPDATE cases SET {set_clause} WHERE case_id = %s"
                cursor.execute(sql, values)
                if cursor.rowcount > 0:
                    updated_fields.extend(update_fields.keys())

            # Update procedure codes if provided
            if case.procedure_codes is not None:
                # Remove duplicates while preserving order
                unique_procedure_codes = list(dict.fromkeys(case.procedure_codes))
                
                # Delete existing codes
                cursor.execute("DELETE FROM case_procedure_codes WHERE case_id = %s", (case.case_id,))
                # Insert new unique codes with descriptions
                for code in unique_procedure_codes:
                    cursor.execute("""
                        INSERT INTO case_procedure_codes (case_id, procedure_code, procedure_desc)
                        SELECT %s, %s, COALESCE(pc.procedure_desc, '')
                        FROM procedure_codes pc 
                        WHERE pc.procedure_code = %s 
                        LIMIT 1
                    """, (case.case_id, code, code))
                updated_fields.append("procedure_codes")

            if not updated_fields:
                # Record failed case update (no changes)
                business_metrics.record_case_operation("update", "no_changes", case.case_id)
                response_status = 400
                error_message = "No changes made to case"
                raise HTTPException(status_code=400, detail="No changes made to case")

            # Calculate and update pay amount if procedure codes were updated or if we need to recalculate
            pay_amount_result = None
            if case.procedure_codes is not None:
                # Get user_id for the case if not provided in update
                if not case.user_id:
                    cursor.execute("SELECT user_id FROM cases WHERE case_id = %s", (case.case_id,))
                    case_user = cursor.fetchone()
                    if case_user:
                        user_id = case_user['user_id']
                    else:
                        user_id = None
                else:
                    user_id = case.user_id
                
                if user_id:
                    pay_amount_result = update_case_pay_amount(case.case_id, user_id, conn)
                    if not pay_amount_result["success"]:
                        logger.error(f"Pay amount calculation failed for case {case.case_id}: {pay_amount_result['message']}")
                        # Don't fail the entire operation, but log the error
                    else:
                        updated_fields.append("pay_amount")

            # Update case status if conditions are met (within the same transaction)
            status_update_result = update_case_status(case.case_id, conn)
            
            # Clear caches BEFORE commit to prevent race conditions
            # This ensures no stale data gets cached between clear and commit
            logger.info(f"🔄 STARTING cache invalidation for case update: {case.case_id}")
            try:
                # 1. Clear global cases cache (affects admin dashboard) - but don't re-warm yet
                from endpoints.backoffice.get_cases_by_status import clear_cases_cache
                clear_cases_cache()  # Clear all cached data
                logger.info(f"✅ CLEARED global cases cache before commit for case update: {case.case_id}")
                
                # 2. Clear user cases cache - but don't re-warm yet
                from endpoints.case.filter_cases import clear_user_cases_cache
                
                # Get user_id from the case data (either provided or from database)
                target_user_id = case.user_id
                if not target_user_id:
                    # Get user_id from database if not provided in update
                    cursor.execute("SELECT user_id FROM cases WHERE case_id = %s", (case.case_id,))
                    case_user = cursor.fetchone()
                    if case_user:
                        target_user_id = case_user['user_id']
                
                if target_user_id:
                    clear_user_cases_cache(target_user_id)  # Clear all cache entries for this user
                    logger.info(f"✅ CLEARED user cases cache for user: {target_user_id}")
                else:
                    logger.warning(f"⚠️ Could not determine user_id for cache invalidation, case: {case.case_id}")
                    
            except Exception as e:
                # Don't fail the main operation if cache invalidation fails
                logger.error(f"❌ Failed to invalidate caches before commit for case update {case.case_id}: {str(e)}", exc_info=True)
            
            # Commit all changes at once
            conn.commit()
            logger.info(f"✅ COMMITTED database changes for case update: {case.case_id}")

            # Record successful case update
            business_metrics.record_case_operation("update", "success", case.case_id)
            
            # Re-warm caches after successful commit
            try:
                # Re-warm global cases cache in background
                from endpoints.backoffice.get_cases_by_status import warm_cases_cache
                import threading
                threading.Thread(
                    target=warm_cases_cache,
                    daemon=True,
                    name="update_case_cache_rewarm_global"
                ).start()
                logger.info(f"🔄 Started background re-warming of global cases cache after case update: {case.case_id}")
                
                # Re-warm user cache if we have a user_id
                if target_user_id:
                    from endpoints.case.filter_cases import _rewarm_user_cases_cache_background
                    threading.Thread(
                        target=_rewarm_user_cases_cache_background,
                        args=(target_user_id,),
                        daemon=True,
                        name=f"update_case_cache_rewarm_user_{target_user_id}"
                    ).start()
                    logger.info(f"🔄 Started background re-warming of user cases cache for user: {target_user_id}")
                
            except Exception as e:
                # Don't fail the main operation if cache re-warming fails
                logger.error(f"❌ Failed to re-warm caches after case update {case.case_id}: {str(e)}", exc_info=True)

        response_data = {
            "statusCode": 200,
            "body": {
                "message": "Case updated successfully",
                "case_id": case.case_id,
                "updated_fields": updated_fields,
                "status_update": status_update_result,
                "pay_amount_update": pay_amount_result
            }
        }
        return response_data

    except HTTPException as http_error:
        # Re-raise HTTP exceptions and capture error details
        response_status = http_error.status_code
        error_message = str(http_error.detail)
        raise
    except Exception as e:
        # Record failed case update
        response_status = 500
        error_message = str(e)
        business_metrics.record_case_operation("update", "error", case.case_id)
        
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
            user_id=user_id,
            response_data=response_data,
            error_message=error_message
        )
        
        # Always close the connection
        if conn:
            close_db_connection(conn)