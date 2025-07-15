# Created: 2025-07-15 09:20:13
# Last Modified: 2025-07-15 11:16:03

# endpoints/facility/get_facilities.py
from fastapi import APIRouter, HTTPException, Query
import pymysql.cursors
from core.database import get_db_connection

router = APIRouter()

@router.get("/facilities")
async def get_facilities(user_id: str = Query(..., description="The user ID to retrieve facilities for")):
    """
    Get all facilities for a user_id.
    """
    try:
        conn = get_db_connection()
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute(
                "SELECT facility_id, facility_name FROM facility_list WHERE user_id = %s",
                (user_id,)
            )
            facilities = cursor.fetchall()

        conn.close()
        return {
            "user_id": user_id,
            "facilities": facilities
        }
    except Exception as e:
        if 'conn' in locals():
            conn.close()
        raise HTTPException(status_code=500, detail={"error": str(e)})