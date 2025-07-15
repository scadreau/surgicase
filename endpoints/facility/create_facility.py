# Created: 2025-07-15 09:20:13
# Last Modified: 2025-07-15 14:46:12

# endpoints/facility/create_facility.py
from fastapi import APIRouter, HTTPException
import pymysql.cursors
from core.database import get_db_connection, close_db_connection
from core.models import FacilityCreate
from utils.monitoring import track_business_operation, business_metrics

router = APIRouter()

@router.post("/facility")
@track_business_operation("create", "facility")
async def add_facility(facility: FacilityCreate):
    """
    Add a new facility for a user.
    """
    try:
        conn = get_db_connection()
        
        try:
            with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                cursor.execute(
                    "INSERT INTO facility_list (user_id, facility_name) VALUES (%s, %s)",
                    (facility.user_id, facility.facility_name)
                )
                conn.commit()
                facility_id = cursor.lastrowid

                # Record successful facility creation
                business_metrics.record_facility_operation("create", "success", facility_id)
                
        finally:
            close_db_connection(conn)
            
        return {
            "statusCode": 201,
            "body": {
                "message": "Facility created successfully",
                "facility_id": facility_id,
                "user_id": facility.user_id,
                "facility_name": facility.facility_name
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        # Record failed facility creation
        business_metrics.record_facility_operation("create", "error", None)
        
        if 'conn' in locals():
            conn.rollback()
            close_db_connection(conn)
        raise HTTPException(status_code=500, detail={"error": str(e)})