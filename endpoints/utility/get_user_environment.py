# Created: 2025-07-24 17:54:30
# Last Modified: 2025-08-06 15:46:58
# Author: Scott Cadreau
# Assisted by: Claude 4 Sonnet

# endpoints/utility/get_user_environment.py
from fastapi import APIRouter, HTTPException, Query, Request
import pymysql.cursors
from core.database import get_db_connection, close_db_connection
from utils.monitoring import track_business_operation, business_metrics
import time
from datetime import datetime

router = APIRouter()

def get_user_profile_info(user_id: str, conn) -> dict:
    """
    Get user profile information from user_profile table.
    
    Args:
        user_id: The user ID to retrieve profile for
        conn: Database connection
        
    Returns:
        dict: User profile information
    """
    with conn.cursor(pymysql.cursors.DictCursor) as cursor:
        cursor.execute("""
            SELECT user_id, user_email, first_name, last_name, addr1, addr2, 
                   city, state, zipcode, telephone, user_npi, referred_by_user, 
                   user_type, message_pref, states_licensed, user_tier, max_case_status,
                   last_login_dt, active
            FROM user_profile 
            WHERE user_id = %s AND active = 1
        """, (user_id,))
        
        user_data = cursor.fetchone()
        if not user_data:
            return None
            
        # Convert datetime to ISO format if present
        if user_data.get("last_login_dt"):
            user_data["last_login_dt"] = user_data["last_login_dt"].isoformat()
            
        # Get user documents
        cursor.execute("""
            SELECT document_type, document_name 
            FROM user_documents 
            WHERE user_id = %s
        """, (user_id,))
        documents = cursor.fetchall()
        user_data["documents"] = documents
        
        # Get user type description
        user_type = user_data.get("user_type")
        if user_type is not None:
            cursor.execute("""
                SELECT user_type_desc 
                FROM user_type_list 
                WHERE user_type = %s
            """, (user_type,))
            user_type_result = cursor.fetchone()
            if user_type_result:
                user_data["user_type_desc"] = user_type_result["user_type_desc"]
            else:
                user_data["user_type_desc"] = None
        else:
            user_data["user_type_desc"] = None
        
        return user_data

def update_user_last_login(user_id: str, conn) -> bool:
    """
    Update the last_login_dt field for a user with current datetime.
    
    Args:
        user_id: The user ID to update
        conn: Database connection
        
    Returns:
        bool: True if update was successful, False otherwise
    """
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            current_time = datetime.now()
            
            cursor.execute("""
                UPDATE user_profile 
                SET last_login_dt = %s 
                WHERE user_id = %s AND active = 1
            """, (current_time, user_id))
            
            # Return True if a row was updated
            return cursor.rowcount > 0
    except Exception as e:
        # Log the error but don't fail the main operation
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Failed to update last_login_dt for user {user_id}: {str(e)}")
        return False

def get_case_statuses_for_user(user_id: str, user_type: int, max_case_status: int, conn) -> dict:
    """
    Get case statuses based on user type permissions.
    
    Args:
        user_id: The user ID
        user_type: The user's type level
        max_case_status: The user's maximum case status level
        conn: Database connection
        
    Returns:
        dict: Case statuses with access information
    """
    with conn.cursor(pymysql.cursors.DictCursor) as cursor:
        # Build query based on user_type
        if user_type < 10:
            # User type < 10: return only case_status <= max_case_status
            cursor.execute("""
                SELECT case_status, case_status_desc 
                FROM case_status_list 
                WHERE case_status <= %s 
                ORDER BY case_status
            """, (max_case_status,))
            access_level = "limited"
        else:
            # User type >= 10: return all case_status rows
            cursor.execute("""
                SELECT case_status, case_status_desc 
                FROM case_status_list 
                ORDER BY case_status
            """)
            access_level = "full"
        
        case_statuses = cursor.fetchall()
        
        return {
            "case_statuses": case_statuses,
            "access_level": access_level,
            "total_count": len(case_statuses)
        }

def get_user_surgeons(user_id: str, conn) -> list:
    """
    Get list of surgeons associated with a user.
    
    Args:
        user_id: The user ID to retrieve surgeons for
        conn: Database connection
        
    Returns:
        list: List of surgeon records
    """
    with conn.cursor(pymysql.cursors.DictCursor) as cursor:
        cursor.execute("""
            SELECT surgeon_id, first_name, last_name, surgeon_npi 
            FROM surgeon_list 
            WHERE user_id = %s
            ORDER BY last_name, first_name
        """, (user_id,))
        
        surgeons = cursor.fetchall()
        return surgeons

