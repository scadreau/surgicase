# Created: 2025-07-15 09:20:13
# Last Modified: 2025-07-15 16:06:40

# endpoints/user/create_user.py
from fastapi import APIRouter, HTTPException
import pymysql.cursors
import pymysql
from core.database import get_db_connection, close_db_connection, is_connection_valid
from core.models import UserCreate
from utils.monitoring import track_business_operation, business_metrics

router = APIRouter()

@router.post("/user")
@track_business_operation("create", "user")
async def add_user(user: UserCreate):
    """
    Add a new user to the user_profile table.
    """
    conn = None
    try:
        conn = get_db_connection()
        
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            # Check if user already exists
            cursor.execute("SELECT user_id FROM user_profile WHERE user_id = %s", (user.user_id,))
            if cursor.fetchone():
                # Record failed user creation (duplicate)
                business_metrics.record_user_operation("create", "duplicate", user.user_id)
                raise HTTPException(status_code=400, detail={"error": "User already exists", "user_id": user.user_id})

            # Insert new user
            cursor.execute("""
                INSERT INTO user_profile (
                    user_id, user_email, first_name, last_name, addr1, addr2, city, state, zipcode, telephone, user_npi, referred_by_user, message_pref, states_licensed
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                user.user_id, user.user_email, user.first_name, user.last_name, user.addr1, user.addr2,
                user.city, user.state, user.zipcode, user.telephone, user.user_npi, user.referred_by_user, user.message_pref, user.states_licensed
            ))
            # Insert user documents if provided
            if user.documents:
                for doc in user.documents:
                    cursor.execute(
                        """
                        INSERT INTO user_documents (user_id, document_type, document_name)
                        VALUES (%s, %s, %s)
                        """,
                        (user.user_id, doc.document_type, doc.document_name)
                    )
            conn.commit()
            
            # Record successful user creation
            business_metrics.record_user_operation("create", "success", user.user_id)
            
        return {
            "statusCode": 201,
            "body": {
                "message": "User created successfully",
                "user_id": user.user_id
            }
        }

    except HTTPException:
        # Re-raise HTTP exceptions without rollback
        raise
    except Exception as e:
        # Record failed user creation
        business_metrics.record_user_operation("create", "error", user.user_id)
        
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