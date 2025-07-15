# Created: 2025-07-15 09:20:13
# Last Modified: 2025-07-15 16:07:05

# endpoints/case/delete_case.py
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
import pymysql.cursors
import pymysql
import json
import datetime as dt
from core.database import get_db_connection, close_db_connection, is_connection_valid
from utils.monitoring import track_business_operation, business_metrics

router = APIRouter()

@router.delete("/case")
@track_business_operation("delete", "case")
async def delete_case(case_id: str = Query(..., description="The case ID to delete")):
    """
    Delete (deactivate) case by case_id
    """
    conn = None
    try:
        if not case_id:
            raise HTTPException(status_code=400, detail="Missing case_id parameter")

        print(f"INFO: Connecting to database")
        conn = get_db_connection()
        print("INFO: Database connection established successfully")

        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            # First check if case exists and get current status
            cursor.execute("""SELECT case_id, active FROM cases WHERE case_id = %s""", (case_id,))
            case_data = cursor.fetchone()

            if not case_data:
                print(f"ERROR: Case not found - case_id: {case_id}")
                # Record failed case deletion (not found)
                business_metrics.record_case_operation("delete", "not_found", case_id)
                return {
                    "statusCode": 404,
                    "body": {"error": "Case not found", "case_id": case_id}
                }

        current_active_status = case_data.get('active')
        print(f"INFO: Case found - case_id: {case_id}, current active status: {current_active_status}")

        # Check if case is already inactive
        if current_active_status == 0:
            print(f"WARNING: Case already inactive - case_id: {case_id}")
            # Record case deletion (already inactive)
            business_metrics.record_case_operation("delete", "already_inactive", case_id)
            return {
                "statusCode": 200,
                "body": {
                    "message": "Case already inactive",
                    "case_id": case_id,
                    "active": 0
                }
            }

        # Soft delete: set active = 0
        cursor.execute("""UPDATE cases SET active = 0 WHERE case_id = %s""", (case_id,))

        # Check if update was successful
        if cursor.rowcount == 0:
            print(f"ERROR: Failed to update case active status - case_id: {case_id}")
            # Record failed case deletion
            business_metrics.record_case_operation("delete", "update_failed", case_id)
            return {
                "statusCode": 500,
                "body": {"error": "Failed to deactivate case", "case_id": case_id}
            }

        print(f"SUCCESS: Case soft deleted (deactivated) - case_id: {case_id}, rows affected: {cursor.rowcount}")

        # Commit the transaction
        conn.commit()
        
        # Record successful case deletion
        business_metrics.record_case_operation("delete", "success", case_id)

        return {
            "statusCode": 200,
            "body": {
                "message": "Case deactivated successfully",
                "case_id": case_id,
                "active": 0,
                "deactivated_at": dt.datetime.now(dt.timezone.utc).isoformat()
            }
        }

    except HTTPException:
        # Re-raise HTTP exceptions without rollback
        raise
    except Exception as e:
        error_msg = f"ERROR: Exception occurred during case soft delete - case_id: {case_id if 'case_id' in locals() else 'unknown'}, error: {str(e)}"
        print(error_msg)
        
        # Record failed case deletion
        business_metrics.record_case_operation("delete", "error", case_id if 'case_id' in locals() else 'unknown')

        # Safe rollback with connection state check
        if conn and is_connection_valid(conn):
            try:
                print("INFO: Rolling back database transaction due to error")
                conn.rollback()
            except (pymysql.err.InterfaceError, pymysql.err.OperationalError) as rollback_error:
                # Log rollback error but don't raise it
                print(f"Rollback failed: {rollback_error}")

        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(e)})
        }
    finally:
        # Always close the connection
        if conn:
            close_db_connection(conn)