# Created: 2025-07-15 09:20:13
# Last Modified: 2025-07-15 20:44:13

# endpoints/utility/get_cpt_codes.py
from fastapi import APIRouter, HTTPException
import pymysql.cursors
from core.database import get_db_connection, close_db_connection
from utils.monitoring import track_business_operation, business_metrics

router = APIRouter()

@router.get("/cpt_codes")
@track_business_operation("get", "cpt_codes")
def get_cpt_codes():
    """
    Get all CPT codes.
    """
    try:
        conn = get_db_connection()
        
        try:
            with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                cursor.execute("""SELECT cpt_code, cpt_description FROM cpt_codes""")
                cpt_codes = cursor.fetchall()

                # Record successful CPT codes retrieval
                business_metrics.record_utility_operation("get_cpt_codes", "success")
                
        finally:
            close_db_connection(conn)
            
        return {
            "cpt_codes": cpt_codes
        }
    except HTTPException:
        raise
    except Exception as e:
        # Record failed CPT codes retrieval
        business_metrics.record_utility_operation("get_cpt_codes", "error")
        
        if 'conn' in locals():
            close_db_connection(conn)
        raise HTTPException(status_code=500, detail={"error": str(e)})