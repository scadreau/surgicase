# Created: 2025-07-15 20:17:09
# Last Modified: 2025-07-22 17:37:15

# utils/archive_deleted_case.py

import threading
import pymysql
import pymysql.cursors
import logging
from core.database import get_db_connection, close_db_connection

logger = logging.getLogger(__name__)

def archive_deleted_case(case_id: str):
    def worker():
        conn = None
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
                    logger.info(f"archived_case_success - case_id: {case_id}")
                else:
                    logger.warning(f"archived_case_not_found_or_active - case_id: {case_id}")

        except Exception as e:
            if conn:
                conn.rollback()
                logger.error(f"archive_case_failed_rolled_back - case_id: {case_id}, error: {str(e)}")
            else:
                logger.error(f"archive_case_failed - case_id: {case_id}, error: {str(e)}")
        finally:
            if conn:
                close_db_connection(conn)

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()