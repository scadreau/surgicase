# Created: 2025-07-15 09:20:13
# Last Modified: 2025-07-15 16:07:33

# endpoints/surgeon/create_surgeon.py
from fastapi import APIRouter, HTTPException
import pymysql.cursors
import pymysql
from core.database import get_db_connection, close_db_connection, is_connection_valid
from core.models import SurgeonCreate
from utils.monitoring import track_business_operation, business_metrics

router = APIRouter()

@router.post("/surgeon")
@track_business_operation("create", "surgeon")
async def add_surgeon(surgeon: SurgeonCreate):
    """
    Add a new surgeon for a user.
    """
    conn = None
    try:
        conn = get_db_connection()
        
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute(
                "INSERT INTO surgeon_list (user_id, first_name, last_name) VALUES (%s, %s, %s)",
                (surgeon.user_id, surgeon.first_name, surgeon.last_name)
            )
            conn.commit()
            surgeon_id = cursor.lastrowid

            # Record successful surgeon creation
            business_metrics.record_surgeon_operation("create", "success", surgeon_id)
            
        return {
            "statusCode": 201,
            "body": {
                "message": "Surgeon created successfully",
                "surgeon_id": surgeon_id,
                "user_id": surgeon.user_id,
                "first_name": surgeon.first_name,
                "last_name": surgeon.last_name
            }
        }
    except HTTPException:
        # Re-raise HTTP exceptions without rollback
        raise
    except Exception as e:
        # Record failed surgeon creation
        business_metrics.record_surgeon_operation("create", "error", None)
        
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