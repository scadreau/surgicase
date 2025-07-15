# Created: 2025-07-15 09:20:13
# Last Modified: 2025-07-15 14:46:24

# endpoints/facility/delete_facility.py
from fastapi import APIRouter, HTTPException, Query
import pymysql.cursors
from core.database import get_db_connection, close_db_connection
from utils.monitoring import track_business_operation, business_metrics

router = APIRouter()

@router.delete("/facility")
@track_business_operation("delete", "facility")
async def delete_facility(facility_id: int = Query(..., description="The facility ID to delete")):
    """
    Delete a facility by facility_id.
    """
    try:
        conn = get_db_connection()
        
        try:
            with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                cursor.execute("DELETE FROM facility_list WHERE facility_id = %s", (facility_id,))
                if cursor.rowcount == 0:
                    # Record failed facility deletion (not found)
                    business_metrics.record_facility_operation("delete", "not_found", facility_id)
                    raise HTTPException(status_code=404, detail={"error": "Facility not found", "facility_id": facility_id})
                conn.commit()

                # Record successful facility deletion
                business_metrics.record_facility_operation("delete", "success", facility_id)
                
        finally:
            close_db_connection(conn)
            
        return {
            "statusCode": 200,
            "body": {
                "message": "Facility deleted successfully",
                "facility_id": facility_id
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        # Record failed facility deletion
        business_metrics.record_facility_operation("delete", "error", facility_id)
        
        if 'conn' in locals():
            conn.rollback()
            close_db_connection(conn)
        raise HTTPException(status_code=500, detail={"error": str(e)})