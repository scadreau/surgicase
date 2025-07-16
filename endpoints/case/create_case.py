# Created: 2025-07-15 09:20:13
# Last Modified: 2025-07-15 18:03:33

# endpoints/case/create_case.py
from fastapi import APIRouter, HTTPException
import pymysql.cursors
import pymysql
from core.database import get_db_connection, close_db_connection, is_connection_valid
from core.models import CaseCreate
from utils.case_status import update_case_status
from utils.monitoring import track_business_operation, business_metrics

router = APIRouter()

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

        # Update case status if conditions are met (within the same transaction)
        status_update_result = update_case_status(case.case_id, conn)
        
        return status_update_result

@router.post("/case")
@track_business_operation("create", "case")
async def add_case(case: CaseCreate):
    """
    Add a new case and its procedure codes.
    """
    conn = None
    try:
        conn = get_db_connection()
        
        # Check if case already exists before starting transaction
        if case_exists(case.case_id, conn):
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
        
        return {
            "message": "Case and procedure codes created successfully",
            "user_id": case.user_id,
            "case_id": case.case_id,
            "procedure_codes": case.procedure_codes,
            "status_update": status_update_result
        }

    except HTTPException:
        # Re-raise HTTP exceptions without rollback (no transaction started yet)
        raise
        
    except Exception as e:
        # Record failed case creation
        business_metrics.record_case_operation("create", "error", case.case_id)
        
        # Safe rollback with connection state check
        if conn and is_connection_valid(conn):
            try:
                conn.rollback()
            except (pymysql.err.InterfaceError, pymysql.err.OperationalError) as rollback_error:
                # Log rollback error but don't raise it
                print(f"Rollback failed: {rollback_error}")
                
        raise HTTPException(status_code=500, detail={"error": str(e)})
        
    finally:
        # Always close the connection
        if conn:
            close_db_connection(conn)