# Created: 2025-07-15 11:54:13
# Last Modified: 2025-08-04 11:20:26
# Author: Scott Cadreau

# endpoints/backoffice/get_cases_by_status.py
from fastapi import APIRouter, HTTPException, Query, Request
import pymysql.cursors
from core.database import get_db_connection, close_db_connection
from utils.monitoring import track_business_operation, business_metrics
from utils.text_formatting import capitalize_name_field
import time
from datetime import datetime

router = APIRouter()

@router.get("/cases_by_status")
@track_business_operation("get", "cases_by_status")
def get_cases_by_status(
    request: Request, 
    user_id: str = Query(..., description="The user ID making the request (must be user_type >= 10)"), 
    filter: str = Query("", description="Comma-separated list of case_status values (e.g. 0,1,2) or 'all' to get all cases"),
    start_date: str = Query(None, description="Start date filter in YYYY-MM-DD format (optional)"),
    end_date: str = Query(None, description="End date filter in YYYY-MM-DD format (optional)")
):
    """
    Retrieve all cases filtered by case_status values and optional date range, only if the calling user has user_type >= 10.
    Returns a list of cases in the same format as get_case.
    Use filter='all' to get all cases regardless of status.
    Use start_date and end_date to filter by case_date range (format: YYYY-MM-DD).
    """
    conn = None
    start_time = time.time()
    response_status = 200
    response_data = None
    error_message = None
    
    try:
        # Parse filter string - handle "all" as special case
        if filter.lower() == "all":
            status_list = "all"
        elif filter:
            status_list = [int(s) for s in filter.split(",") if s.strip().isdigit()]
        else:
            status_list = []

        # Validate date formats if provided
        parsed_start_date = None
        parsed_end_date = None
        
        if start_date:
            try:
                parsed_start_date = datetime.strptime(start_date, "%Y-%m-%d").date()
            except ValueError:
                response_status = 400
                error_message = "Invalid start_date format. Use YYYY-MM-DD format."
                raise HTTPException(status_code=400, detail="Invalid start_date format. Use YYYY-MM-DD format.")
        
        if end_date:
            try:
                parsed_end_date = datetime.strptime(end_date, "%Y-%m-%d").date()
            except ValueError:
                response_status = 400
                error_message = "Invalid end_date format. Use YYYY-MM-DD format."
                raise HTTPException(status_code=400, detail="Invalid end_date format. Use YYYY-MM-DD format.")

        conn = get_db_connection()
        
        try:
            with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                # Check user_type for the requesting user
                cursor.execute("SELECT user_type FROM user_profile WHERE user_id = %s", (user_id,))
                user_row = cursor.fetchone()
                if not user_row or user_row.get("user_type", 0) < 10:
                    # Record failed access (permission denied)
                    business_metrics.record_utility_operation("get_cases_by_status", "permission_denied")
                    response_status = 403
                    error_message = "User does not have permission to access all cases"
                    raise HTTPException(status_code=403, detail="User does not have permission to access all cases.")

                # Build query for all cases with surgeon, facility, and provider names
                sql = """
                    SELECT 
                        c.user_id, c.case_id, c.case_date, c.patient_first, c.patient_last, 
                        c.ins_provider, c.surgeon_id, c.facility_id, c.case_status, 
                        csl.case_status_desc,
                        c.demo_file, c.note_file, c.misc_file, c.pay_amount,
                        CONCAT(s.first_name, ' ', s.last_name) as surgeon_name,
                        f.facility_name,
                        up.first_name as provider_first_name,
                        up.last_name as provider_last_name
                    FROM cases c
                    LEFT JOIN surgeon_list s ON c.surgeon_id = s.surgeon_id
                    LEFT JOIN facility_list f ON c.facility_id = f.facility_id
                    LEFT JOIN case_status_list csl ON c.case_status = csl.case_status
                    LEFT JOIN user_profile up ON c.user_id = up.user_id
                    WHERE c.active = 1
                """
                params = []
                
                # Only add status filter if not "all"
                if status_list != "all" and status_list:
                    placeholders = ",".join(["%s"] * len(status_list))
                    sql += f" AND c.case_status IN ({placeholders})"
                    params.extend(status_list)
                
                # Add date filters if provided
                if parsed_start_date:
                    sql += " AND c.case_date >= %s"
                    params.append(parsed_start_date)
                
                if parsed_end_date:
                    sql += " AND c.case_date <= %s"
                    params.append(parsed_end_date)
                    
                cursor.execute(sql, params)
                cases = cursor.fetchall()

                result = []
                for case_data in cases:
                    # Convert datetime to ISO format if it's a datetime object
                    if case_data["case_date"] and hasattr(case_data["case_date"], 'isoformat'):
                        case_data["case_date"] = case_data["case_date"].isoformat()
                    
                    # Apply proper capitalization to provider names and combine them
                    provider_first = case_data.get("provider_first_name")
                    provider_last = case_data.get("provider_last_name")
                    
                    if provider_first or provider_last:
                        # Apply capitalization to each name component
                        capitalized_first = capitalize_name_field(provider_first) if provider_first else ""
                        capitalized_last = capitalize_name_field(provider_last) if provider_last else ""
                        
                        # Combine into full provider name
                        provider_name_parts = [part for part in [capitalized_first, capitalized_last] if part.strip()]
                        case_data["provider_name"] = " ".join(provider_name_parts) if provider_name_parts else None
                    else:
                        case_data["provider_name"] = None
                    
                    # Remove the separate first/last name fields from the response
                    case_data.pop("provider_first_name", None)
                    case_data.pop("provider_last_name", None)
                    
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

                # Record successful cases retrieval
                business_metrics.record_utility_operation("get_cases_by_status", "success")
                
        finally:
            close_db_connection(conn)
            
        response_data = {
            "cases": result,
            "filter": status_list,
            "start_date": start_date,
            "end_date": end_date
        }
        return response_data

    except HTTPException as http_error:
        # Re-raise HTTP exceptions and capture error details
        response_status = http_error.status_code
        error_message = str(http_error.detail)
        raise
    except Exception as e:
        # Record failed cases retrieval
        response_status = 500
        error_message = str(e)
        business_metrics.record_utility_operation("get_cases_by_status", "error")
        
        if 'conn' in locals():
            close_db_connection(conn)
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