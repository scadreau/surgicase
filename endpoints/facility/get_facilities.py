# Created: 2025-07-15 09:20:13
# Last Modified: 2025-07-15 20:43:58

# endpoints/facility/get_facilities.py
from fastapi import APIRouter, HTTPException, Query
import pymysql.cursors
from core.database import get_db_connection, close_db_connection
from utils.monitoring import track_business_operation, business_metrics

router = APIRouter()

@router.get("/facilities")
@track_business_operation("get", "facility")
def get_facilities(user_id: str = Query(..., description="The user ID to retrieve facilities for")):
    """
    Get all facilities for a user_id.
    """
    try:
        conn = get_db_connection()
        
        try:
            with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                cursor.execute(
                    "SELECT facility_id, facility_name FROM facility_list WHERE user_id = %s",
                    (user_id,)
                )
                facilities = cursor.fetchall()

                # Record successful facility retrieval
                business_metrics.record_facility_operation("get", "success", None)
                
        finally:
            close_db_connection(conn)
            
        return {
            "user_id": user_id,
            "facilities": facilities
        }
    except HTTPException:
        raise
    except Exception as e:
        # Record failed facility retrieval
        business_metrics.record_facility_operation("get", "error", None)
        
        if 'conn' in locals():
            close_db_connection(conn)
        raise HTTPException(status_code=500, detail={"error": str(e)})