# Created: 2025-07-15 11:54:13
# Last Modified: 2025-07-15 12:46:37

# endpoints/backoffice/get_cases_by_status.py
from fastapi import APIRouter, HTTPException, Query, Request
import pymysql.cursors
from core.database import get_db_connection
import time
import requests

router = APIRouter()

@router.get("/casesbystatus")
async def get_cases_by_status(
    request: Request,  # <-- Move this before default arguments
    user_id: str = Query(..., description="The user ID making the request (must be user_type >= 10)"),
    filter: str = Query("", description="Comma-separated list of case_status values (e.g. 0,1,2)")
):
    start_time = time.time()
    log_data = {
        "user_id": user_id,
        "endpoint": str(request.url.path),
        "method": request.method,
        "request_payload": "",
        "query_params": dict(request.query_params),
        "client_ip": request.client.host if request.client else None,
    }
    try:
        # Parse filter string into a list of integers
        if filter:
            status_list = [int(s) for s in filter.split(",") if s.strip().isdigit()]
        else:
            status_list = []

        conn = get_db_connection()
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            # Check user_type for the requesting user
            cursor.execute("SELECT user_type FROM user_profile WHERE user_id = %s", (user_id,))
            user_row = cursor.fetchone()
            if not user_row or user_row.get("user_type", 0) < 10:
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

        conn.close()
        execution_time_ms = int((time.time() - start_time) * 1000)
        log_data.update({
            "timestamp": None,
            "response_status": 200,
            "response_payload": str({"cases": result, "filter": status_list}),
            "execution_time_ms": execution_time_ms,
            "error_message": None,
        })
        try:
            requests.post("http://localhost:8000/log_request", json=log_data)
        except Exception as log_exc:
            pass
        return {
            "cases": result,
            "filter": status_list
        }

    except HTTPException as http_exc:
        if 'conn' in locals():
            conn.close()
        execution_time_ms = int((time.time() - start_time) * 1000)
        log_data.update({
            "timestamp": None,
            "response_status": http_exc.status_code if hasattr(http_exc, 'status_code') else 403,
            "response_payload": None,
            "execution_time_ms": execution_time_ms,
            "error_message": str(http_exc.detail) if hasattr(http_exc, 'detail') else "User does not have permission to access all cases.",
        })
        try:
            requests.post("http://localhost:8000/log_request", json=log_data)
        except Exception as log_exc:
            pass
        raise
    except Exception as e:
        if 'conn' in locals():
            conn.close()
        execution_time_ms = int((time.time() - start_time) * 1000)
        log_data.update({
            "timestamp": None,
            "response_status": 500,
            "response_payload": None,
            "execution_time_ms": execution_time_ms,
            "error_message": str(e),
        })
        try:
            requests.post("http://localhost:8000/log_request", json=log_data)
        except Exception as log_exc:
            pass
        raise HTTPException(status_code=500, detail={"error": str(e)}) 