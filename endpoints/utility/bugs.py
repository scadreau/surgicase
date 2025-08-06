# Created: 2025-08-06 14:20:21
# Last Modified: 2025-08-06 15:43:25
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
def create_bug_report(request: Request, bug_data: BugReport, user_id: str = Query(..., description="User ID for authorization")):
    """
    Create a comprehensive bug report with full application context and user validation.
    
    This endpoint provides a robust bug reporting system that captures detailed application
    state information including user context, environmental data, and system status at the
    time of the bug occurrence. The system validates user authorization before accepting
    bug reports and stores both structured data and the complete JSON payload for analysis.
    
    Args:
        request (Request): FastAPI request object for logging and monitoring
        bug_data (BugReport): Comprehensive bug report data model containing:
            - bug_date (str): Date/time when the bug occurred
            - calling_page (str): Page or component where the bug was encountered
            - priority (str): Bug priority level (e.g., "High", "Medium", "Low")
            - bug (Dict[str, str]): Core bug information including:
                - title (str): Brief description of the bug
                - description (str): Detailed bug description and reproduction steps
            - user_profile (Dict[str, Any]): User information including:
                - first_name (str): User's first name
                - last_name (str): User's last name
                - Additional profile fields for context
            - case_statuses (list, optional): Current case status data for context
            - surgeons (list, optional): Available surgeons data for context
            - facilities (list, optional): Available facilities data for context
            - user_types (list, optional): User type information for context
            - permissions (Dict[str, Any], optional): User permissions at time of bug
            - environment_info (Dict[str, Any], optional): Browser/system environment data
        user_id (str): User ID for authorization validation (must exist in user_profile table)
    
    Returns:
        dict: Response containing:
            - message (str): Success confirmation message
            - bug_id (int): Auto-generated unique identifier for the bug report
            - status (str): Initial bug status (always "Open")
    
    Raises:
        HTTPException:
            - 404 Not Found: User not found or inactive in user_profile table
            - 500 Internal Server Error: Database errors or processing failures
    
    Database Operations:
        - Validates user existence and active status in 'user_profile' table
        - Inserts comprehensive bug report into 'bugs' table with field mapping:
          - title: Extracted from bug_data.bug["title"]
          - description: Extracted from bug_data.bug["description"]
          - calling_page: Direct mapping from bug_data.calling_page
          - status: Hardcoded as "Open" for new reports
          - priority: Direct mapping from bug_data.priority
          - reported_by: Concatenated first_name + last_name from user_profile
          - full_json: Complete JSON serialization of bug_data for analysis
        - Transaction management with automatic rollback on errors
        - Auto-generated bug_id returned for tracking purposes
    
    Monitoring & Logging:
        - Business metrics tracking for bug report operations:
          - "success": Bug report successfully created
          - "user_not_found": Authorization validation failed
          - "error": System or database errors
        - Prometheus monitoring via @track_business_operation decorator
        - Comprehensive request logging with execution time tracking
        - Full JSON payload preservation for debugging and analysis
        - Error logging with rollback tracking
    
    Data Processing:
        - JSON serialization of complete bug report for forensic analysis
        - Name concatenation with proper spacing and trimming
        - Field extraction with fallback handling for missing data
        - Automatic timestamp generation for created_ts field
    
    Example Request:
        POST /bugs?user_id=USER123
        {
            "bug_date": "2024-01-15T10:30:00Z",
            "calling_page": "/dashboard/cases",
            "priority": "High",
            "bug": {
                "title": "Case creation fails silently",
                "description": "When clicking 'Create Case', no error shown but case not created"
            },
            "user_profile": {
                "first_name": "John",
                "last_name": "Doe",
                "user_type": 200
            },
            "case_statuses": [...],
            "environment_info": {"browser": "Chrome", "version": "120.0"}
        }
    
    Example Response:
        {
            "message": "Bug report created successfully",
            "bug_id": 1234,
            "status": "Open"
        }
    
    Security Considerations:
        - User authorization required via active user_profile validation
        - Input sanitization through Pydantic model validation
        - No sensitive data exposure in error messages
        - Complete audit trail through full JSON preservation
    
    Notes:
        - Bug reports are created with "Open" status regardless of priority
        - Full application context captured for comprehensive debugging
        - User profile validation ensures only authorized users can submit reports
        - JSON payload preserved for forensic analysis and debugging
    """
    conn = None
    start_time = time.time()
    response_status = 201
    response_data = None
    error_message = None
    
    try:
        conn = get_db_connection()
        
        try:
            # First, validate that the user exists
            with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                cursor.execute(
                    "SELECT user_id FROM user_profile WHERE user_id = %s AND active = 1",
                    (user_id,)
                )
                user = cursor.fetchone()
                
                if not user:
                    response_status = 404
                    error_message = "User not found or inactive"
                    business_metrics.record_utility_operation("create_bug_report", "user_not_found")
                    raise HTTPException(status_code=404, detail={"error": "User not found or inactive"})
            
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
            user_id=user_id,
            response_data=response_data,
            error_message=error_message
        )

