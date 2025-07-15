# Created: 2025-07-15 09:20:13
# Last Modified: 2025-07-15 11:16:32

# endpoints/surgeon/get_surgeons.py
from fastapi import APIRouter, HTTPException, Query
import pymysql.cursors
from core.database import get_db_connection

router = APIRouter()

@router.get("/surgeons")
async def get_surgeons(user_id: str = Query(..., description="The user ID to retrieve surgeons for")):
    """
    Get all surgeons for a user_id.
    """
    try:
        conn = get_db_connection()
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute(
                "SELECT surgeon_id, first_name, last_name FROM surgeon_list WHERE user_id = %s",
                (user_id,)
            )
            surgeons = cursor.fetchall()

        conn.close()
        return {
            "user_id": user_id,
            "surgeons": surgeons
        }
    except Exception as e:
        if 'conn' in locals():
            conn.close()
        raise HTTPException(status_code=500, detail={"error": str(e)})