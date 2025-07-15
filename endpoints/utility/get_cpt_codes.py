# endpoints/utility/get_cpt_codes.py
from fastapi import APIRouter, HTTPException
import pymysql.cursors
from core.database import get_db_connection

router = APIRouter()

@router.get("/cpt_codes")
async def get_cpt_codes():
    """
    Get all CPT codes.
    """
    try:
        conn = get_db_connection()
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute("""SELECT cpt_code, cpt_description FROM cpt_codes""")
            cpt_codes = cursor.fetchall()

        conn.close()
        return {
            "cpt_codes": cpt_codes
        }
    except Exception as e:
        if 'conn' in locals():
            conn.close()
        raise HTTPException(status_code=500, detail={"error": str(e)})