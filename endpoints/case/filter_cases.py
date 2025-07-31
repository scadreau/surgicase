# Created: 2025-07-15 09:20:13
# Last Modified: 2025-07-31 18:47:55
# Author: Scott Cadreau

# endpoints/case/filter_cases.py
from fastapi import APIRouter, HTTPException, Query, Request
import pymysql.cursors
from core.database import get_db_connection, close_db_connection
from utils.monitoring import track_business_operation, business_metrics
import time

router = APIRouter()

@router.get("/case_filter")
@track_business_operation("filter", "case")
def get_cases(request: Request, user_id: str = Query(..., description="The user ID to retrieve cases for"), filter: str = Query("", description="Comma-separated list of case_status values (e.g. 0,1,2) or 'all' for all statuses")):
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
        # Parse filter string - handle "all" case or comma-separated integers
        if filter.lower() == "all":
            status_list = ["all"]
        elif filter:
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
                
                # Build query with special handling for max_case_status filter and "all" option with surgeon and facility names
                sql = """
                    SELECT 
                        c.user_id, c.case_id, c.case_date, c.patient_first, c.patient_last, 
                        c.ins_provider, c.surgeon_id, c.facility_id, c.case_status, 
                        c.demo_file, c.note_file, c.misc_file, c.pay_amount,
                        CONCAT(s.first_name, ' ', s.last_name) as surgeon_name,
                        f.facility_name
                    FROM cases c
                    LEFT JOIN surgeon_list s ON c.surgeon_id = s.surgeon_id
                    LEFT JOIN facility_list f ON c.facility_id = f.facility_id
                    WHERE c.user_id = %s and c.active = 1 order by case_id desc
                """
                params = [user_id]
                
                if status_list and status_list != ["all"]:
                    # Check if max_case_status is in the filter list
                    if max_case_status in status_list:
                        # Remove max_case_status from the list for separate handling
                        other_statuses = [s for s in status_list if s != max_case_status]
                        
                        if other_statuses:
                            # Query for both specific statuses and >= max_case_status
                            sql += " AND (c.case_status IN (%s) OR c.case_status >= %%s)" % (",".join(["%s"] * len(other_statuses)))
                            params.extend([str(s) for s in other_statuses])
                            params.append(max_case_status)
                        else:
                            # Only max_case_status requested, get all >= max_case_status
                            sql += " AND c.case_status >= %s"
                            params.append(max_case_status)
                    else:
                        # Normal filtering without max_case_status special handling
                        sql += " AND c.case_status IN (%s)" % (",".join(["%s"] * len(status_list)))
                        params.extend([str(s) for s in status_list])
                # If status_list is empty or ["all"], no additional WHERE clause needed
                
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
                    
                    # fetch procedure codes with descriptions - JOIN with procedure_codes table
                    cursor.execute("""
                        SELECT cpc.procedure_code, pc.procedure_desc 
                        FROM case_procedure_codes cpc 
                        LEFT JOIN procedure_codes_desc pc ON cpc.procedure_code = pc.procedure_code 
                        WHERE cpc.case_id = %s
                    """, (case_data["case_id"],))
                    procedure_data = [{'procedure_code': row['procedure_code'], 'procedure_desc': row['procedure_desc']} for row in cursor.fetchall()]
                    case_data['procedure_codes'] = procedure_data
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