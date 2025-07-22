# Created: 2025-07-15 09:20:13
# Last Modified: 2025-07-22 12:11:06

# endpoints/case/get_case.py
from fastapi import APIRouter, HTTPException, Query
import pymysql.cursors
from core.database import get_db_connection, close_db_connection
from utils.monitoring import track_business_operation, business_metrics

router = APIRouter()

@router.get("/case")
@track_business_operation("read", "case")
def get_case(case_id: str = Query(..., description="The case ID to retrieve")):
    """
    Retrieve case information by case_id
    """
    try:
        if not case_id:
            raise HTTPException(status_code=400, detail="Missing case_id parameter")

        conn = get_db_connection()

        try:
            with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                # fetch from cases table
                cursor.execute("""
                    SELECT user_id, case_id, case_date, patient_first, patient_last, ins_provider, surgeon_id, facility_id, case_status, demo_file, note_file, misc_file, pay_amount
                    FROM cases 
                    WHERE case_id = %s and active = 1
                """, (case_id,))
                case_data = cursor.fetchone()

                if not case_data:
                    # Record failed case read operation
                    business_metrics.record_case_operation("read", "not_found", case_id)
                    raise HTTPException(
                        status_code=404,
                        detail={"error": "Case not found", "case_id": case_id}
                    )
                
                # Get user's max_case_status from user_profile
                user_id = case_data["user_id"]
                cursor.execute("""
                    SELECT max_case_status 
                    FROM user_profile 
                    WHERE user_id = %s AND active = 1
                """, (user_id,))
                user_profile = cursor.fetchone()
                
                if not user_profile:
                    # If user profile not found, use default max_case_status of 20
                    max_case_status = 20
                else:
                    max_case_status = user_profile["max_case_status"] or 20
                
                # Apply case status visibility restriction
                original_case_status = case_data["case_status"]
                if original_case_status > max_case_status:
                    case_data["case_status"] = max_case_status
                
                # Convert datetime to ISO format
                if case_data["case_date"]:
                    case_data["case_date"] = case_data["case_date"].isoformat()

                # fetch procedure codes with descriptions - JOIN with procedure_codes table
                cursor.execute("""
                    SELECT cpc.procedure_code, pc.procedure_desc 
                    FROM case_procedure_codes cpc 
                    LEFT JOIN procedure_codes pc ON cpc.procedure_code = pc.procedure_code 
                    WHERE cpc.case_id = %s
                """, (case_id,))
                procedure_data = [{'procedure_code': row['procedure_code'], 'procedure_desc': row['procedure_desc']} for row in cursor.fetchall()]
                case_data['procedure_codes'] = procedure_data

            # Record successful case read operation
            business_metrics.record_case_operation("read", "success", case_id)

        finally:
            close_db_connection(conn)

        return {
            "case": case_data,
            "user_id": case_data["user_id"],
            "case_id": case_id
        }

    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail={"error": str(e)})