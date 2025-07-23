# Created: 2025-07-15 20:17:09
# Last Modified: 2025-07-23 09:41:58

# utils/archive_deleted_case.py

import pymysql
import pymysql.cursors
import logging
from core.database import get_db_connection, close_db_connection
from utils.s3_case_files import move_case_files_to_deleted

logger = logging.getLogger(__name__)

def archive_deleted_case(case_id: str):
    conn = None
    s3_move_result = None
    try:
        conn = get_db_connection()
        # Start transaction
        conn.begin()
        
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute(
                "SELECT * FROM cases WHERE case_id = %s AND active = 0",
                (case_id,)
            )
            case = cursor.fetchone()

            if case:
                # Extract file information and user_id for S3 operations
                user_id = case.get('user_id')
                demo_file = case.get('demo_file')
                note_file = case.get('note_file')
                misc_file = case.get('misc_file')
                
                # Move S3 files before database archiving
                logger.info(f"Starting S3 file movement for case {case_id}")
                s3_move_result = move_case_files_to_deleted(
                    case_id=case_id,
                    user_id=user_id,
                    demo_file=demo_file,
                    note_file=note_file,
                    misc_file=misc_file
                )
                
                # Check if S3 file movement was successful
                if not s3_move_result["success"]:
                    error_msg = f"S3 file movement failed for case {case_id}: {s3_move_result['message']}"
                    if s3_move_result["errors"]:
                        error_msg += f" Errors: {'; '.join(s3_move_result['errors'])}"
                    logger.error(error_msg)
                    raise Exception(error_msg)
                
                logger.info(f"S3 files moved successfully for case {case_id}: {s3_move_result['files_moved']} files")
                
                # Archive the case
                cursor.execute("""
                    INSERT INTO deleted_cases 
                    SELECT *
                    FROM cases
                    WHERE case_id = %s
                """, (case_id,))
                
                # Archive associated procedure codes
                cursor.execute("""
                    INSERT INTO deleted_case_procedure_codes 
                    SELECT *
                    FROM case_procedure_codes 
                    WHERE case_id = %s
                """, (case_id,))
                
                # Delete the original procedure codes
                cursor.execute("""
                    DELETE FROM case_procedure_codes 
                    WHERE case_id = %s
                """, (case_id,))
                
                # Delete the original case
                cursor.execute("""
                    DELETE FROM cases 
                    WHERE case_id = %s
                """, (case_id,))
                
                conn.commit()
                logger.info(f"archived_case_success - case_id: {case_id}, s3_files_moved: {s3_move_result['files_moved']}")
            else:
                logger.warning(f"archived_case_not_found_or_active - case_id: {case_id}")

    except Exception as e:
        if conn:
            conn.rollback()
            logger.error(f"archive_case_failed_rolled_back - case_id: {case_id}, error: {str(e)}")
            
            # Log S3 movement details if available
            if s3_move_result:
                logger.error(f"S3 movement result: {s3_move_result}")
        else:
            logger.error(f"archive_case_failed - case_id: {case_id}, error: {str(e)}")
        
        # Re-raise the exception so delete_case can handle the failure
        raise e
    finally:
        if conn:
            close_db_connection(conn)