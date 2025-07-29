# Created: 2025-07-15 09:20:13
# Last Modified: 2025-07-29 01:52:03

# endpoints/case/create_case.py
from fastapi import APIRouter, HTTPException, Request
from fastapi import Depends
import pymysql.cursors
from core.database import get_db_connection, close_db_connection, is_connection_valid
from core.models import CaseCreate
from utils.case_status import update_case_status
from utils.pay_amount_calculator import update_case_pay_amount
from utils.monitoring import track_business_operation, business_metrics
import logging
import time

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
    
    with conn.cursor(pymysql.cursors.DictCursor) as cursor:
        # Insert into cases table
        cursor.execute("""
            INSERT INTO cases (
                case_id, user_id, case_date, patient_first, patient_last, 
                ins_provider, surgeon_id, facility_id, demo_file, note_file, misc_file
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            case.case_id, case.user_id, case.case_date, case.patient.first, 
            case.patient.last, case.patient.ins_provider, case.surgeon_id, 
            case.facility_id, case.demo_file, case.note_file, case.misc_file
        ))

        # Insert procedure codes using batch operation if any exist
        if case.procedure_codes:
            cursor.executemany("""
                INSERT INTO case_procedure_codes (case_id, procedure_code)
                VALUES (%s, %s)
            """, [(case.case_id, code) for code in case.procedure_codes])

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
    Add a new case to the cases table and its procedure codes to case_procedure_codes table.
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
        
        # Commit all changes at once
        conn.commit()
        
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