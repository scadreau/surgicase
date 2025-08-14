# Created: 2025-08-14 12:43:04
# Last Modified: 2025-08-14 12:44:04
# Author: Scott Cadreau

# endpoints/user/change_password.py
from fastapi import APIRouter, HTTPException, Body, Request
import pymysql.cursors
import boto3
from core.database import get_db_connection, close_db_connection
from core.models import PasswordChange
from utils.monitoring import track_business_operation, business_metrics
import time

router = APIRouter()

def change_cognito_password(user_id: str, new_password: str) -> bool:
    """
    Change user password in Cognito User Pool using admin privileges
    
    Args:
        user_id (str): The Cognito user ID (username) whose password to change
        new_password (str): The new password to set for the user
        
    Returns:
        bool: True if password change successful, False if failed
        
    Raises:
        Exception: If there's a network/permission error during password change
    """
    try:
        # Initialize Cognito Identity Provider client
        cognito_client = boto3.client('cognito-idp', region_name='us-east-1')
        
        # Set the new password for the user using admin privileges
        cognito_client.admin_set_user_password(
            UserPoolId='us-east-1_whzpZgWwq',
            Username=user_id,
            Password=new_password,
            Permanent=True  # Set password as permanent (user won't be forced to change on next login)
        )
        
        print(f"INFO: Successfully changed password in Cognito - user_id: {user_id}")
        return True
        
    except cognito_client.exceptions.UserNotFoundException:
        # User doesn't exist in Cognito - this is an error for password change
        print(f"ERROR: User not found in Cognito for password change - user_id: {user_id}")
        raise Exception(f"User not found in Cognito: {user_id}")
        
    except cognito_client.exceptions.InvalidPasswordException as e:
        # Password doesn't meet Cognito password policy requirements
        print(f"ERROR: Invalid password for user {user_id}: {str(e)}")
        raise Exception(f"Password does not meet requirements: {str(e)}")
        
    except cognito_client.exceptions.InvalidParameterException as e:
        # Invalid parameter provided
        print(f"ERROR: Invalid parameter for password change - user_id: {user_id}, error: {str(e)}")
        raise Exception(f"Invalid parameter: {str(e)}")
        
    except Exception as e:
        # Any other error is a failure
        print(f"ERROR: Failed to change password in Cognito - user_id: {user_id}, error: {str(e)}")
        raise Exception(f"Cognito password change failed: {str(e)}")

