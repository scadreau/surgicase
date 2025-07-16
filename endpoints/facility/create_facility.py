# Created: 2025-07-15 09:20:13
# Last Modified: 2025-07-15 20:45:08

# endpoints/facility/create_facility.py
from fastapi import APIRouter, HTTPException
import pymysql.cursors
import pymysql
from core.database import get_db_connection, close_db_connection, is_connection_valid
from core.models import FacilityCreate
from utils.monitoring import track_business_operation, business_metrics

router = APIRouter()

@router.post("/facility")
@track_business_operation("create", "facility")
def add_facility(facility: FacilityCreate):
    """
    Add a new facility for a user.
    """
    conn = None
    try:
        conn = get_db_connection()
        
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute(
                "INSERT INTO facility_list (user_id, facility_name) VALUES (%s, %s)",
                (facility.user_id, facility.facility_name)
            )
            conn.commit()
            facility_id = cursor.lastrowid

            # Record successful facility creation
            business_metrics.record_facility_operation("create", "success", facility_id)
            
        return {
            "statusCode": 201,
            "body": {
                "message": "Facility created successfully",
                "facility_id": facility_id,
                "user_id": facility.user_id,
                "facility_name": facility.facility_name
            }
        }
    except HTTPException:
        # Re-raise HTTP exceptions without rollback
        raise
    except Exception as e:
        # Record failed facility creation
        business_metrics.record_facility_operation("create", "error", None)
        
        # Safe rollback with connection state check
        if conn and is_connection_valid(conn):
            try:
                conn.rollback()
            except (pymysql.err.InterfaceError, pymysql.err.OperationalError) as rollback_error:
                # Log rollback error but don't raise it
                print(f"Rollback failed: {rollback_error}")
        raise HTTPException(status_code=500, detail={"error": str(e)})
    finally:
        # Always close the connection
        if conn:
            close_db_connection(conn)