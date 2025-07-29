# Created: 2025-07-15 09:20:13
# Last Modified: 2025-07-29 01:51:57

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
    Update fields in cases and replace procedure codes if provided. Only case_id is required.
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
                # Insert new unique codes
                for code in unique_procedure_codes:
                    cursor.execute(
                        "INSERT INTO case_procedure_codes (case_id, procedure_code) VALUES (%s, %s)",
                        (case.case_id, code)
                    )
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
            
            # Commit all changes at once
            conn.commit()

            # Record successful case update
            business_metrics.record_case_operation("update", "success", case.case_id)

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