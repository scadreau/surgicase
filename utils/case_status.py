# Created: 2025-07-15 23:02:51
# Last Modified: 2025-10-18 17:19:45
# Author: Scott Cadreau

# utils/case_status.py
import pymysql.cursors
from datetime import date

def update_case_status(case_id: str, conn) -> dict:
    """
    Update case status from 0 to 7 or 10 based on completeness, patient age, and billing eligibility:
    
    Important: If case status is already > 10, no changes are made (preserves workflow progress)
    
    Conditions for status update:
    - demo_file is not null
    - note_file is not null  
    - at least 1 procedure code exists
    
    Status determination:
    - No change: Case status > 10 (case has progressed beyond initial review)
    - Status 7: All conditions met AND patient is >= 65 years old (needs insurance confirmation)
    - Status 10: All conditions met AND patient < 65 (or DOB is NULL) AND at least one procedure has asst_surg = 2 (billable)
    - Status 7: All conditions met AND patient < 65 (or DOB is NULL) BUT no procedures have asst_surg = 2 (needs review)
    - Status 0: Conditions not met (remains incomplete)
    
    Args:
        case_id: The case ID to update
        conn: PyMySQL connection object
        
    Returns:
        dict: Status of the update operation including:
            - success (bool): Whether the update was successful
            - message (str): Description of the result
            - case_id (str): The case ID processed
            - case_status (int): Final status (7 or 10 if successful)
            - procedure_count (int): Number of procedure codes found
            - billable_procedures (int): Number of procedures with asst_surg = 2
            - patient_age (int, optional): Patient's age if DOB available
    """
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            # Check if case exists and get current status with patient DOB
            cursor.execute("""
                SELECT case_id, case_status, demo_file, note_file, patient_dob 
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
            
            # Check if case status is already greater than 10 (don't revert progress)
            if case_data["case_status"] > 10:
                return {
                    "success": True,
                    "message": f"Case status is {case_data['case_status']} (>10), no status change made",
                    "case_id": case_id,
                    "case_status": case_data["case_status"]
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
            
            # Check if patient is 65 or older
            patient_age = None
            is_senior = False
            
            if case_data["patient_dob"]:
                # Calculate patient age based on DOB
                today = date.today()
                birth_date = case_data["patient_dob"]
                patient_age = today.year - birth_date.year - ((today.month, today.day) < (birth_date.month, birth_date.day))
                is_senior = patient_age >= 65
            
            # Determine final status based on patient age and assistant surgeon billing eligibility
            if is_senior:
                # Patient is 65 or older - needs manual insurance confirmation
                final_status = 7
                status_message = f"Case status updated successfully to 7 (patient age {patient_age} >= 65, needs insurance confirmation)"
            else:
                # Patient is under 65 or DOB is NULL - use billable procedure logic
                cursor.execute("""
                    SELECT COUNT(*) as billable_count 
                    FROM case_procedure_codes 
                    WHERE case_id = %s AND asst_surg = 2
                """, (case_id,))
                billable_count = cursor.fetchone()["billable_count"]
                
                if billable_count > 0:
                    # At least one billable assistant surgeon procedure - ready for submission
                    final_status = 10
                    status_message = "Case status updated successfully from 0 to 10 (ready for submission)"
                else:
                    # No billable assistant surgeon procedures - needs review
                    final_status = 7
                    status_message = "Case status updated successfully from 0 to 7 (complete but needs review - no billable assistant surgeon procedures)"
            
            # All conditions met, update case status
            cursor.execute("""
                UPDATE cases 
                SET case_status = %s 
                WHERE case_id = %s AND active = 1
            """, (final_status, case_id))
            
            if cursor.rowcount == 0:
                return {
                    "success": False,
                    "message": "Failed to update case status",
                    "case_id": case_id
                }
            
            # Build response with optional fields
            response = {
                "success": True,
                "message": status_message,
                "case_id": case_id,
                "case_status": final_status,
                "procedure_count": procedure_count
            }
            
            # Add patient age if available
            if patient_age is not None:
                response["patient_age"] = patient_age
            
            # Add billable procedures count if not senior (since we only check it for non-seniors)
            if not is_senior:
                response["billable_procedures"] = billable_count
            
            # Note: No commit here - the calling function will handle the transaction
            return response
            
    except Exception as e:
        # Don't rollback here - let the calling function handle transaction management
        return {
            "success": False,
            "message": f"Error updating case status: {str(e)}",
            "case_id": case_id
        }