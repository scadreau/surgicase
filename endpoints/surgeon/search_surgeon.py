# Created: 2025-07-21 15:08:09
# Last Modified: 2025-07-21 15:18:26

# endpoints/surgeon/search_surgeon.py
from fastapi import APIRouter, HTTPException, Query
import pymysql.cursors
from core.database import get_db_connection, close_db_connection
from utils.monitoring import track_business_operation, business_metrics

router = APIRouter()

@router.get("/search-surgeon")
@track_business_operation("search", "surgeon")
def search_surgeon(
    first_name: str = Query(..., description="First name to search for"),
    last_name: str = Query(..., description="Last name to search for")
):
    """
    Search for surgeons by first and last name.
    Returns all matching records from search_surgeon table.
    """
    try:
        if not first_name.strip() or not last_name.strip():
            raise HTTPException(status_code=400, detail={"error": "Both first_name and last_name are required and cannot be empty"})

        conn = get_db_connection()
        
        try:
            with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                # Search using LIKE for partial matching on both names
                cursor.execute("""
                    SELECT npi, first_name, last_name, address, city, state, zip
                    FROM search_surgeon 
                    WHERE first_name LIKE %s AND last_name LIKE %s
                """, (f"%{first_name}%", f"%{last_name}%"))
                
                surgeons = cursor.fetchall()

                # Record successful surgeon search
                business_metrics.record_surgeon_operation("search", "success", None)
                
        finally:
            close_db_connection(conn)
            
        return {
            "statusCode": 200,
            "body": {
                "message": f"Found {len(surgeons)} matching surgeon(s)",
                "search_criteria": {
                    "first_name": first_name,
                    "last_name": last_name
                },
                "surgeons": surgeons
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        # Record failed surgeon search
        business_metrics.record_surgeon_operation("search", "error", None)
        
        if 'conn' in locals():
            close_db_connection(conn)
        raise HTTPException(status_code=500, detail={"error": f"Internal server error: {str(e)}"}) 