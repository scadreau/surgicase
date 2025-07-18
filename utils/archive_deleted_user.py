# Created: 2025-07-15 20:26:30
# Last Modified: 2025-07-16 12:18:32

# utils/archive_deleted_user.py

import threading
import pymysql
import pymysql.cursors
import logging
from core.database import get_db_connection, close_db_connection

logger = logging.getLogger(__name__)

def archive_deleted_user(user_id: str):
    def worker():
        conn = None
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
                    # Archive the user
                    cursor.execute("""
                        INSERT INTO deleted_users (
                            user_id, user_email, first_name, last_name, addr1, addr2,
                            city, state, zipcode, telephone, user_npi, referred_by_user,
                            user_type, message_pref, create_ts, last_login_dt, active, states_licensed, last_updated_ts, user_tier
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """, (
                        user["user_id"], user["user_email"], user["first_name"], user["last_name"],
                        user["addr1"], user["addr2"], user["city"], user["state"], user["zipcode"],
                        user["telephone"], user["user_npi"], user["referred_by_user"], user["user_type"],
                        user["message_pref"], user.get("create_ts"), user.get("last_login_dt"), user.get("active"), 
                        user["states_licensed"], user.get("last_updated_ts"), user["user_tier"]
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
                    logger.info(f"archived_user_success - user_id: {user_id}")
                else:
                    logger.warning(f"archived_user_not_found_or_active - user_id: {user_id}")

        except Exception as e:
            if conn:
                conn.rollback()
                logger.error(f"archive_user_failed_rolled_back - user_id: {user_id}, error: {str(e)}")
            else:
                logger.error(f"archive_user_failed - user_id: {user_id}, error: {str(e)}")
        finally:
            if conn:
                close_db_connection(conn)

    thread = threading.Thread(target=worker, daemon=True)
    thread.start() 