# Created: 2025-07-15 09:20:13
# Last Modified: 2025-07-15 11:15:56

# endpoints/facility/delete_facility.py
from fastapi import APIRouter, HTTPException, Query
import pymysql.cursors
from core.database import get_db_connection

router = APIRouter()

@router.delete("/facility")
async def delete_facility(facility_id: int = Query(..., description="The facility ID to delete")):
    """
    Delete a facility by facility_id.
    """
    try:
        conn = get_db_connection()
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute("DELETE FROM facility_list WHERE facility_id = %s", (facility_id,))
            if cursor.rowcount == 0:
                raise HTTPException(status_code=404, detail={"error": "Facility not found", "facility_id": facility_id})
            conn.commit()

        conn.close()
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
        if 'conn' in locals():
            conn.rollback()
            conn.close()
        raise HTTPException(status_code=500, detail={"error": str(e)})