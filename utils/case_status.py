# Created: 2025-07-15 23:02:51
# Last Modified: 2025-11-04 19:47:00
# Author: Scott Cadreau

# utils/case_status.py
import pymysql.cursors
import logging
from datetime import date, datetime
from utils.status_timestamps import build_status_update_query

logger = logging.getLogger(__name__)

def update_case_status(case_id: str, conn) -> dict:
    """
    Update case status from 0 to 7, 10, or 400 based on completeness, patient age, billing eligibility, procedure codes, and insurance provider.
    Automatically updates corresponding timestamp fields when setting status (billable_flag_ts, submitted_ts, rejected_ts).
    
    Status Update Priority (evaluated in this order):
    1. No change: Case status > 10 (case has progressed beyond initial review - preserves workflow progress)
    2. Status 400: ALL procedure codes are in range [10004-11960] (REJECTED - highest priority for active cases)
    3. Status 400: Humana detected in insurance (REJECTED - Humana only covers Medicare/Medicaid)
    4. Status 7: Medicare detected in insurance (overrides other conditions except rejected codes)
    5. Normal logic: Status determined by completeness, patient age, and billability
    
    Conditions for normal status update:
    - demo_file is not null
    - note_file is not null  
    - at least 1 procedure code exists
    
    Normal status determination:
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
            - case_status (int): Final status (7, 10, or 400)
            - procedure_count (int): Number of procedure codes found
            - billable_procedures (int): Number of procedures with asst_surg = 2
            - patient_age (int, optional): Patient's age if DOB available
            - override_reason (str, optional): "medicare", "procedure_codes_rejected", or "humana_insurance_rejected" if override was applied
    """
    try:
        logger.info(f"update_case_status called for case_id: {case_id}")
        
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            # Check if case exists and get current status with patient DOB, insurance, and user_id for decryption
            cursor.execute("""
                SELECT case_id, case_status, demo_file, note_file, patient_dob, ins_provider, user_id, phi_encrypted 
                FROM cases 
                WHERE case_id = %s AND active = 1
            """, (case_id,))
            case_data = cursor.fetchone()
            
            if not case_data:
                logger.warning(f"Case {case_id} not found or inactive")
                return {
                    "success": False,
                    "message": "Case not found or inactive",
                    "case_id": case_id
                }
            
            # Decrypt ins_provider if PHI is encrypted
            if case_data.get('phi_encrypted') == 1 and case_data.get('ins_provider'):
                try:
                    from utils.phi_encryption import PHIEncryption, get_user_dek
                    
                    user_id = case_data.get('user_id')
                    if user_id:
                        dek = get_user_dek(user_id, conn)
                        phi_crypto = PHIEncryption()
                        
                        # Decrypt ins_provider field if it looks encrypted (>= 28 chars)
                        ins_provider_value = str(case_data['ins_provider'])
                        if len(ins_provider_value) >= 28:
                            try:
                                case_data['ins_provider'] = phi_crypto.decrypt_field(case_data['ins_provider'], dek)
                                logger.debug(f"Case {case_id}: Decrypted ins_provider for status check")
                            except Exception as decrypt_error:
                                logger.warning(f"Case {case_id}: Could not decrypt ins_provider, using encrypted value: {str(decrypt_error)}")
                except Exception as e:
                    logger.warning(f"Case {case_id}: Error during ins_provider decryption setup: {str(e)}")
            
            # Check if case status is already greater than 10 (don't revert progress)
            if case_data["case_status"] > 10:
                logger.info(f"Case {case_id} status is {case_data['case_status']} (>10), no change made")
                return {
                    "success": True,
                    "message": f"Case status is {case_data['case_status']} (>10), no status change made",
                    "case_id": case_id,
                    "case_status": case_data["case_status"]
                }
            
            # Check if all procedure codes are in the rejected range [10004-11960]
            cursor.execute("""
                SELECT procedure_code 
                FROM case_procedure_codes 
                WHERE case_id = %s
            """, (case_id,))
            procedure_codes = cursor.fetchall()
            
            if procedure_codes:  # Only check if there are procedure codes
                all_in_rejected_range = True
                for proc in procedure_codes:
                    code = proc["procedure_code"]
                    try:
                        # Convert to integer for comparison
                        code_int = int(code)
                        if not (10004 <= code_int <= 11960):
                            all_in_rejected_range = False
                            break
                    except (ValueError, TypeError):
                        # If code can't be converted to int, it's not in the range
                        all_in_rejected_range = False
                        break
                
                # If all codes are in rejected range, set status to 400
                if all_in_rejected_range:
                    logger.info(f"Case {case_id}: All procedure codes in rejected range, setting status to 400")
                    update_query, has_timestamp = build_status_update_query(400)
                    cursor.execute(update_query, (400, case_id))
                    
                    return {
                        "success": True,
                        "message": "Case status set to 400 (all procedure codes in rejected range 10004-11960)",
                        "case_id": case_id,
                        "case_status": 400,
                        "override_reason": "procedure_codes_rejected",
                        "procedure_count": len(procedure_codes)
                    }
            
            # Check if Humana is in insurance - if so, set case_status to 400 (rejected)
            # Humana has moved to only Medicare and Medicaid which client cannot file against
            if case_data.get("ins_provider") and "humana" in case_data["ins_provider"].lower():
                logger.info(f"Case {case_id}: Humana detected in insurance, setting status to 400")
                update_query, has_timestamp = build_status_update_query(400)
                cursor.execute(update_query, (400, case_id))
                
                return {
                    "success": True,
                    "message": "Case status set to 400 (Humana insurance detected - only Medicare/Medicaid coverage)",
                    "case_id": case_id,
                    "case_status": 400,
                    "override_reason": "humana_insurance_rejected"
                }
            
            # Check if Medicare is in insurance - if so, set case_status to 7
            if case_data.get("ins_provider") and "medicare" in case_data["ins_provider"].lower():
                logger.info(f"Case {case_id}: Medicare detected in insurance, setting status to 7")
                update_query, has_timestamp = build_status_update_query(7)
                cursor.execute(update_query, (7, case_id))
                
                return {
                    "success": True,
                    "message": "Case status set to 7 (Medicare insurance detected)",
                    "case_id": case_id,
                    "case_status": 7,
                    "override_reason": "medicare"
                }
            
            # Check if demo_file and note_file are not null
            if not case_data["demo_file"] or not case_data["note_file"]:
                logger.info(f"Case {case_id}: Missing required files - demo_file: {case_data['demo_file']}, note_file: {case_data['note_file']}")
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
                logger.info(f"Case {case_id}: No procedure codes found, cannot update status")
                return {
                    "success": False,
                    "message": "At least one procedure code is required",
                    "case_id": case_id,
                    "procedure_count": procedure_count
                }
            
            logger.debug(f"Case {case_id}: Found {procedure_count} procedure code(s)")
            
            # Check if patient is 65 or older
            patient_age = None
            is_senior = False
            
            if case_data["patient_dob"] == '0000-00-00':
                logger.debug(f"Case {case_id}: patient_dob is '0000-00-00' (MySQL NULL), treating as no DOB")
            
            if case_data["patient_dob"] and case_data["patient_dob"] != '0000-00-00':
                # Calculate patient age based on DOB
                today = date.today()
                birth_date = case_data["patient_dob"]
                
                # Handle both date objects and string dates from database
                if isinstance(birth_date, str):
                    birth_date = datetime.strptime(birth_date, "%Y-%m-%d").date()
                
                patient_age = today.year - birth_date.year - ((today.month, today.day) < (birth_date.month, birth_date.day))
                is_senior = patient_age >= 65
            
            # Determine final status based on patient age and assistant surgeon billing eligibility
            if is_senior:
                # Patient is 65 or older - needs manual insurance confirmation
                final_status = 7
                status_message = f"Case status updated successfully to 7 (patient age {patient_age} >= 65, needs insurance confirmation)"
                logger.info(f"Case {case_id}: Patient age {patient_age} >= 65, setting status to 7")
            else:
                # Patient is under 65 or DOB is NULL - use billable procedure logic
                cursor.execute("""
                    SELECT COUNT(*) as billable_count 
                    FROM case_procedure_codes 
                    WHERE case_id = %s AND asst_surg = 2
                """, (case_id,))
                billable_count = cursor.fetchone()["billable_count"]
                
                logger.info(f"Case {case_id}: Patient age {patient_age if patient_age else 'NULL'} (< 65), billable procedures (asst_surg=2): {billable_count}")
                
                if billable_count > 0:
                    # At least one billable assistant surgeon procedure - ready for submission
                    final_status = 10
                    status_message = "Case status updated successfully from 0 to 10 (ready for submission)"
                    logger.info(f"Case {case_id}: {billable_count} billable procedure(s) found, setting status to 10")
                else:
                    # No billable assistant surgeon procedures - needs review
                    final_status = 7
                    status_message = "Case status updated successfully from 0 to 7 (complete but needs review - no billable assistant surgeon procedures)"
                    logger.info(f"Case {case_id}: No billable procedures found, setting status to 7")
            
            # All conditions met, update case status
            update_query, has_timestamp = build_status_update_query(final_status)
            logger.debug(f"Case {case_id}: Executing UPDATE query with status={final_status}, timestamp_update={has_timestamp}")
            cursor.execute(update_query, (final_status, case_id))
            
            if cursor.rowcount == 0:
                logger.error(f"Case {case_id}: UPDATE query affected 0 rows - case may not exist or be inactive")
                return {
                    "success": False,
                    "message": "Failed to update case status",
                    "case_id": case_id
                }
            
            logger.info(f"Case {case_id}: Successfully updated to status {final_status} (timestamp_updated: {has_timestamp})")
            
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
        logger.error(f"Case {case_id}: Exception in update_case_status: {str(e)}", exc_info=True)
        return {
            "success": False,
            "message": f"Error updating case status: {str(e)}",
            "case_id": case_id
        }