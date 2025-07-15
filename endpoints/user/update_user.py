# Created: 2025-07-15 09:20:13
# Last Modified: 2025-07-15 11:17:01

# endpoints/user/update_user.py
from fastapi import APIRouter, HTTPException, Body
import pymysql.cursors
from core.database import get_db_connection
from core.models import UserUpdate

router = APIRouter()

@router.patch("/user")
async def update_user(user: UserUpdate = Body(...)):
    """
    Update user fields in user_profile. Only user_id is required; any other provided fields will be updated.
    If documents are provided, replace all user documents with the new list.
    """
    try:
        # Ensure at least one field to update besides user_id or documents
        update_fields = {k: v for k, v in user.dict().items() if k not in ("user_id", "documents") and v is not None}
        if not user.user_id:
            raise HTTPException(status_code=400, detail="Missing user_id parameter")
        if not update_fields and user.documents is None:
            raise HTTPException(status_code=400, detail="No fields to update")

        conn = get_db_connection()
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            # Check if user exists
            cursor.execute("SELECT user_id FROM user_profile WHERE user_id = %s", (user.user_id,))
            if not cursor.fetchone():
                raise HTTPException(status_code=404, detail={"error": "User not found", "user_id": user.user_id})

            updated_fields = []
            # Update user_profile table if needed
            if update_fields:
                set_clause = ", ".join([f"{field} = %s" for field in update_fields])
                values = list(update_fields.values())
                values.append(user.user_id)
                sql = f"UPDATE user_profile SET {set_clause} WHERE user_id = %s"
                cursor.execute(sql, values)
                if cursor.rowcount > 0:
                    updated_fields.extend(update_fields.keys())
            # Replace user documents if provided
            if user.documents is not None:
                # Delete existing documents for user
                cursor.execute("DELETE FROM user_documents WHERE user_id = %s", (user.user_id,))
                # Insert new documents
                for doc in user.documents:
                    cursor.execute(
                        """
                        INSERT INTO user_documents (user_id, document_type, document_name)
                        VALUES (%s, %s, %s)
                        """,
                        (user.user_id, doc.document_type, doc.document_name)
                    )
                updated_fields.append("documents")
            conn.commit()

        conn.close()
        return {
            "statusCode": 200,
            "body": {
                "message": "User updated successfully",
                "user_id": user.user_id,
                "updated_fields": list(updated_fields)
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        if 'conn' in locals():
            conn.rollback()
            conn.close()
        raise HTTPException(status_code=500, detail={"error": str(e)})