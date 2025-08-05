# Created: 2025-07-15 09:20:13
# Last Modified: 2025-08-05 20:27:43
# Author: Scott Cadreau

# endpoints/user/delete_user.py
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse
import pymysql.cursors
import json
import datetime as dt
import time
import boto3
from core.database import get_db_connection, close_db_connection, is_connection_valid
from utils.monitoring import track_business_operation, business_metrics
from utils.archive_deleted_user import archive_deleted_user

router = APIRouter()

def delete_cognito_user(user_id: str) -> bool:
    """
    Delete user from Cognito User Pool
    
    Args:
        user_id (str): The Cognito user ID to delete
        
    Returns:
        bool: True if deletion successful or user not found, False if deletion failed
        
    Raises:
        Exception: If there's a network/permission error during deletion
    """
    try:
        # Initialize Cognito Identity Provider client
        cognito_client = boto3.client('cognito-idp', region_name='us-east-1')
        
        # Attempt to delete the user from the user pool
        cognito_client.admin_delete_user(
            UserPoolId='us-east-1_whzpZgWwq',
            Username=user_id
        )
        
        print(f"INFO: Successfully deleted user from Cognito - user_id: {user_id}")
        return True
        
    except cognito_client.exceptions.UserNotFoundException:
        # User doesn't exist in Cognito - this is acceptable, continue with soft delete
        print(f"INFO: User not found in Cognito, continuing with database deletion - user_id: {user_id}")
        return True
        
    except Exception as e:
        # Any other error is a failure that should trigger rollback
        print(f"ERROR: Failed to delete user from Cognito - user_id: {user_id}, error: {str(e)}")
        raise Exception(f"Cognito user deletion failed: {str(e)}")

