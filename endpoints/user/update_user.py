# Created: 2025-07-15 09:20:13
# Last Modified: 2025-07-15 20:44:40

# endpoints/user/update_user.py
from fastapi import APIRouter, HTTPException, Body
import pymysql.cursors
import pymysql
from core.database import get_db_connection, close_db_connection, is_connection_valid
from core.models import UserUpdate
from utils.monitoring import track_business_operation, business_metrics

router = APIRouter()

@router.patch("/user")
@track_business_operation("update", "user")
def update_user(user: UserUpdate = Body(...)):
    """
    Update user fields in user_profile. Only user_id is required; any other provided fields will be updated.
    If documents are provided, replace all user documents with the new list.
    """
    conn = None
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
                # Record failed user update (not found)
                business_metrics.record_user_operation("update", "not_found", user.user_id)
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
                # Insert new documents
                for doc in user.documents:
                    # Delete existing documents for user
                    cursor.execute("DELETE FROM user_documents WHERE user_id = %s and document_type = %s", (user.user_id, doc.document_type))
                    cursor.execute(
                        """
                        INSERT INTO user_documents (user_id, document_type, document_name)
                        VALUES (%s, %s, %s)
                        """,
                        (user.user_id, doc.document_type, doc.document_name)
                    )
                updated_fields.append("documents")
            
            if not updated_fields:
                # Record failed user update (no changes)
                business_metrics.record_user_operation("update", "no_changes", user.user_id)
                raise HTTPException(status_code=400, detail="No changes made to user")
            
            conn.commit()
            
            # Record successful user update
            business_metrics.record_user_operation("update", "success", user.user_id)

        return {
            "statusCode": 200,
            "body": {
                "message": "User updated successfully",
                "user_id": user.user_id,
                "updated_fields": list(updated_fields)
            }
        }

    except HTTPException:
        # Re-raise HTTP exceptions without rollback
        raise
    except Exception as e:
        # Record failed user update
        business_metrics.record_user_operation("update", "error", user.user_id)
        
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