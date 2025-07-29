# Created: 2025-07-15 23:02:51
# Last Modified: 2025-07-29 01:51:02
# utils/case_status.py
import pymysql.cursors

def update_case_status(case_id: str, conn) -> dict:
    """
    Update case status from 0 to 1 if conditions are met:
    - demo_file is not null
    - note_file is not null  
    - at least 1 procedure code exists
    
    Args:
        case_id: The case ID to update
        conn: PyMySQL connection object
        
    Returns:
        dict: Status of the update operation
    """
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            # Check if case exists and get current status
            cursor.execute("""
                SELECT case_id, case_status, demo_file, note_file 
                FROM cases 
                WHERE case_id = %s AND active = 1
            """, (case_id,))
            case_data = cursor.fetchone()
            
            if not case_data:
                return {
                    "success": False,
                    "message": "Case not found or inactive",
                    "case_id": case_id
                }
            
            # Check if case status is already 1
            if case_data["case_status"] == 10:
                return {
                    "success": True,
                    "message": "Case status already updated to 10",
                    "case_id": case_id,
                    "case_status": 1
                }
            
            # Check if demo_file and note_file are not null
            if not case_data["demo_file"] or not case_data["note_file"]:
                return {
                    "success": False,
                    "message": "demo_file and note_file must not be null",
                    "case_id": case_id,
                    "demo_file": case_data["demo_file"],
                    "note_file": case_data["note_file"]
                }
            
            # Check if at least one procedure code exists
            cursor.execute("""
                SELECT COUNT(*) as code_count 
                FROM case_procedure_codes 
                WHERE case_id = %s
            """, (case_id,))
            procedure_count = cursor.fetchone()["code_count"]
            
            if procedure_count == 0:
                return {
                    "success": False,
                    "message": "At least one procedure code is required",
                    "case_id": case_id,
                    "procedure_count": procedure_count
                }
            
            # All conditions met, update case status to 1
            cursor.execute("""
                UPDATE cases 
                SET case_status = 10 
                WHERE case_id = %s AND active = 1
            """, (case_id,))
            
            if cursor.rowcount == 0:
                return {
                    "success": False,
                    "message": "Failed to update case status",
                    "case_id": case_id
                }
            
            # Note: No commit here - the calling function will handle the transaction
            return {
                "success": True,
                "message": "Case status updated successfully from 0 to 10",
                "case_id": case_id,
                "case_status": 10,
                "procedure_count": procedure_count
            }
            
    except Exception as e:
        # Don't rollback here - let the calling function handle transaction management
        return {
            "success": False,
            "message": f"Error updating case status: {str(e)}",
            "case_id": case_id
        }