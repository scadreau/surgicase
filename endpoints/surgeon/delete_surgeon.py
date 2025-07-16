# Created: 2025-07-15 09:20:13
# Last Modified: 2025-07-15 20:45:22

# endpoints/surgeon/delete_surgeon.py
from fastapi import APIRouter, HTTPException, Query
import pymysql.cursors
import pymysql
from core.database import get_db_connection, close_db_connection, is_connection_valid
from utils.monitoring import track_business_operation, business_metrics

router = APIRouter()

@router.delete("/surgeon")
@track_business_operation("delete", "surgeon")
def delete_surgeon(surgeon_id: int = Query(..., description="The surgeon ID to delete")):
    """
    Delete a surgeon by surgeon_id.
    """
    conn = None
    try:
        conn = get_db_connection()
        
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute("DELETE FROM surgeon_list WHERE surgeon_id = %s", (surgeon_id,))
            if cursor.rowcount == 0:
                # Record failed surgeon deletion (not found)
                business_metrics.record_surgeon_operation("delete", "not_found", surgeon_id)
                raise HTTPException(status_code=404, detail={"error": "Surgeon not found", "surgeon_id": surgeon_id})
            conn.commit()

            # Record successful surgeon deletion
            business_metrics.record_surgeon_operation("delete", "success", surgeon_id)
            
        return {
            "statusCode": 200,
            "body": {
                "message": "Surgeon deleted successfully",
                "surgeon_id": surgeon_id
            }
        }
    except HTTPException:
        # Re-raise HTTP exceptions without rollback
        raise
    except Exception as e:
        # Record failed surgeon deletion
        business_metrics.record_surgeon_operation("delete", "error", surgeon_id)
        
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