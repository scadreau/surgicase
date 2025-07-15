# Created: 2025-07-15 09:20:13
# Last Modified: 2025-07-15 11:12:58

# endpoints/case/filter_cases.py
from fastapi import APIRouter, HTTPException, Query
import pymysql.cursors
from core.database import get_db_connection

router = APIRouter()

@router.get("/casefilter")
async def get_cases(user_id: str = Query(..., description="The user ID to retrieve cases for"), filter: str = Query("", description="Comma-separated list of case_status values (e.g. 0,1,2)")):
    """
    Retrieve all cases for a user_id, filtered by case_status values.
    Returns a list of cases in the same format as get_case.
    """
    try:
        # Parse filter string into a list of integers
        if filter:
            status_list = [int(s) for s in filter.split(",") if s.strip().isdigit()]
        else:
            status_list = []

        conn = get_db_connection()
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            # Build query
            sql = "SELECT user_id, case_id, case_date, patient_first, patient_last, ins_provider, surgeon_id, facility_id, case_status, demo_file, note_file, misc_file, pay_amount FROM cases WHERE user_id = %s and active = 1"
            params = [user_id]
            if status_list:
                sql += " AND case_status IN (%s)" % (",".join(["%s"] * len(status_list)))
                params.extend([str(s) for s in status_list])
            cursor.execute(sql, params)
            cases = cursor.fetchall()

            result = []
            for case_data in cases:
                # Convert datetime to ISO format
                if case_data["case_date"]:
                    case_data["case_date"] = case_data["case_date"].isoformat()
                # fetch procedure codes for each case
                cursor.execute("SELECT procedure_code FROM case_procedure_codes WHERE case_id = %s", (case_data["case_id"],))
                codes = [row['procedure_code'] for row in cursor.fetchall()]
                case_data['procedure_codes'] = codes
                result.append(case_data)

        conn.close()
        return {
            "cases": result,
            "user_id": user_id,
            "filter": status_list
        }

    except Exception as e:
        if 'conn' in locals():
            conn.close()
        raise HTTPException(status_code=500, detail={"error": str(e)})