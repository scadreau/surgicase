# Created: 2025-07-15 09:20:13
# Last Modified: 2025-07-23 11:59:43

# endpoints/case/filter_cases.py
from fastapi import APIRouter, HTTPException, Query, Request
import pymysql.cursors
from core.database import get_db_connection, close_db_connection
from utils.monitoring import track_business_operation, business_metrics
import time

router = APIRouter()

@router.get("/casefilter")
@track_business_operation("filter", "case")
def get_cases(request: Request, user_id: str = Query(..., description="The user ID to retrieve cases for"), filter: str = Query("", description="Comma-separated list of case_status values (e.g. 0,1,2)")):
    """
    Retrieve all cases for a user_id, filtered by case_status values.
    Returns a list of cases in the same format as get_case.
    """
    conn = None
    start_time = time.time()
    response_status = 200
    response_data = None
    error_message = None
    
    try:
        # Parse filter string into a list of integers
        if filter:
            status_list = [int(s) for s in filter.split(",") if s.strip().isdigit()]
        else:
            status_list = []

        conn = get_db_connection()
        
        try:
            with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                # Get user's max_case_status from user_profile
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
                    # Apply case status visibility restriction
                    original_case_status = case_data["case_status"]
                    if original_case_status > max_case_status:
                        case_data["case_status"] = max_case_status
                    
                    # Convert datetime to ISO format
                    if case_data["case_date"]:
                        case_data["case_date"] = case_data["case_date"].isoformat()
                    # fetch procedure codes for each case
                    cursor.execute("SELECT procedure_code FROM case_procedure_codes WHERE case_id = %s", (case_data["case_id"],))
                    codes = [row['procedure_code'] for row in cursor.fetchall()]
                    case_data['procedure_codes'] = codes
                    result.append(case_data)
            
            # Record successful case filtering
            business_metrics.record_case_operation("filter", "success", f"user_{user_id}")
            
        finally:
            close_db_connection(conn)
            
        response_data = {
            "cases": result,
            "user_id": user_id,
            "filter": status_list
        }
        return response_data

    except HTTPException as http_error:
        # Re-raise HTTP exceptions and capture error details
        response_status = http_error.status_code
        error_message = str(http_error.detail)
        raise
    except Exception as e:
        response_status = 500
        error_message = str(e)
        raise HTTPException(status_code=500, detail={"error": str(e)})
        
    finally:
        # Calculate execution time
        execution_time_ms = int((time.time() - start_time) * 1000)
        
        # Log request details for monitoring using the utility function
        from endpoints.utility.log_request import log_request_from_endpoint
        log_request_from_endpoint(
            request=request,
            execution_time_ms=execution_time_ms,
            response_status=response_status,
            user_id=user_id,
            response_data=response_data,
            error_message=error_message
        )