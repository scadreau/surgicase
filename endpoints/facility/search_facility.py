# Created: 2025-07-21 16:40:47
# Last Modified: 2025-07-21 16:40:48

# endpoints/facility/search_facility.py
from fastapi import APIRouter, HTTPException, Query
import pymysql.cursors
from core.database import get_db_connection, close_db_connection
from utils.monitoring import track_business_operation, business_metrics

router = APIRouter()

@router.get("/search-facility")
@track_business_operation("search", "facility")
def search_facility(
    facility_name: str = Query(..., description="Facility name to search for")
):
    """
    Search for facilities by facility name.
    Returns all matching records from search_facility table.
    """
    try:
        if not facility_name.strip():
            raise HTTPException(status_code=400, detail={"error": "facility_name is required and cannot be empty"})

        conn = get_db_connection()
        
        try:
            with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                # Search using LIKE for partial matching on facility name
                cursor.execute("""
                    SELECT *
                    FROM search_facility 
                    WHERE facility_name LIKE %s
                """, (f"%{facility_name}%",))
                
                facilities = cursor.fetchall()

                # Record successful facility search
                business_metrics.record_facility_operation("search", "success", None)
                
        finally:
            close_db_connection(conn)
            
        return {
            "statusCode": 200,
            "body": {
                "message": f"Found {len(facilities)} matching facility(ies)",
                "search_criteria": {
                    "facility_name": facility_name
                },
                "facilities": facilities
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        # Record failed facility search
        business_metrics.record_facility_operation("search", "error", None)
        
        if 'conn' in locals():
            close_db_connection(conn)
        raise HTTPException(status_code=500, detail={"error": f"Internal server error: {str(e)}"}) 