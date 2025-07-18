# Created: 2025-07-15 11:54:13
# Last Modified: 2025-07-15 20:45:35

# endpoints/backoffice/get_cases_by_status.py
from fastapi import APIRouter, HTTPException, Query
import pymysql.cursors
from core.database import get_db_connection, close_db_connection
from utils.monitoring import track_business_operation, business_metrics

router = APIRouter()

@router.get("/casesbystatus")
@track_business_operation("get", "cases_by_status")
def get_cases_by_status(user_id: str = Query(..., description="The user ID making the request (must be user_type >= 10)"), filter: str = Query("", description="Comma-separated list of case_status values (e.g. 0,1,2)")):
    """
    Retrieve all cases filtered by case_status values, only if the calling user has user_type >= 10.
    Returns a list of cases in the same format as get_case.
    """
    try:
        # Parse filter string into a list of integers
        if filter:
            status_list = [int(s) for s in filter.split(",") if s.strip().isdigit()]
        else:
            status_list = []

        conn = get_db_connection()
        
        try:
            with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                # Check user_type for the requesting user
                cursor.execute("SELECT user_type FROM user_profile WHERE user_id = %s", (user_id,))
                user_row = cursor.fetchone()
                if not user_row or user_row.get("user_type", 0) < 10:
                    # Record failed access (permission denied)
                    business_metrics.record_utility_operation("get_cases_by_status", "permission_denied")
                    raise HTTPException(status_code=403, detail="User does not have permission to access all cases.")

                # Build query for all cases (no user_id filter)
                sql = "SELECT user_id, case_id, case_date, patient_first, patient_last, ins_provider, surgeon_id, facility_id, case_status, demo_file, note_file, misc_file, pay_amount FROM cases WHERE active = 1"
                params = []
                if status_list:
                    placeholders = ",".join(["%s"] * len(status_list))
                    sql += f" AND case_status IN ({placeholders})"
                    params.extend(status_list)
                cursor.execute(sql, params)
                cases = cursor.fetchall()

                result = []
                for case_data in cases:
                    # Convert datetime to ISO format if it's a datetime object
                    if case_data["case_date"] and hasattr(case_data["case_date"], 'isoformat'):
                        case_data["case_date"] = case_data["case_date"].isoformat()
                    # fetch procedure codes for each case
                    cursor.execute("SELECT procedure_code FROM case_procedure_codes WHERE case_id = %s", (case_data["case_id"],))
                    codes = [row['procedure_code'] for row in cursor.fetchall()]
                    case_data['procedure_codes'] = codes
                    result.append(case_data)

                # Record successful cases retrieval
                business_metrics.record_utility_operation("get_cases_by_status", "success")
                
        finally:
            close_db_connection(conn)
            
        return {
            "cases": result,
            "filter": status_list
        }

    except HTTPException:
        raise
    except Exception as e:
        # Record failed cases retrieval
        business_metrics.record_utility_operation("get_cases_by_status", "error")
        
        if 'conn' in locals():
            close_db_connection(conn)
        raise HTTPException(status_code=500, detail={"error": str(e)}) 