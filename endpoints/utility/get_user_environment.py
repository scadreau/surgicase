# Created: 2025-07-24 17:54:30
# Last Modified: 2025-07-24 19:36:15
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

@router.get("/user_environment")
@track_business_operation("get", "user_environment")
def get_user_environment(request: Request, user_id: str = Query(..., description="The user ID to get environment for")):
    """
    Get complete user environment including user profile and case statuses.
    This provides all the information the frontend needs about a user in one call.
    
    Returns:
        - User profile information
        - Available case statuses based on user permissions
        - User access levels and capabilities
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
            
            # Record successful user environment retrieval
            business_metrics.record_utility_operation("get_user_environment", "success")
                
        finally:
            close_db_connection(conn)
            
        response_data = {
            "user_profile": user_profile,
            "case_statuses": case_status_info["case_statuses"],
            "surgeons": surgeons,
            "facilities": facilities,
            "permissions": {
                "user_type": user_type,
                "case_status_access_level": case_status_info["access_level"],
                "max_case_status": user_profile.get("max_case_status", 20),
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
 