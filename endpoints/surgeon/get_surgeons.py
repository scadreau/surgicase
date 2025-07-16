# Created: 2025-07-15 09:20:13
# Last Modified: 2025-07-15 20:44:04

# endpoints/surgeon/get_surgeons.py
from fastapi import APIRouter, HTTPException, Query
import pymysql.cursors
from core.database import get_db_connection, close_db_connection
from utils.monitoring import track_business_operation, business_metrics

router = APIRouter()

@router.get("/surgeons")
@track_business_operation("get", "surgeon")
def get_surgeons(user_id: str = Query(..., description="The user ID to retrieve surgeons for")):
    """
    Get all surgeons for a user_id.
    """
    try:
        conn = get_db_connection()
        
        try:
            with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                cursor.execute(
                    "SELECT surgeon_id, first_name, last_name FROM surgeon_list WHERE user_id = %s",
                    (user_id,)
                )
                surgeons = cursor.fetchall()

                # Record successful surgeon retrieval
                business_metrics.record_surgeon_operation("get", "success", None)
                
        finally:
            close_db_connection(conn)
            
        return {
            "user_id": user_id,
            "surgeons": surgeons
        }
    except HTTPException:
        raise
    except Exception as e:
        # Record failed surgeon retrieval
        business_metrics.record_surgeon_operation("get", "error", None)
        
        if 'conn' in locals():
            close_db_connection(conn)
        raise HTTPException(status_code=500, detail={"error": str(e)})