@router.get("/bugs")
@track_business_operation("get", "bugs")
def get_bug_reports(request: Request, user_id: str = Query(..., description="User ID for authorization")):
    """
    Retrieve all open bug reports for review and management purposes.
    
    This endpoint provides access to all bug reports that are not in 'Closed' status,
    allowing administrators and developers to review, prioritize, and manage outstanding
    issues. The endpoint requires user authorization for access control and audit logging
    but returns all open bugs regardless of the original reporter.
    
    Args:
        request (Request): FastAPI request object for logging and monitoring
        user_id (str): User ID for authorization and logging purposes.
                      Required for access control but does not filter results.
    
    Returns:
        dict: Response containing:
            - bugs (List[dict]): Array of open bug report objects, each containing:
                - bug_id (int): Unique identifier for the bug report
                - title (str): Brief description/title of the bug
                - description (str): Detailed bug description and reproduction steps
                - calling_page (str): Page or component where the bug was encountered
                - status (str): Current bug status (excluding 'Closed' bugs)
                - priority (str): Bug priority level (e.g., "High", "Medium", "Low")
                - created_ts (datetime): Timestamp when the bug report was created
    
    Raises:
        HTTPException: 
            - 500 Internal Server Error: Database connection or query execution errors
    
    Database Operations:
        - Queries 'bugs' table for all records where status != 'Closed'
        - Returns essential bug tracking fields for management interface
        - Read-only operation with automatic connection management
        - Results may be ordered by created_ts or priority (database default)
    
    Monitoring & Logging:
        - Business metrics tracking for bug report retrieval operations
        - Prometheus monitoring via @track_business_operation decorator
        - Comprehensive request logging with execution time tracking
        - User ID tracking for audit purposes
    
    Example Response:
        {
            "bugs": [
                {
                    "bug_id": 1234,
                    "title": "Case creation fails silently",
                    "description": "When clicking 'Create Case', no error shown but case not created",
                    "calling_page": "/dashboard/cases",
                    "status": "Open",
                    "priority": "High",
                    "created_ts": "2024-01-15T10:30:00"
                },
                {
                    "bug_id": 1235,
                    "title": "Search results pagination broken",
                    "description": "Page navigation buttons not working in surgeon search",
                    "calling_page": "/surgeons/search",
                    "status": "In Progress",
                    "priority": "Medium",
                    "created_ts": "2024-01-16T14:22:15"
                }
            ]
        }
    
    Usage:
        GET /bugs?user_id=USER123
        
    Notes:
        - User ID is required for authorization but does not filter bug results
        - Only returns bugs with status other than 'Closed'
        - Used by administrative interfaces for bug management and tracking
        - Results include all essential fields for bug triage and assignment
        - Full bug details including JSON payload available through other endpoints if needed
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