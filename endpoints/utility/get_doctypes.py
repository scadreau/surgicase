# Created: 2025-07-15 09:20:13
# Last Modified: 2025-07-15 14:47:18

# endpoints/utility/get_doctypes.py
from fastapi import APIRouter, HTTPException
import pymysql.cursors
from core.database import get_db_connection, close_db_connection
from utils.monitoring import track_business_operation, business_metrics

router = APIRouter()

@router.get("/doctypes")
@track_business_operation("get", "doctypes")
async def get_doc_types():
    """
    Get all document types.
    """
    try:
        conn = get_db_connection()
        
        try:
            with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                cursor.execute(
                    "SELECT doc_type FROM doc_type_list"
                )
                doc_types = cursor.fetchall()

                # Record successful document types retrieval
                business_metrics.record_utility_operation("get_doctypes", "success")
                
        finally:
            close_db_connection(conn)
            
        return {
            "document_types": doc_types
        }
    except HTTPException:
        raise
    except Exception as e:
        # Record failed document types retrieval
        business_metrics.record_utility_operation("get_doctypes", "error")
        
        if 'conn' in locals():
            close_db_connection(conn)
        raise HTTPException(status_code=500, detail={"error": str(e)})