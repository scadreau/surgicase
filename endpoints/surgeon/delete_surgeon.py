# Created: 2025-07-15 09:20:13
# Last Modified: 2025-07-15 11:16:24

# endpoints/surgeon/delete_surgeon.py
from fastapi import APIRouter, HTTPException, Query
import pymysql.cursors
from core.database import get_db_connection

router = APIRouter()

@router.delete("/surgeon")
async def delete_surgeon(surgeon_id: int = Query(..., description="The surgeon ID to delete")):
    """
    Delete a surgeon by surgeon_id.
    """
    try:
        conn = get_db_connection()
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute("DELETE FROM surgeon_list WHERE surgeon_id = %s", (surgeon_id,))
            if cursor.rowcount == 0:
                raise HTTPException(status_code=404, detail={"error": "Surgeon not found", "surgeon_id": surgeon_id})
            conn.commit()

        conn.close()
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
        if 'conn' in locals():
            conn.rollback()
            conn.close()
        raise HTTPException(status_code=500, detail={"error": str(e)})