# Created: 2025-07-15 09:20:13
# Last Modified: 2025-07-15 11:16:46

# endpoints/user/delete_user.py
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
import pymysql.cursors
import json
import datetime as dt
from core.database import get_db_connection

router = APIRouter()

@router.delete("/user")
async def delete_user(user_id: str = Query(..., description="The user ID to delete")):
    """
    Delete (deactivate) user by user_id
    """
    try:
        if not user_id:
            raise HTTPException(status_code=400, detail="Missing user_id parameter")

        print(f"INFO: Connecting to database")
        conn = get_db_connection()
        print("INFO: Database connection established successfully")

        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            # First check if user exists and get current status
            cursor.execute("""SELECT user_id, active FROM user_profile WHERE user_id = %s""", (user_id,))
            user_data = cursor.fetchone()

            if not user_data:
                print(f"ERROR: User not found - user_id: {user_id}")
                return {
                    "statusCode": 404,
                    "body": {"error": "User not found", "user_id":  user_id}
                }

            current_active_status = user_data.get('active')
            print(f"INFO: User found - user_id: {user_id}, current active status: {current_active_status}")

            # Check if user is already inactive
            if current_active_status == 0:
                print(f"WARNING: User already inactive - user_id: {user_id}")
                return {
                    "statusCode": 200,
                    "body": {
                        "message": "User already inactive",
                        "user_id": user_id,
                        "active": 0
                    }
                }

            # Soft delete: set active = 0
            cursor.execute("""UPDATE user_profile SET active = 0 WHERE user_id = %s""", (user_id,))

            # Check if update was successful
            if cursor.rowcount == 0:
                print(f"ERROR: Failed to update user active status - user_id: {user_id}")
                return {
                    "statusCode": 500,
                    "body": {"error": "Failed to deactivate user", "user_id": user_id}
                }

            print(f"SUCCESS: User soft deleted (deactivated) - user_id: {user_id}, rows affected: {cursor.rowcount}")

            # Commit the transaction
            conn.commit()

            return {
                "statusCode": 200,
                "body": {
                    "message": "User deactivated successfully",
                    "user_id": user_id,
                    "active": 0,
                    "deactivated_at": dt.datetime.now(dt.timezone.utc).isoformat() 
                }
            }

    except Exception as e:
        error_msg = f"ERROR: Exception occurred during user soft delete - user_id: {user_id if 'user_id' in locals() else 'unknown'}, error: {str(e)}"
        print(error_msg)

        # Rollback in case of error
        if 'conn' in locals():
            print("INFO: Rolling back database transaction due to error")
            conn.rollback()

        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(e)})
        }

    finally:
        # Close connection if it exists
        if 'conn' in locals():
            print("INFO: Closing database connection")
            conn.close()
            print("INFO: Database connection closed successfully")