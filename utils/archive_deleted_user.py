# Created: 2025-07-15 20:26:30
# Last Modified: 2025-07-23 09:41:51

# utils/archive_deleted_user.py

import pymysql
import pymysql.cursors
import logging
from core.database import get_db_connection, close_db_connection
from utils.s3_user_files import move_user_documents_to_deleted

logger = logging.getLogger(__name__)

def archive_deleted_user(user_id: str):
    conn = None
    s3_move_result = None
    try:
        conn = get_db_connection()
        # Start transaction
        conn.begin()
        
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute(
                "SELECT * FROM user_profile WHERE user_id = %s AND active = 0",
                (user_id,)
            )
            user = cursor.fetchone()

            if user:
                # Get user documents for S3 operations
                cursor.execute("""
                    SELECT document_type, document_name 
                    FROM user_documents 
                    WHERE user_id = %s
                """, (user_id,))
                user_documents = [(row['document_type'], row['document_name']) for row in cursor.fetchall()]
                
                # Move S3 user documents before database archiving
                logger.info(f"Starting S3 user document movement for user {user_id}")
                s3_move_result = move_user_documents_to_deleted(
                    user_id=user_id,
                    user_documents=user_documents
                )
                
                # Check if S3 file movement was successful
                if not s3_move_result["success"]:
                    error_msg = f"S3 user document movement failed for user {user_id}: {s3_move_result['message']}"
                    if s3_move_result["errors"]:
                        error_msg += f" Errors: {'; '.join(s3_move_result['errors'])}"
                    logger.error(error_msg)
                    raise Exception(error_msg)
                
                logger.info(f"S3 user documents moved successfully for user {user_id}: {s3_move_result['files_moved']} files")
                # Archive the user
                cursor.execute("""
                    INSERT INTO deleted_users (
                        user_id, user_email, first_name, last_name, addr1, addr2,
                        city, state, zipcode, telephone, user_npi, referred_by_user,
                        user_type, message_pref, create_ts, last_login_dt, active, states_licensed, last_updated_ts, user_tier, max_case_status
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    user["user_id"], user["user_email"], user["first_name"], user["last_name"],
                    user["addr1"], user["addr2"], user["city"], user["state"], user["zipcode"],
                    user["telephone"], user["user_npi"], user["referred_by_user"], user["user_type"],
                    user["message_pref"], user.get("create_ts"), user.get("last_login_dt"), user.get("active"), 
                    user["states_licensed"], user.get("last_updated_ts"), user["user_tier"], user.get("max_case_status")
                ))
                
                # Archive associated user documents
                cursor.execute("""
                    INSERT INTO deleted_user_documents 
                    SELECT *
                    FROM user_documents 
                    WHERE user_id = %s
                """, (user_id,))
                
                # Archive associated surgeons
                cursor.execute("""
                    INSERT INTO deleted_surgeons 
                    SELECT *
                    FROM surgeon_list 
                    WHERE user_id = %s
                """, (user_id,))
                
                # Archive associated facilities
                cursor.execute("""
                    INSERT INTO deleted_facilities 
                    SELECT *
                    FROM facility_list 
                    WHERE user_id = %s
                """, (user_id,))
                
                # Archive associated cases
                cursor.execute("""INSERT INTO deleted_cases 
                    SELECT * 
                    FROM cases 
                    WHERE user_id = %s
                    """, (user_id,))
                
                # Archive associated case procedure codes
                cursor.execute("""
                    INSERT INTO deleted_case_procedure_codes (
                        case_id, procedure_code
                    ) 
                    SELECT cpc.case_id, cpc.procedure_code
                    FROM case_procedure_codes cpc
                    INNER JOIN cases c ON cpc.case_id = c.case_id
                    WHERE c.user_id = %s
                """, (user_id,))
                
                # Delete the original user documents
                cursor.execute("""
                    DELETE FROM user_documents 
                    WHERE user_id = %s
                """, (user_id,))
                
                # Delete the original surgeons
                cursor.execute("""
                    DELETE FROM surgeon_list 
                    WHERE user_id = %s
                """, (user_id,))
                
                # Delete the original facilities
                cursor.execute("""
                    DELETE FROM facility_list 
                    WHERE user_id = %s
                """, (user_id,))
                
                # Delete the original case procedure codes
                cursor.execute("""
                    DELETE cpc FROM case_procedure_codes cpc
                    INNER JOIN cases c ON cpc.case_id = c.case_id
                    WHERE c.user_id = %s
                """, (user_id,))
                
                # Delete the original cases
                cursor.execute("""
                    DELETE FROM cases 
                    WHERE user_id = %s
                """, (user_id,))
                
                # Delete the original user
                cursor.execute("""
                    DELETE FROM user_profile 
                    WHERE user_id = %s
                """, (user_id,))
                
                conn.commit()
                logger.info(f"archived_user_success - user_id: {user_id}, s3_files_moved: {s3_move_result['files_moved']}")
            else:
                logger.warning(f"archived_user_not_found_or_active - user_id: {user_id}")

    except Exception as e:
        if conn:
            conn.rollback()
            logger.error(f"archive_user_failed_rolled_back - user_id: {user_id}, error: {str(e)}")
            
            # Log S3 movement details if available
            if s3_move_result:
                logger.error(f"S3 user document movement result: {s3_move_result}")
        else:
            logger.error(f"archive_user_failed - user_id: {user_id}, error: {str(e)}")
        
        # Re-raise the exception so delete_user can handle the failure
        raise e
    finally:
        if conn:
            close_db_connection(conn) 