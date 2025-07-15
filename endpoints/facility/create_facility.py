# Created: 2025-07-15 09:20:13
# Last Modified: 2025-07-15 11:15:47

# endpoints/facility/create_facility.py
from fastapi import APIRouter, HTTPException
import pymysql.cursors
from core.database import get_db_connection
from core.models import FacilityCreate

router = APIRouter()

@router.post("/facility")
async def add_facility(facility: FacilityCreate):
    """
    Add a new facility for a user.
    """
    try:
        conn = get_db_connection()
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute(
                "INSERT INTO facility_list (user_id, facility_name) VALUES (%s, %s)",
                (facility.user_id, facility.facility_name)
            )
            conn.commit()
            facility_id = cursor.lastrowid

        conn.close()
        return {
            "statusCode": 201,
            "body": {
                "message": "Facility created successfully",
                "facility_id": facility_id,
                "user_id": facility.user_id,
                "facility_name": facility.facility_name
            }
        }
    except Exception as e:
        if 'conn' in locals():
            conn.rollback()
            conn.close()
        raise HTTPException(status_code=500, detail={"error": str(e)})