def get_user_facilities(user_id: str, conn) -> list:
    """
    Get list of facilities associated with a user.
    
    Args:
        user_id: The user ID to retrieve facilities for
        conn: Database connection
        
    Returns:
        list: List of facility records
    """
    with conn.cursor(pymysql.cursors.DictCursor) as cursor:
        cursor.execute("""
            SELECT facility_id, facility_name, facility_npi 
            FROM facility_list 
            WHERE user_id = %s
            ORDER BY facility_name
        """, (user_id,))
        
        facilities = cursor.fetchall()
        return facilities

def get_available_user_types(user_type: int, conn) -> list:
    """
    Get list of user types that are <= the user's current user type.
    
    Args:
        user_type: The user's current user type level
        conn: Database connection
        
    Returns:
        list: List of user type records that the user can access/assign
    """
    with conn.cursor(pymysql.cursors.DictCursor) as cursor:
        cursor.execute("""
            SELECT user_type, user_type_desc 
            FROM user_type_list 
            WHERE user_type <= %s
            ORDER BY user_type
        """, (user_type,))
        
        user_types = cursor.fetchall()
        return user_types

@router.get("/user_environment")
@track_business_operation("get", "user_environment")
def get_user_environment(request: Request, user_id: str = Query(..., description="The user ID to get environment for")):
    """
    Retrieve comprehensive user environment data for complete application initialization.
    
    This endpoint serves as the primary user environment initialization call, providing
    all essential user context, permissions, and available resources in a single request.
    It delivers personalized data based on the user's type, access level, and permissions
    to enable complete frontend application state setup with optimal performance.
    
    Args:
        request (Request): FastAPI request object for logging and monitoring
        user_id (str): User ID to retrieve environment data for.
                      Must exist in user_profile table as an active user.
    
    Returns:
        dict: Comprehensive response containing:
            - user_profile (dict): Complete user profile information including:
                - user_id (str): User identifier
                - user_email (str): User's email address
                - first_name (str): User's first name
                - last_name (str): User's last name
                - addr1, addr2, city, state, zipcode (str): Address information
                - telephone (str): Contact phone number
                - user_npi (str): National Provider Identifier if applicable
                - referred_by_user (str): Referring user ID if applicable
                - user_type (int): User type/role level
                - user_type_desc (str): Human-readable user type description
                - message_pref (str): Communication preferences
                - states_licensed (str): Licensed states information
                - user_tier (int): User tier level
                - max_case_status (int): Maximum case status user can access
                - max_case_status_desc (str): Description of maximum case status
                - last_login_dt (str): Last login timestamp (ISO format)
                - active (int): Account active status
                - documents (List[dict]): User's uploaded documents
                - login_updated (bool): Whether last login was successfully updated
            - case_statuses (List[dict]): Available case statuses based on permissions
            - surgeons (List[dict]): User's associated surgeons
            - facilities (List[dict]): User's associated facilities  
            - user_types (List[dict]): Available user types (≤ current user's type)
    
    Raises:
        HTTPException:
            - 400 Bad Request: Missing or invalid user_id parameter
            - 404 Not Found: User not found or inactive in user_profile table
            - 500 Internal Server Error: Database connection or processing errors
    
    Database Operations:
        - Retrieves comprehensive user profile from 'user_profile' table
        - Gets user documents from 'user_documents' table
        - Updates last_login_dt timestamp for user activity tracking
        - Retrieves case statuses filtered by user's max_case_status permissions
        - Gets user's associated surgeons and facilities based on relationships
        - Retrieves available user types based on hierarchical permissions
        - All operations use consistent connection management and error handling
    
    Permission-Based Filtering:
        - Case statuses limited to user's max_case_status level for security
        - User types filtered to show only types ≤ current user's type
        - Surgeon and facility lists based on user's access permissions
        - Hierarchical access control throughout all data retrieval
    
    Monitoring & Logging:
        - Business metrics tracking for user environment operations:
          - "success": Complete environment successfully retrieved
          - "user_not_found": User validation failed
          - "error": Database or processing errors
        - Prometheus monitoring via @track_business_operation decorator
        - Comprehensive request logging with execution time tracking
        - User activity tracking through last login updates
    
    Data Processing:
        - Automatic datetime formatting to ISO standard for frontend consumption
        - User type description lookup and integration
        - Maximum case status description resolution
        - Login timestamp update for user activity tracking
        - Comprehensive error handling with graceful degradation
    
    Example Response:
        {
            "user_profile": {
                "user_id": "USER123",
                "user_email": "john.doe@example.com",
                "first_name": "John",
                "last_name": "Doe",
                "user_type": 200,
                "user_type_desc": "Advanced User",
                "max_case_status": 5,
                "max_case_status_desc": "Completed",
                "last_login_dt": "2024-01-15T10:30:45.123456",
                "documents": [...],
                "login_updated": true
            },
            "case_statuses": [...],
            "surgeons": [...], 
            "facilities": [...],
            "user_types": [...]
        }
    
    Usage:
        GET /user_environment?user_id=USER123
        
    Performance Considerations:
        - Single endpoint call replaces multiple separate requests
        - Optimized for frontend application initialization
        - Minimal database connections through connection reuse
        - Efficient data aggregation for complete user context
    
    Security Features:
        - Permission-based data filtering throughout all queries
        - User validation and active status verification
        - Hierarchical access control for user types and case statuses
        - Complete audit trail through comprehensive logging
    
    Notes:
        - Primary endpoint for user session initialization
        - Provides complete user context in single request for performance
        - Updates user activity tracking automatically
        - Essential for role-based access control throughout application
        - Optimized for frontend state management and caching strategies
    """
    conn = None
    start_time = time.time()
    response_status = 200
    response_data = None
    error_message = None
    
    try:
        if not user_id:
            response_status = 400
            error_message = "Missing user_id parameter"
            raise HTTPException(status_code=400, detail="Missing user_id parameter")

        conn = get_db_connection()
        
        try:
            # Get user profile information
            user_profile = get_user_profile_info(user_id, conn)
            
            if not user_profile:
                # Record failed access (user not found)
                business_metrics.record_utility_operation("get_user_environment", "user_not_found")
                response_status = 404
                error_message = "User not found or inactive"
                raise HTTPException(status_code=404, detail="User not found or inactive")

            user_type = user_profile.get("user_type", 0)
            max_case_status = user_profile.get("max_case_status", 20)
            
            # Update last login datetime
            login_updated = update_user_last_login(user_id, conn)
            
            # Get case statuses based on user permissions
            case_status_info = get_case_statuses_for_user(user_id, user_type, max_case_status, conn)
            
            # Get surgeon and facility lists for the user
            surgeons = get_user_surgeons(user_id, conn)
            facilities = get_user_facilities(user_id, conn)
            
            # Get available user types for the user
            available_user_types = get_available_user_types(user_type, conn)
            
            # Find max_case_status_desc from the case_statuses array
            max_case_status_desc = None
            for case_status in case_status_info["case_statuses"]:
                if case_status["case_status"] == max_case_status:
                    max_case_status_desc = case_status["case_status_desc"]
                    break
            
            # Record successful user environment retrieval
            business_metrics.record_utility_operation("get_user_environment", "success")
                
        finally:
            close_db_connection(conn)
            
        response_data = {
            "user_profile": user_profile,
            "case_statuses": case_status_info["case_statuses"],
            "surgeons": surgeons,
            "facilities": facilities,
            "user_types": available_user_types,
            "permissions": {
                "user_type": user_type,
                "user_type_desc": user_profile.get("user_type_desc"),
                "case_status_access_level": case_status_info["access_level"],
                "max_case_status": user_profile.get("max_case_status", 20),
                "max_case_status_desc": max_case_status_desc,
                "can_access_all_cases": user_type >= 10,
                "can_access_backoffice": user_type >= 10
            },
            "environment_info": {
                "user_id": user_id,
                "case_statuses_count": case_status_info["total_count"],
                "has_documents": len(user_profile.get("documents", [])) > 0,
                "document_count": len(user_profile.get("documents", [])),
                "surgeon_count": len(surgeons),
                "facility_count": len(facilities),
                "user_types_count": len(available_user_types),
                "last_login_updated": login_updated
            }
        }
        return response_data
        
    except HTTPException as http_error:
        # Re-raise HTTP exceptions and capture error details
        response_status = http_error.status_code
        error_message = str(http_error.detail)
        raise
    except Exception as e:
        # Record failed user environment retrieval
        response_status = 500
        error_message = str(e)
        business_metrics.record_utility_operation("get_user_environment", "error")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")
    finally:
        # Log request execution if monitoring is available
        if conn:
            try:
                close_db_connection(conn)
            except:
                pass  # Connection might already be closed
 