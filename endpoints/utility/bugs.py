# Created: 2025-08-06 14:20:21
# Last Modified: 2025-08-06 14:30:54
# Author: Scott Cadreau

# endpoints/utility/bugs.py
from fastapi import APIRouter, HTTPException, Request, Query
from pydantic import BaseModel
from typing import Dict, Any
import pymysql.cursors
import json
from core.database import get_db_connection, close_db_connection
from utils.monitoring import track_business_operation, business_metrics
import time

router = APIRouter()

class BugReport(BaseModel):
    bug_date: str
    calling_page: str
    priority: str
    bug: Dict[str, str]
    user_profile: Dict[str, Any]
    case_statuses: list = []
    surgeons: list = []
    facilities: list = []
    user_types: list = []
    permissions: Dict[str, Any] = {}
    environment_info: Dict[str, Any] = {}

@router.post("/bugs")
@track_business_operation("post", "bugs")
def create_bug_report(request: Request, bug_data: BugReport):
    """
    Create a new bug report entry.
    Takes the provided JSON package and logs the information in the bugs table.
    
    Field mapping:
    - title: bug.title from json
    - description: bug.description from json  
    - calling_page: calling_page from json
    - status: "Open" (hardcoded)
    - priority: priority from json
    - reported_by: user_profile.first_name + user_profile.last_name from json
    - full_json: the full json package from the request
    """
    conn = None
    start_time = time.time()
    response_status = 201
    response_data = None
    error_message = None
    
    try:
        conn = get_db_connection()
        
        try:
            # Extract required fields from the JSON payload
            title = bug_data.bug.get("title", "")
            description = bug_data.bug.get("description", "")
            calling_page = bug_data.calling_page
            status = "Open"  # Hardcoded as requested
            priority = bug_data.priority
            
            # Combine first and last name for reported_by field
            first_name = bug_data.user_profile.get("first_name", "").strip()
            last_name = bug_data.user_profile.get("last_name", "").strip()
            reported_by = f"{first_name} {last_name}".strip()
            
            # Convert the full payload to JSON string
            full_json = json.dumps(bug_data.dict())
            
            with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                # Insert the bug report into the bugs table
                insert_query = """
                    INSERT INTO bugs (title, description, calling_page, status, priority, reported_by, full_json)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """
                cursor.execute(
                    insert_query,
                    (title, description, calling_page, status, priority, reported_by, full_json)
                )
                
                # Get the auto-generated bug_id
                bug_id = cursor.lastrowid
                
                # Commit the transaction
                conn.commit()

                # Record successful bug report creation
                business_metrics.record_utility_operation("create_bug_report", "success")
                
        finally:
            close_db_connection(conn)
            
        response_data = {
            "message": "Bug report created successfully",
            "bug_id": bug_id,
            "status": status
        }
        return response_data
        
    except Exception as e:
        # Record failed bug report creation
        response_status = 500
        error_message = str(e)
        business_metrics.record_utility_operation("create_bug_report", "error")
        
        if 'conn' in locals() and conn:
            conn.rollback()
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
            user_id=bug_data.user_profile.get("user_id", "unknown"),
            response_data=response_data,
            error_message=error_message
        )

@router.get("/bugs")
@track_business_operation("get", "bugs")
def get_bug_reports(request: Request, user_id: str = Query(..., description="User ID for authorization")):
    """
    Get all open bug reports (status not 'Closed').
    Returns bug_id, title, description, calling_page, status, priority, created_ts from bugs table.
    
    Note: This endpoint requires user_id for authorization and logging purposes,
    but currently returns all open bugs regardless of who reported them.
    """
    conn = None
    start_time = time.time()
    response_status = 200
    response_data = None
    error_message = None
    
    try:
        conn = get_db_connection()
        
        try:
            with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                # Query for all open bug reports
                select_query = """
                    SELECT bug_id, title, description, calling_page, status, priority, created_ts 
                    FROM bugs 
                    WHERE status NOT IN ('Closed')
                    ORDER BY created_ts DESC
                """
                cursor.execute(select_query)
                bugs = cursor.fetchall()

                # Record successful bug reports retrieval
                business_metrics.record_utility_operation("get_bug_reports", "success")
                
        finally:
            close_db_connection(conn)
            
        response_data = {
            "bugs": bugs,
            "count": len(bugs)
        }
        return response_data
        
    except HTTPException as http_error:
        # Re-raise HTTP exceptions and capture error details
        response_status = http_error.status_code
        error_message = str(http_error.detail)
        raise
    except Exception as e:
        # Record failed bug reports retrieval
        response_status = 500
        error_message = str(e)
        business_metrics.record_utility_operation("get_bug_reports", "error")
        
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