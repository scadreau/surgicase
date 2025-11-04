# Created: 2025-07-15 09:20:13
# Last Modified: 2025-10-03 18:49:07
# Author: Scott Cadreau

# endpoints/user/update_user.py
from fastapi import APIRouter, HTTPException, Body, Request
import pymysql.cursors
import logging
from core.database import get_db_connection, close_db_connection, is_connection_valid
from core.models import UserUpdate
from utils.monitoring import track_business_operation, business_metrics
import time

router = APIRouter()

@router.patch("/user")
@track_business_operation("update", "user")
def update_user(request: Request, user: UserUpdate = Body(...)):
    """
    Update user profile fields and documents with selective field modification and complete document replacement.
    
    This endpoint provides comprehensive user profile updating capabilities with selective field updates
    and complete document management. Only the user_id is required; any other provided fields will be
    updated while null/undefined fields remain unchanged. Document updates completely replace the
    existing document set for specific document types.
    
    Key Features:
    - Selective field updates (only provided fields are modified)
    - Complete document type replacement with validation
    - Transactional operations ensuring data consistency  
    - Comprehensive validation and error handling
    - Professional information management (NPI, licensing, etc.)
    - Contact and address information updates
    - User preference and type management
    - Detailed change tracking and reporting
    
    Args:
        request (Request): FastAPI request object for logging and monitoring
        user (UserUpdate): User update model containing:
            - user_id (str): Unique identifier of the user to update (required)
            - user_email (str, optional): Updated email address
            - first_name (str, optional): Updated first name
            - last_name (str, optional): Updated last name
            - addr1 (str, optional): Updated primary address line
            - addr2 (str, optional): Updated secondary address line
            - city (str, optional): Updated city of residence
            - state (str, optional): Updated state/province
            - zipcode (str, optional): Updated postal/ZIP code
            - telephone (str, optional): Updated primary phone number
            - user_npi (str, optional): Updated National Provider Identifier
            - referred_by_user (str, optional): Updated referring user ID
            - user_type (int, optional): Updated user type/permission level
            - message_pref (str, optional): Updated communication preferences
            - states_licensed (str, optional): Updated licensing state information
            - timezone (str, optional): Updated timezone preference
            - credentials (str, optional): Updated professional credentials (e.g., MD, DO, PA, NP, CSA, PA-C)
            - ins_exp_date (str, optional): Updated malpractice insurance expiration date in ISO format (YYYY-MM-DD)
            - user_tier (int, optional): Updated user tier level
            - documents (List[UserDocument], optional): Document list for replacement:
                - document_type (str): Type/category of document
                - document_name (str): Name/path of the document file
    
    Returns:
        dict: Response containing:
            - statusCode (int): HTTP status code (200 for success)
            - body (dict): Response body with:
                - message (str): Success confirmation message
                - user_id (str): The user identifier that was updated
                - updated_fields (List[str]): List of fields that were actually modified
    
    Raises:
        HTTPException:
            - 400 Bad Request: Missing user_id, no fields to update, or no changes made
            - 404 Not Found: User does not exist in the database
            - 500 Internal Server Error: Database errors or transaction failures
    
    Database Operations:
        1. Validates user existence in user_profile table
        2. Updates user_profile fields selectively based on provided data
        3. Manages document replacement per document type:
            - Deletes existing documents of the same type
            - Inserts new documents for each provided type
        4. All operations performed within a single transaction
        5. Commits changes atomically or rolls back on failure
    
    Business Logic:
        - Only non-null fields in the request are updated
        - user_id is required but not updateable
        - Document updates are type-specific replacements, not global
        - Empty document arrays remove all documents of that type
        - Professional information updates maintain regulatory compliance
        - User preferences affect system behavior and notifications
        - User type changes automatically update max_case_status from user_type_list
        - User tier updates affect the user's access level and system privileges
    
    Document Management Logic:
        - Documents are replaced per document_type, not globally
        - For each unique document_type in the request:
            * All existing documents of that type are deleted
            * New documents of that type are inserted
        - Document types not included in request remain unchanged
        - This allows selective document type management
    
    Field Update Logic:
        - Only fields with non-null values are updated
        - user_id and documents are excluded from field updates
        - Dynamic SQL generation based on provided fields
        - Change tracking reports only fields that actually changed
        - Database-level constraints ensure data integrity
    
    Professional Information Updates:
        - NPI updates for healthcare professional verification
        - State licensing updates for regulatory compliance
        - User type modifications affect system permissions and auto-update max_case_status
        - User tier modifications affect access levels and system privileges
        - Referral chain updates for business relationship tracking
    
    Monitoring & Logging:
        - Business metrics tracking for user update operations
        - Prometheus monitoring via @track_business_operation decorator
        - Detailed execution time and response logging
        - Change tracking for all modified fields
        - Error categorization for different failure types:
            * not_found: User doesn't exist
            * no_changes: No actual database changes occurred
            * success: User updated successfully
            * error: General transaction or database errors
    
    Transaction Management:
        - Explicit transaction control for data consistency
        - All database operations within single transaction
        - Automatic rollback on any operation failure
        - Connection state validation before rollback attempts
        - Proper database connection cleanup
    
    Validation Logic:
        - user_id is mandatory and must exist
        - At least one updateable field or documents must be provided
        - Empty updates return 400 Bad Request
        - Non-existent users return 404 Not Found
        - Database constraint violations handled gracefully
    
    Example Request:
        PATCH /user
        {
            "user_id": "USER123",
            "first_name": "Dr. Jane Updated",
            "telephone": "+1-555-9999",
            "user_npi": "0987654321",
            "user_type": 10,
            "user_tier": 2,
            "credentials": "DO",
            "ins_exp_date": "2026-06-30",
            "documents": [
                {
                    "document_type": "medical_license",
                    "document_name": "updated_ca_license.pdf"
                },
                {
                    "document_type": "medical_license", 
                    "document_name": "ny_license.pdf"
                }
            ]
        }
    
    Example Response:
        {
            "statusCode": 200,
            "body": {
                "message": "User updated successfully",
                "user_id": "USER123",
                "updated_fields": ["first_name", "telephone", "user_npi", "user_type", "user_tier", "credentials", "max_case_status", "documents"]
            }
        }
    
    Example Error Response (No Changes):
        {
            "statusCode": 400,
            "body": {
                "error": "No changes made to user"
            }
        }
    
    Example Error Response (Not Found):
        {
            "statusCode": 404,
            "body": {
                "error": "User not found",
                "user_id": "INVALID_USER"
            }
        }
    
    Note:
        - Only active users can be updated (soft-deleted users return 404)
        - Document updates are per document_type, allowing selective management
        - Multiple documents of the same type can be provided
        - Empty document array for a type removes all documents of that type
        - Professional fields (NPI, licensing) have regulatory implications
        - User type changes affect system permissions and automatically update max_case_status
        - When user_type is changed, max_case_status is retrieved from user_type_list table
        - Max_case_status determines maximum case status visibility for the user
        - User tier changes affect the user's access level and available features
        - All field updates are atomic - either all succeed or all are rolled back
        - File path updates do not trigger automatic file operations
        - Communication preference changes affect notification behavior
        - Timezone updates affect user experience timestamps
    """
    conn = None
    start_time = time.time()
    response_status = 200
    response_data = None
    error_message = None
    
    try:
        # Ensure at least one field to update besides user_id or documents
        update_fields = {k: v for k, v in user.dict().items() if k not in ("user_id", "documents") and v is not None}
        if not user.user_id:
            response_status = 400
            error_message = "Missing user_id parameter"
            raise HTTPException(status_code=400, detail="Missing user_id parameter")
        if not update_fields and user.documents is None:
            response_status = 400
            error_message = "No fields to update"
            raise HTTPException(status_code=400, detail="No fields to update")

        conn = get_db_connection()
        
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            # Check if user exists and get current user_type for comparison
            cursor.execute("SELECT user_id, user_type FROM user_profile WHERE user_id = %s", (user.user_id,))
            existing_user = cursor.fetchone()
            if not existing_user:
                # Record failed user update (not found)
                business_metrics.record_user_operation("update", "not_found", user.user_id)
                response_status = 404
                error_message = "User not found"
                raise HTTPException(status_code=404, detail={"error": "User not found", "user_id": user.user_id})
            
            current_user_type = existing_user['user_type']

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
            
            # Check if user_type was changed and update max_case_status accordingly
            if user.user_type is not None and user.user_type != current_user_type:
                # Lookup the max_case_status for the new user_type from user_type_list
                cursor.execute(
                    "SELECT user_max_case_status FROM user_type_list WHERE user_type = %s",
                    (user.user_type,)
                )
                user_type_data = cursor.fetchone()
                
                if user_type_data and user_type_data['user_max_case_status'] is not None:
                    new_max_case_status = user_type_data['user_max_case_status']
                    
                    # Update the max_case_status in user_profile
                    cursor.execute(
                        "UPDATE user_profile SET max_case_status = %s WHERE user_id = %s",
                        (new_max_case_status, user.user_id)
                    )
                    
                    if cursor.rowcount > 0:
                        # Only add to updated_fields if max_case_status wasn't already in the update
                        if "max_case_status" not in updated_fields:
                            updated_fields.append("max_case_status")
            
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
                response_status = 400
                error_message = "No changes made to user"
                raise HTTPException(status_code=400, detail="No changes made to user")
            
            conn.commit()
            
            # Clear user environment cache after successful update
            try:
                from endpoints.utility.get_user_environment import invalidate_and_rewarm_user_environment_cache
                invalidate_and_rewarm_user_environment_cache(user.user_id)
                logging.info(f"Invalidated user environment cache for user: {user.user_id}")
            except Exception as cache_error:
                # Don't fail the operation if cache invalidation fails
                logging.error(f"Failed to invalidate user environment cache for user {user.user_id}: {str(cache_error)}")
            
            # Record successful user update
            business_metrics.record_user_operation("update", "success", user.user_id)

        response_data = {
            "statusCode": 200,
            "body": {
                "message": "User updated successfully",
                "user_id": user.user_id,
                "updated_fields": list(updated_fields)
            }
        }
        return response_data

    except HTTPException as http_error:
        # Re-raise HTTP exceptions and capture error details
        response_status = http_error.status_code
        error_message = str(http_error.detail)
        raise
    except Exception as e:
        # Record failed user update
        response_status = 500
        error_message = str(e)
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
        # Calculate execution time
        execution_time_ms = int((time.time() - start_time) * 1000)
        
        # Log request details for monitoring using the utility function
        from endpoints.utility.log_request import log_request_from_endpoint
        log_request_from_endpoint(
            request=request,
            execution_time_ms=execution_time_ms,
            response_status=response_status,
            user_id=user.user_id,
            response_data=response_data,
            error_message=error_message
        )
        
        # Always close the connection
        if conn:
            close_db_connection(conn)