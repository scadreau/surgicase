# Created: 2025-07-15 09:20:13
# Last Modified: 2025-07-15 14:22:28

# endpoints/user/get_user.py
from fastapi import APIRouter, HTTPException, Query
import pymysql.cursors
from core.database import get_db_connection, close_db_connection
from utils.monitoring import track_business_operation, business_metrics

router = APIRouter()

@router.get("/user")
@track_business_operation("read", "user")
async def get_user(user_id: str = Query(..., description="The user ID to retrieve")):
    """
    Retrieve user information by user_id
    """
    try:
        if not user_id:
            raise HTTPException(status_code=400, detail="Missing user_id parameter")

        conn = get_db_connection()

        try:
            with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                # fetch from users table
                cursor.execute("""select user_id,user_email, first_name, last_name, addr1, addr2, city, state, zipcode, telephone, user_npi, 
                    referred_by_user, user_type, message_pref, states_licensed from user_profile where user_id = %s and active = 1""", (user_id))
                user_data = cursor.fetchone()

                if not user_data:
                    # Record failed user read operation
                    business_metrics.record_user_operation("read", "not_found", user_id)
                    raise HTTPException(
                        status_code=404, 
                        detail={"error": "User not found", "user_id": user_id}
                    )

                # fetch user documents
                cursor.execute("""SELECT document_type, document_name FROM user_documents WHERE user_id = %s""", (user_id,))
                docs = [{"document_type": row['document_type'], "document_name": row['document_name']} for row in cursor.fetchall()]
                user_data['documents'] = docs

            # Record successful user read operation
            business_metrics.record_user_operation("read", "success", user_id)

        finally:
            close_db_connection(conn)

        return {
            "user": user_data,
            "user_id": user_data["user_id"]
        }

    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except Exception as e:
        # Record failed user read operation
        business_metrics.record_user_operation("read", "error", user_id)
        raise HTTPException(status_code=500, detail={"error": str(e)})