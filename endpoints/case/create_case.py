# Created: 2025-07-15 09:20:13
# Last Modified: 2025-07-15 14:41:03

# endpoints/case/create_case.py
from fastapi import APIRouter, HTTPException
import pymysql.cursors
from core.database import get_db_connection, close_db_connection
from core.models import CaseCreate
from utils.case_status import update_case_status
from utils.monitoring import track_business_operation, business_metrics

router = APIRouter()

@router.post("/case")
@track_business_operation("create", "case")
async def add_case(case: CaseCreate):
    """
    Add a new case and its procedure codes.
    """
    try:
        conn = get_db_connection()
        
        try:
            with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                # Check if case already exists
                cursor.execute("SELECT case_id FROM cases WHERE case_id = %s", (case.case_id,))
                if cursor.fetchone():
                    # Record failed case creation (duplicate)
                    business_metrics.record_case_operation("create", "duplicate", case.case_id)
                    raise HTTPException(status_code=400, detail={"error": "Case already exists", "case_id": case.case_id})

                # Insert into cases table
                cursor.execute("""
                    INSERT INTO cases (case_id, user_id, case_date, patient_first, patient_last, ins_provider, surgeon_id, facility_id, demo_file, note_file, misc_file) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (case.case_id, case.user_id, case.case_date, case.patient.first, case.patient.last, case.patient.ins_provider, case.surgeon_id, case.facility_id, case.demo_file, case.note_file, case.misc_file))

                # Insert procedure codes
                if case.procedure_codes:
                    for code in case.procedure_codes:
                        cursor.execute("""
                            INSERT INTO case_procedure_codes (case_id, procedure_code)
                            VALUES (%s, %s)
                        """, (case.case_id, code))

                conn.commit()
                # Update case status if conditions are met
                status_update_result = update_case_status(case.case_id, conn)                

                # Record successful case creation
                business_metrics.record_case_operation("create", "success", case.case_id)
                
        finally:
            close_db_connection(conn)
        return {
            "statusCode": 201,
            "body": {
                "message": "Case and procedure codes created successfully",
                "user_id": case.user_id,
                "case_id": case.case_id,
                "procedure_codes": case.procedure_codes
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        # Record failed case creation
        business_metrics.record_case_operation("create", "error", case.case_id)
        
        if 'conn' in locals():
            conn.rollback()
            close_db_connection(conn)
        raise HTTPException(status_code=500, detail={"error": str(e)})