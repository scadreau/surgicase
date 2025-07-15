# Created: 2025-07-15 09:20:13
# Last Modified: 2025-07-15 11:16:53

# endpoints/user/get_user.py
from fastapi import APIRouter, HTTPException, Query
import pymysql.cursors
from core.database import get_db_connection

router = APIRouter()

@router.get("/user")
async def get_user(user_id: str = Query(..., description="The user ID to retrieve")):
    """
    Retrieve user information by user_id
    """
    try:
        if not user_id:
            raise HTTPException(status_code=400, detail="Missing user_id parameter")

        conn = get_db_connection()

        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            # fetch from users table
            cursor.execute("""select user_id,user_email, first_name, last_name, addr1, addr2, city, state, zipcode, telephone, user_npi, 
                referred_by_user, user_type, message_pref, states_licensed from user_profile where user_id = %s and active = 1""", (user_id))
            user_data = cursor.fetchone()
            print(user_data)

            if not user_data:
                raise HTTPException(
                    status_code=404, 
                    detail={"error": "User not found", "user_id": user_id}
                )

            # fetch procedure codes - these are in a separate table and there can be multiple procedure codes for a case
            cursor.execute("""SELECT document_type, document_name FROM user_documents WHERE user_id = %s""", (user_id,))
            docs = [{"document_type": row['document_type'], "document_name": row['document_name']} for row in cursor.fetchall()]
            user_data['documents'] = docs

        conn.close()

        return {
            "user": user_data,
            "user_id": user_data["user_id"]
        }

    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail={"error": str(e)})