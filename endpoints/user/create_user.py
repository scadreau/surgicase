# Created: 2025-07-15 09:20:13
# Last Modified: 2025-07-15 11:16:40

# endpoints/user/create_user.py
from fastapi import APIRouter, HTTPException
import pymysql.cursors
from core.database import get_db_connection
from core.models import UserCreate

router = APIRouter()

@router.post("/user")
async def add_user(user: UserCreate):
    """
    Add a new user to the user_profile table.
    """
    try:
        conn = get_db_connection()
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            # Check if user already exists
            cursor.execute("SELECT user_id FROM user_profile WHERE user_id = %s", (user.user_id,))
            if cursor.fetchone():
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

        conn.close()
        return {
            "statusCode": 201,
            "body": {
                "message": "User created successfully",
                "user_id": user.user_id
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        if 'conn' in locals():
            conn.rollback()
            conn.close()
        raise HTTPException(status_code=500, detail={"error": str(e)})