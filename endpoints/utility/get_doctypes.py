# endpoints/utility/get_doctypes.py
from fastapi import APIRouter, HTTPException
import pymysql.cursors
from core.database import get_db_connection

router = APIRouter()

@router.get("/doctypes")
async def get_doc_types():
    """
    Get all document types.
    """
    try:
        conn = get_db_connection()
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute(
                "SELECT doc_type FROM doc_type_list"
            )
            doc_types = cursor.fetchall()

        conn.close()
        return {
            "document_types": doc_types
        }
    except Exception as e:
        if 'conn' in locals():
            conn.close()
        raise HTTPException(status_code=500, detail={"error": str(e)})