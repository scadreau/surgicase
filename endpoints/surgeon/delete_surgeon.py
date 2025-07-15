# Created: 2025-07-15 09:20:13
# Last Modified: 2025-07-15 14:45:53

# endpoints/surgeon/delete_surgeon.py
from fastapi import APIRouter, HTTPException, Query
import pymysql.cursors
from core.database import get_db_connection, close_db_connection
from utils.monitoring import track_business_operation, business_metrics

router = APIRouter()

@router.delete("/surgeon")
@track_business_operation("delete", "surgeon")
async def delete_surgeon(surgeon_id: int = Query(..., description="The surgeon ID to delete")):
    """
    Delete a surgeon by surgeon_id.
    """
    try:
        conn = get_db_connection()
        
        try:
            with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                cursor.execute("DELETE FROM surgeon_list WHERE surgeon_id = %s", (surgeon_id,))
                if cursor.rowcount == 0:
                    # Record failed surgeon deletion (not found)
                    business_metrics.record_surgeon_operation("delete", "not_found", surgeon_id)
                    raise HTTPException(status_code=404, detail={"error": "Surgeon not found", "surgeon_id": surgeon_id})
                conn.commit()

                # Record successful surgeon deletion
                business_metrics.record_surgeon_operation("delete", "success", surgeon_id)
                
        finally:
            close_db_connection(conn)
            
        return {
            "statusCode": 200,
            "body": {
                "message": "Surgeon deleted successfully",
                "surgeon_id": surgeon_id
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        # Record failed surgeon deletion
        business_metrics.record_surgeon_operation("delete", "error", surgeon_id)
        
        if 'conn' in locals():
            conn.rollback()
            close_db_connection(conn)
        raise HTTPException(status_code=500, detail={"error": str(e)})