@router.delete("/user")
@track_business_operation("delete", "user")
def delete_user(request: Request, user_id: str = Query(..., description="The user ID to delete")):
    """
    Delete (deactivate) user by user_id
    """
    conn = None
    start_time = time.time()
    response_status = 200
    response_data = None
    error_message = None
    
    try:
        if not user_id:
            response_status = 400
            error_message = "Missing user_id parameter"
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
                # Record failed user deletion (not found)
                business_metrics.record_user_operation("delete", "not_found", user_id)
                response_status = 404
                error_message = "User not found"
                response_data = {
                    "statusCode": 404,
                    "body": {"error": "User not found", "user_id":  user_id}
                }
                return response_data

            current_active_status = user_data.get('active')
            print(f"INFO: User found - user_id: {user_id}, current active status: {current_active_status}")

            # Check if user is already inactive
            if current_active_status == 0:
                print(f"WARNING: User already inactive - user_id: {user_id}")
                # Record user deletion (already inactive)
                business_metrics.record_user_operation("delete", "already_inactive", user_id)
                response_data = {
                    "statusCode": 200,
                    "body": {
                        "message": "User already inactive",
                        "user_id": user_id,
                        "active": 0
                    }
                }
                return response_data

            # Soft delete: set active = 0
            cursor.execute("""UPDATE user_profile SET active = 0 WHERE user_id = %s""", (user_id,))

            # Check if update was successful
            if cursor.rowcount == 0:
                print(f"ERROR: Failed to update user active status - user_id: {user_id}")
                # Record failed user deletion
                business_metrics.record_user_operation("delete", "update_failed", user_id)
                response_status = 500
                error_message = "Failed to deactivate user"
                response_data = {
                    "statusCode": 500,
                    "body": {"error": "Failed to deactivate user", "user_id": user_id}
                }
                return response_data

            print(f"SUCCESS: User soft deleted (deactivated) - user_id: {user_id}, rows affected: {cursor.rowcount}")

            # Commit the transaction
            conn.commit()
            
            # Record successful user deletion
            business_metrics.record_user_operation("delete", "success", user_id)

            # Archive the deleted user
            # Note: This includes S3 user document movement and will raise exceptions on failure
            try:
                archive_deleted_user(user_id)
            except Exception as archive_error:
                # If archiving (including S3 movement) fails, we need to rollback the soft delete
                print(f"ERROR: Archive operation failed for user {user_id}: {str(archive_error)}")
                
                # Rollback the soft delete by setting active = 1
                try:
                    cursor.execute("""UPDATE user_profile SET active = 1 WHERE user_id = %s""", (user_id,))
                    conn.commit()
                    print(f"INFO: Rolled back user soft delete due to archive failure - user_id: {user_id}")
                except Exception as rollback_error:
                    print(f"CRITICAL: Failed to rollback user soft delete - user_id: {user_id}, error: {str(rollback_error)}")
             
                # Record failed user deletion due to archive/S3 failure
                business_metrics.record_user_operation("delete", "archive_failed", user_id)
                
                response_status = 500
                error_message = f"User deletion failed during archive/S3 operations: {str(archive_error)}"
                response_data = {
                    "statusCode": 500,
                    "body": {
                        "error": f"User deletion failed during archive/S3 operations: {str(archive_error)}",
                        "user_id": user_id,
                        "details": "User has been restored to active status"
                    }
                }
                return response_data

            # Delete user from Cognito User Pool (only after successful archive)
            try:
                delete_cognito_user(user_id)
                business_metrics.record_user_operation("delete", "cognito_success", user_id)
            except Exception as cognito_error:
                # If Cognito deletion fails, we need to rollback everything
                print(f"ERROR: Cognito deletion failed for user {user_id}: {str(cognito_error)}")
                
                # Rollback the soft delete by setting active = 1
                try:
                    cursor.execute("""UPDATE user_profile SET active = 1 WHERE user_id = %s""", (user_id,))
                    conn.commit()
                    print(f"INFO: Rolled back user soft delete due to Cognito failure - user_id: {user_id}")
                except Exception as rollback_error:
                    print(f"CRITICAL: Failed to rollback user soft delete - user_id: {user_id}, error: {str(rollback_error)}")
             
                # Record failed user deletion due to Cognito failure
                business_metrics.record_user_operation("delete", "cognito_failed", user_id)
                
                response_status = 500
                error_message = f"User deletion failed during Cognito operations: {str(cognito_error)}"
                response_data = {
                    "statusCode": 500,
                    "body": {
                        "error": f"User deletion failed during Cognito operations: {str(cognito_error)}",
                        "user_id": user_id,
                        "details": "User has been restored to active status. Archive operations may need manual cleanup."
                    }
                }
                return response_data

        response_data = {
            "statusCode": 200,
            "body": {
                "message": "User deactivated successfully",
                "user_id": user_id,
                "active": 0,
                "deactivated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
                "cognito_deleted": True,
                "archived": True
            }
        }
        return response_data

    except HTTPException as http_error:
        # Re-raise HTTP exceptions and capture error details
        response_status = http_error.status_code
        error_message = str(http_error.detail)
        raise
    except Exception as e:
        # Record failed user deletion
        response_status = 500
        error_message = str(e)
        business_metrics.record_user_operation("delete", "error", user_id)
        
        # Safe rollback with connection state check
        if conn and is_connection_valid(conn):
            try:
                conn.rollback()
            except (pymysql.err.InterfaceError, pymysql.err.OperationalError) as rollback_error:
                # Log rollback error but don't raise it
                print(f"Rollback failed: {rollback_error}")
        raise HTTPException(status_code=500, detail={"error": str(e)})
        
    finally:
        # Calculate execution time
        execution_time_ms = int((time.time() - start_time) * 1000)
        
        # Log request details for monitoring using the utility function
        from endpoints.utility.log_request import log_request_from_endpoint
        log_request_from_endpoint(
            request=request,
            execution_time_ms=execution_time_ms,
            response_status=response_status,
            user_id=user_id,
            response_data=response_data,
            error_message=error_message
        )
        
        # Always close the connection
        if conn:
            close_db_connection(conn)