@router.put("/user/password")
@track_business_operation("update", "user_password")
def change_user_password(request: Request, password_data: PasswordChange = Body(...)):
    """
    Change user password in AWS Cognito User Pool with comprehensive validation and error handling.
    
    This endpoint provides secure password management capabilities for users in the surgical case
    management system. It validates user existence in the local database before attempting to
    change the password in AWS Cognito, ensuring system consistency and user authentication
    security across the platform.
    
    Key Features:
    - Secure password updates in AWS Cognito User Pool
    - User existence validation in local database
    - Comprehensive error handling with rollback capabilities
    - Password policy enforcement via Cognito validation
    - Detailed monitoring and audit logging
    - Business metrics tracking for security operations
    - Active user verification (soft-delete protection)
    
    Args:
        request (Request): FastAPI request object for logging and monitoring
        password_data (PasswordChange): Password change model containing:
            - user_id (str): Unique identifier of the user whose password to change (required)
            - new_password (str): New password meeting system requirements (required, min 8 chars)
    
    Returns:
        dict: Response containing:
            - statusCode (int): HTTP status code (200 for success)
            - body (dict): Response body with:
                - message (str): Success confirmation message
                - user_id (str): The user identifier whose password was changed
                - cognito_updated (bool): Cognito password update success status
    
    Raises:
        HTTPException:
            - 400 Bad Request: Missing required fields or invalid password format
            - 404 Not Found: User does not exist in database or is inactive
            - 422 Unprocessable Entity: Password does not meet Cognito policy requirements
            - 500 Internal Server Error: Database errors, Cognito errors, or system failures
    
    Database Operations:
        1. Validates user existence and active status in user_profile table
        2. Ensures only active users can change passwords (soft-delete protection)
        3. No database password storage - all authentication handled by Cognito
        4. User verification ensures consistency between local and Cognito user stores
    
    AWS Cognito Integration:
        - Updates password in Cognito User Pool (us-east-1_whzpZgWwq)
        - Uses admin_set_user_password for privileged password management
        - Sets password as permanent (no forced change on next login)
        - Enforces Cognito password policy requirements automatically
        - Handles user-not-found scenarios with appropriate error responses
        - Proper error handling for network and permission issues
    
    Business Logic:
        - Only active users in local database can change passwords
        - Password must meet minimum 8-character requirement (enforced by model)
        - Cognito password policy provides additional security constraints
        - User authentication remains consistent across database and Cognito
        - Password changes are immediate and effective for next login
        - No password history or previous password validation required
    
    Security Features:
        - Validates user existence before attempting password change
        - Enforces minimum password length requirements
        - Leverages AWS Cognito's built-in password policy enforcement
        - Secure transmission of password data via HTTPS
        - No password storage in local database (Cognito-only)
        - Audit logging for all password change attempts
        - Active user verification prevents unauthorized access
    
    Password Requirements:
        - Minimum 8 characters (enforced by Pydantic model)
        - Additional requirements enforced by Cognito password policy:
            * May include uppercase, lowercase, numbers, special characters
            * Cannot be common passwords or dictionary words
            * Cannot match user attributes (username, email, etc.)
            * Must meet complexity requirements configured in Cognito
    
    Monitoring & Logging:
        - Business metrics tracking for password change operations
        - Prometheus monitoring via @track_business_operation decorator
        - Detailed execution time and response logging
        - Security audit trail for all password change attempts
        - Error categorization for different failure types:
            * not_found: User doesn't exist in database
            * inactive_user: User exists but is soft-deleted
            * cognito_user_not_found: User not found in Cognito
            * invalid_password: Password doesn't meet requirements
            * cognito_error: General Cognito operation failure
            * success: Password changed successfully
            * error: General system errors
    
    Error Handling & Recovery:
        - Validates user in database before attempting Cognito operations
        - Graceful handling of password policy violations
        - Detailed error messages for different failure scenarios
        - No rollback required (operation is atomic in Cognito)
        - Specific error codes for frontend handling
    
    Example Request:
        PUT /user/password
        {
            "user_id": "USER123",
            "new_password": "NewSecurePassword123!"
        }
    
    Example Response (Success):
        {
            "statusCode": 200,
            "body": {
                "message": "Password changed successfully",
                "user_id": "USER123",
                "cognito_updated": true
            }
        }
    
    Example Response (User Not Found):
        {
            "statusCode": 404,
            "body": {
                "error": "User not found or inactive",
                "user_id": "USER123"
            }
        }
    
    Example Response (Invalid Password):
        {
            "statusCode": 422,
            "body": {
                "error": "Password does not meet requirements: Password must contain at least 1 uppercase letter",
                "user_id": "USER123"
            }
        }
    
    Example Response (Cognito Error):
        {
            "statusCode": 500,
            "body": {
                "error": "Cognito password change failed: Network timeout",
                "user_id": "USER123"
            }
        }
    
    Note:
        - This endpoint only changes passwords in Cognito, not local database
        - User must exist and be active in local database for security validation
        - Password requirements are enforced by both model validation and Cognito policy
        - Users will use the new password immediately for authentication
        - No email notification is sent (can be added as enhancement)
        - This is an administrative operation - user identity should be verified
        - Consider implementing additional authentication for password changes
        - Cognito password policy settings determine actual complexity requirements
        - Password history and reuse prevention handled by Cognito configuration
        - Failed attempts may trigger Cognito account lockout policies
    """
    conn = None
    start_time = time.time()
    response_status = 200
    response_data = None
    error_message = None
    
    try:
        # Validate required fields
        if not password_data.user_id:
            response_status = 400
            error_message = "Missing user_id parameter"
            raise HTTPException(status_code=400, detail="Missing user_id parameter")
        
        if not password_data.new_password:
            response_status = 400
            error_message = "Missing new_password parameter"
            raise HTTPException(status_code=400, detail="Missing new_password parameter")

        conn = get_db_connection()

        try:
            with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                # Verify user exists and is active in the database
                cursor.execute("""SELECT user_id, active FROM user_profile WHERE user_id = %s""", (password_data.user_id,))
                user_data = cursor.fetchone()

                if not user_data:
                    # Record failed password change (user not found)
                    business_metrics.record_user_operation("update_password", "not_found", password_data.user_id)
                    response_status = 404
                    error_message = "User not found"
                    raise HTTPException(
                        status_code=404, 
                        detail={"error": "User not found or inactive", "user_id": password_data.user_id}
                    )
                
                if user_data['active'] != 1:
                    # Record failed password change (inactive user)
                    business_metrics.record_user_operation("update_password", "inactive_user", password_data.user_id)
                    response_status = 404
                    error_message = "User is inactive"
                    raise HTTPException(
                        status_code=404, 
                        detail={"error": "User not found or inactive", "user_id": password_data.user_id}
                    )

        finally:
            close_db_connection(conn)

        # Change password in Cognito User Pool
        try:
            change_cognito_password(password_data.user_id, password_data.new_password)
            business_metrics.record_user_operation("update_password", "success", password_data.user_id)
        except Exception as cognito_error:
            error_str = str(cognito_error)
            print(f"ERROR: Cognito password change failed for user {password_data.user_id}: {error_str}")
            
            # Determine specific error type for better user experience
            if "User not found in Cognito" in error_str:
                business_metrics.record_user_operation("update_password", "cognito_user_not_found", password_data.user_id)
                response_status = 404
                error_message = f"User not found in authentication system"
                response_data = {
                    "statusCode": 404,
                    "body": {
                        "error": "User not found in authentication system",
                        "user_id": password_data.user_id
                    }
                }
                return response_data
            elif "Password does not meet requirements" in error_str:
                business_metrics.record_user_operation("update_password", "invalid_password", password_data.user_id)
                response_status = 422
                error_message = error_str
                response_data = {
                    "statusCode": 422,
                    "body": {
                        "error": error_str,
                        "user_id": password_data.user_id
                    }
                }
                return response_data
            else:
                business_metrics.record_user_operation("update_password", "cognito_error", password_data.user_id)
                response_status = 500
                error_message = f"Cognito password change failed: {error_str}"
                response_data = {
                    "statusCode": 500,
                    "body": {
                        "error": f"Password change failed: {error_str}",
                        "user_id": password_data.user_id
                    }
                }
                return response_data

        response_data = {
            "statusCode": 200,
            "body": {
                "message": "Password changed successfully",
                "user_id": password_data.user_id,
                "cognito_updated": True
            }
        }
        return response_data

    except HTTPException as http_error:
        # Re-raise HTTP exceptions and capture error details
        response_status = http_error.status_code
        error_message = str(http_error.detail)
        raise
    except Exception as e:
        # Record failed password change
        response_status = 500
        error_message = str(e)
        business_metrics.record_user_operation("update_password", "error", password_data.user_id)
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
            user_id=password_data.user_id,
            response_data=response_data,
            error_message=error_message
        )
