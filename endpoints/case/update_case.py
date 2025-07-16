# Created: 2025-07-15 09:20:13
# Last Modified: 2025-07-15 20:45:03

# endpoints/case/update_case.py
from fastapi import APIRouter, HTTPException, Body
import pymysql.cursors
import pymysql
from core.database import get_db_connection, close_db_connection, is_connection_valid
from core.models import CaseUpdate
from utils.case_status import update_case_status
from utils.monitoring import track_business_operation, business_metrics

router = APIRouter()

@router.patch("/case")
@track_business_operation("update", "case")
def update_case(case: CaseUpdate = Body(...)):
    """
    Update fields in cases and replace procedure codes if provided. Only case_id is required.
    """
    conn = None
    try:
        update_fields = {k: v for k, v in case.dict().items() if k not in ("case_id", "procedure_codes") and v is not None}
        if not case.case_id:
            raise HTTPException(status_code=400, detail="Missing case_id parameter")
        if not update_fields and case.procedure_codes is None:
            raise HTTPException(status_code=400, detail="No fields to update")

        conn = get_db_connection()
        
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            # Check if case exists
            cursor.execute("SELECT case_id FROM cases WHERE case_id = %s", (case.case_id,))
            if not cursor.fetchone():
                # Record failed case update (not found)
                business_metrics.record_case_operation("update", "not_found", case.case_id)
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
                # Delete existing codes
                cursor.execute("DELETE FROM case_procedure_codes WHERE case_id = %s", (case.case_id,))
                # Insert new codes
                for code in case.procedure_codes:
                    cursor.execute(
                        "INSERT INTO case_procedure_codes (case_id, procedure_code) VALUES (%s, %s)",
                        (case.case_id, code)
                    )
                updated_fields.append("procedure_codes")

            if not updated_fields:
                # Record failed case update (no changes)
                business_metrics.record_case_operation("update", "no_changes", case.case_id)
                raise HTTPException(status_code=400, detail="No changes made to case")

            # Update case status if conditions are met (within the same transaction)
            status_update_result = update_case_status(case.case_id, conn)
            
            # Commit all changes at once
            conn.commit()

            # Record successful case update
            business_metrics.record_case_operation("update", "success", case.case_id)

        return {
            "statusCode": 200,
            "body": {
                "message": "Case updated successfully",
                "case_id": case.case_id,
                "updated_fields": updated_fields,
                "status_update": status_update_result
            }
        }

    except HTTPException:
        # Re-raise HTTP exceptions without rollback
        raise
    except Exception as e:
        # Record failed case update
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
        # Always close the connection
        if conn:
            close_db_connection(conn)