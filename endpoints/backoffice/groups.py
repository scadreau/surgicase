# Created: 2025-11-14 17:30:00
# Last Modified: 2025-11-14 17:36:33
# Author: Scott Cadreau

# endpoints/backoffice/groups.py
from fastapi import APIRouter, HTTPException, Query, Request, Body
import pymysql.cursors
from core.database import get_db_connection, close_db_connection
from utils.monitoring import track_business_operation, business_metrics
from pydantic import BaseModel, Field
from typing import List, Optional
import time
import logging

router = APIRouter()

# ============================================================================
# Pydantic Models
# ============================================================================

class CreateGroupRequest(BaseModel):
    name: str = Field(..., description="Group name")
    admin_user_id: str = Field(..., description="User ID of the group administrator")

class UpdateGroupRequest(BaseModel):
    name: Optional[str] = Field(None, description="New group name")
    active: Optional[bool] = Field(None, description="Active status")

class AddMembersRequest(BaseModel):
    user_ids: List[str] = Field(..., description="List of user IDs to add to the group")

class RemoveMembersRequest(BaseModel):
    user_ids: List[str] = Field(..., description="List of user IDs to remove from the group")

# ============================================================================
# Helper Functions
# ============================================================================

def _validate_backoffice_access(user_id: str, cursor) -> bool:
    """
    Validate if user has backoffice access (user_type >= 10).
    
    Args:
        user_id: The user ID to validate
        cursor: Database cursor
        
    Returns:
        bool: True if user has access, False otherwise
    """
    cursor.execute("""
        SELECT user_type 
        FROM user_profile 
        WHERE user_id = %s AND active = 1
    """, (user_id,))
    
    result = cursor.fetchone()
    if not result:
        return False
    
    return result.get("user_type", 0) >= 10

def _validate_user_exists(user_id: str, cursor) -> bool:
    """Check if a user exists and is active."""
    cursor.execute("""
        SELECT user_id 
        FROM user_profile 
        WHERE user_id = %s AND active = 1
    """, (user_id,))
    
    return cursor.fetchone() is not None

def _get_group_with_details(group_id: int, cursor) -> dict:
    """Get group details including admin info and members."""
    # Get group basic info with admin name
    cursor.execute("""
        SELECT 
            pg.id,
            pg.name,
            pg.admin_user_id,
            CONCAT(COALESCE(up.first_name, ''), ' ', COALESCE(up.last_name, '')) as admin_name,
            up.user_email as admin_email,
            pg.active,
            pg.created_date
        FROM provider_groups pg
        LEFT JOIN user_profile up ON pg.admin_user_id = up.user_id
        WHERE pg.id = %s
    """, (group_id,))
    
    group = cursor.fetchone()
    if not group:
        return None
    
    # Get group members
    cursor.execute("""
        SELECT 
            pgm.user_id,
            CONCAT(COALESCE(up.first_name, ''), ' ', COALESCE(up.last_name, '')) as name,
            up.user_email,
            pgm.added_date
        FROM provider_group_members pgm
        JOIN user_profile up ON pgm.user_id = up.user_id AND up.active = 1
        WHERE pgm.group_id = %s
        ORDER BY up.last_name, up.first_name
    """, (group_id,))
    
    members = cursor.fetchall()
    
    # Convert datetime fields to ISO format
    if group.get("created_date"):
        group["created_date"] = group["created_date"].isoformat()
    
    for member in members:
        if member.get("added_date"):
            member["added_date"] = member["added_date"].isoformat()
    
    group["members"] = members
    group["member_count"] = len(members)
    
    return group

# ============================================================================
# Endpoints
# ============================================================================

@router.get("/groups")
@track_business_operation("list", "groups")
def list_groups(
    request: Request,
    requesting_user_id: str = Query(..., description="User ID making the request")
):
    """
    List all active provider groups.
    
    Returns list of active groups with basic info, admin details, and member counts.
    Used for dropdowns and group management interface.
    
    Args:
        requesting_user_id: User making the request (must have user_type >= 10)
        
    Returns:
        dict: { groups: [...] }
    """
    conn = None
    start_time = time.time()
    response_status = 200
    response_data = None
    error_message = None
    
    try:
        conn = get_db_connection()
        
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            # Validate backoffice access
            if not _validate_backoffice_access(requesting_user_id, cursor):
                response_status = 403
                error_message = "Access denied: insufficient permissions"
                raise HTTPException(status_code=403, detail="Access denied: insufficient permissions")
            
            # Get all active groups with admin info and member counts
            cursor.execute("""
                SELECT 
                    pg.id,
                    pg.name,
                    pg.admin_user_id,
                    CONCAT(COALESCE(up.first_name, ''), ' ', COALESCE(up.last_name, '')) as admin_name,
                    up.user_email as admin_email,
                    pg.created_date,
                    COUNT(DISTINCT pgm.user_id) as member_count
                FROM provider_groups pg
                LEFT JOIN user_profile up ON pg.admin_user_id = up.user_id
                LEFT JOIN provider_group_members pgm ON pg.id = pgm.group_id
                WHERE pg.active = 1
                GROUP BY pg.id, pg.name, pg.admin_user_id, up.first_name, up.last_name, up.user_email, pg.created_date
                ORDER BY pg.name
            """)
            
            groups = cursor.fetchall()
            
            # Convert datetime to ISO format
            for group in groups:
                if group.get("created_date"):
                    group["created_date"] = group["created_date"].isoformat()
            
            business_metrics.record_utility_operation("list_groups", "success")
            
            response_data = {"groups": groups}
            return response_data
            
    except HTTPException:
        raise
    except Exception as e:
        response_status = 500
        error_message = str(e)
        business_metrics.record_utility_operation("list_groups", "error")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")
    finally:
        if conn:
            close_db_connection(conn)
        
        execution_time_ms = int((time.time() - start_time) * 1000)
        from endpoints.utility.log_request import log_request_from_endpoint
        log_request_from_endpoint(
            request=request,
            execution_time_ms=execution_time_ms,
            response_status=response_status,
            user_id=requesting_user_id,
            response_data=response_data,
            error_message=error_message
        )

@router.post("/groups")
@track_business_operation("create", "group")
def create_group(
    request: Request,
    requesting_user_id: str = Query(..., description="User ID making the request"),
    body: CreateGroupRequest = Body(...)
):
    """
    Create a new provider group with an assigned administrator.
    
    Args:
        requesting_user_id: User making the request (must have user_type >= 10)
        body: { name, admin_user_id }
        
    Returns:
        dict: Created group object
    """
    conn = None
    start_time = time.time()
    response_status = 200
    response_data = None
    error_message = None
    
    try:
        conn = get_db_connection()
        
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            # Validate backoffice access
            if not _validate_backoffice_access(requesting_user_id, cursor):
                response_status = 403
                error_message = "Access denied: insufficient permissions"
                raise HTTPException(status_code=403, detail="Access denied: insufficient permissions")
            
            # Validate admin user exists
            if not _validate_user_exists(body.admin_user_id, cursor):
                response_status = 400
                error_message = f"Admin user {body.admin_user_id} not found or inactive"
                raise HTTPException(status_code=400, detail=f"Admin user {body.admin_user_id} not found or inactive")
            
            # Create group - unique constraint on admin_user_id will catch duplicates
            try:
                cursor.execute("""
                    INSERT INTO provider_groups (name, admin_user_id, active, created_date)
                    VALUES (%s, %s, 1, CURRENT_TIMESTAMP)
                """, (body.name, body.admin_user_id))
                
                conn.commit()
                group_id = cursor.lastrowid
                
                # Get the created group with details
                group = _get_group_with_details(group_id, cursor)
                
                business_metrics.record_utility_operation("create_group", "success")
                
                response_data = {"group": group}
                return response_data
                
            except pymysql.IntegrityError as e:
                conn.rollback()
                response_status = 400
                error_message = f"Admin user is already assigned to another group"
                raise HTTPException(status_code=400, detail="Admin user is already assigned to another group")
            
    except HTTPException:
        raise
    except Exception as e:
        if conn:
            conn.rollback()
        response_status = 500
        error_message = str(e)
        business_metrics.record_utility_operation("create_group", "error")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")
    finally:
        if conn:
            close_db_connection(conn)
        
        execution_time_ms = int((time.time() - start_time) * 1000)
        from endpoints.utility.log_request import log_request_from_endpoint
        log_request_from_endpoint(
            request=request,
            execution_time_ms=execution_time_ms,
            response_status=response_status,
            user_id=requesting_user_id,
            response_data=response_data,
            error_message=error_message
        )

@router.get("/groups/{group_id}")
@track_business_operation("get", "group")
def get_group(
    request: Request,
    group_id: int,
    requesting_user_id: str = Query(..., description="User ID making the request")
):
    """
    Get detailed information about a specific group.
    
    Returns full group details including member list.
    
    Args:
        group_id: ID of the group to retrieve
        requesting_user_id: User making the request (must have user_type >= 10)
        
    Returns:
        dict: Complete group object with members
    """
    conn = None
    start_time = time.time()
    response_status = 200
    response_data = None
    error_message = None
    
    try:
        conn = get_db_connection()
        
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            # Validate backoffice access
            if not _validate_backoffice_access(requesting_user_id, cursor):
                response_status = 403
                error_message = "Access denied: insufficient permissions"
                raise HTTPException(status_code=403, detail="Access denied: insufficient permissions")
            
            # Get group details
            group = _get_group_with_details(group_id, cursor)
            
            if not group:
                response_status = 404
                error_message = f"Group {group_id} not found"
                raise HTTPException(status_code=404, detail=f"Group {group_id} not found")
            
            business_metrics.record_utility_operation("get_group", "success")
            
            response_data = {"group": group}
            return response_data
            
    except HTTPException:
        raise
    except Exception as e:
        response_status = 500
        error_message = str(e)
        business_metrics.record_utility_operation("get_group", "error")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")
    finally:
        if conn:
            close_db_connection(conn)
        
        execution_time_ms = int((time.time() - start_time) * 1000)
        from endpoints.utility.log_request import log_request_from_endpoint
        log_request_from_endpoint(
            request=request,
            execution_time_ms=execution_time_ms,
            response_status=response_status,
            user_id=requesting_user_id,
            response_data=response_data,
            error_message=error_message
        )

@router.put("/groups/{group_id}")
@track_business_operation("update", "group")
def update_group(
    request: Request,
    group_id: int,
    requesting_user_id: str = Query(..., description="User ID making the request"),
    body: UpdateGroupRequest = Body(...)
):
    """
    Update a group's name or active status.
    
    Note: Admin cannot be changed - new admin requires new group.
    
    Args:
        group_id: ID of the group to update
        requesting_user_id: User making the request (must have user_type >= 10)
        body: { name (optional), active (optional) }
        
    Returns:
        dict: Updated group object
    """
    conn = None
    start_time = time.time()
    response_status = 200
    response_data = None
    error_message = None
    
    try:
        conn = get_db_connection()
        
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            # Validate backoffice access
            if not _validate_backoffice_access(requesting_user_id, cursor):
                response_status = 403
                error_message = "Access denied: insufficient permissions"
                raise HTTPException(status_code=403, detail="Access denied: insufficient permissions")
            
            # Check if group exists
            cursor.execute("SELECT id FROM provider_groups WHERE id = %s", (group_id,))
            if not cursor.fetchone():
                response_status = 404
                error_message = f"Group {group_id} not found"
                raise HTTPException(status_code=404, detail=f"Group {group_id} not found")
            
            # Build update query dynamically based on provided fields
            updates = []
            params = []
            
            if body.name is not None:
                updates.append("name = %s")
                params.append(body.name)
            
            if body.active is not None:
                updates.append("active = %s")
                params.append(1 if body.active else 0)
            
            if not updates:
                response_status = 400
                error_message = "No fields to update"
                raise HTTPException(status_code=400, detail="No fields to update")
            
            # Execute update
            params.append(group_id)
            cursor.execute(f"""
                UPDATE provider_groups 
                SET {', '.join(updates)}
                WHERE id = %s
            """, params)
            
            conn.commit()
            
            # Get updated group
            group = _get_group_with_details(group_id, cursor)
            
            business_metrics.record_utility_operation("update_group", "success")
            
            response_data = {"group": group}
            return response_data
            
    except HTTPException:
        raise
    except Exception as e:
        if conn:
            conn.rollback()
        response_status = 500
        error_message = str(e)
        business_metrics.record_utility_operation("update_group", "error")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")
    finally:
        if conn:
            close_db_connection(conn)
        
        execution_time_ms = int((time.time() - start_time) * 1000)
        from endpoints.utility.log_request import log_request_from_endpoint
        log_request_from_endpoint(
            request=request,
            execution_time_ms=execution_time_ms,
            response_status=response_status,
            user_id=requesting_user_id,
            response_data=response_data,
            error_message=error_message
        )

@router.delete("/groups/{group_id}")
@track_business_operation("delete", "group")
def delete_group(
    request: Request,
    group_id: int,
    requesting_user_id: str = Query(..., description="User ID making the request")
):
    """
    Soft delete a group by setting active = 0.
    
    Providers remain in the system, membership records are preserved.
    
    Args:
        group_id: ID of the group to delete
        requesting_user_id: User making the request (must have user_type >= 10)
        
    Returns:
        dict: Success message
    """
    conn = None
    start_time = time.time()
    response_status = 200
    response_data = None
    error_message = None
    
    try:
        conn = get_db_connection()
        
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            # Validate backoffice access
            if not _validate_backoffice_access(requesting_user_id, cursor):
                response_status = 403
                error_message = "Access denied: insufficient permissions"
                raise HTTPException(status_code=403, detail="Access denied: insufficient permissions")
            
            # Check if group exists
            cursor.execute("SELECT id FROM provider_groups WHERE id = %s", (group_id,))
            if not cursor.fetchone():
                response_status = 404
                error_message = f"Group {group_id} not found"
                raise HTTPException(status_code=404, detail=f"Group {group_id} not found")
            
            # Soft delete
            cursor.execute("""
                UPDATE provider_groups 
                SET active = 0 
                WHERE id = %s
            """, (group_id,))
            
            conn.commit()
            
            business_metrics.record_utility_operation("delete_group", "success")
            
            response_data = {"message": f"Group {group_id} deactivated successfully"}
            return response_data
            
    except HTTPException:
        raise
    except Exception as e:
        if conn:
            conn.rollback()
        response_status = 500
        error_message = str(e)
        business_metrics.record_utility_operation("delete_group", "error")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")
    finally:
        if conn:
            close_db_connection(conn)
        
        execution_time_ms = int((time.time() - start_time) * 1000)
        from endpoints.utility.log_request import log_request_from_endpoint
        log_request_from_endpoint(
            request=request,
            execution_time_ms=execution_time_ms,
            response_status=response_status,
            user_id=requesting_user_id,
            response_data=response_data,
            error_message=error_message
        )

@router.post("/groups/{group_id}/members")
@track_business_operation("add", "group_members")
def add_group_members(
    request: Request,
    group_id: int,
    requesting_user_id: str = Query(..., description="User ID making the request"),
    body: AddMembersRequest = Body(...)
):
    """
    Add multiple providers to a group (batch operation).
    
    Skips:
    - Users that don't exist
    - Users already in the group (duplicates)
    - The admin user (if included)
    
    Args:
        group_id: ID of the group
        requesting_user_id: User making the request (must have user_type >= 10)
        body: { user_ids: ["user1", "user2", ...] }
        
    Returns:
        dict: { added_count, skipped_count, skipped_users: [...] }
    """
    conn = None
    start_time = time.time()
    response_status = 200
    response_data = None
    error_message = None
    
    try:
        conn = get_db_connection()
        
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            # Validate backoffice access
            if not _validate_backoffice_access(requesting_user_id, cursor):
                response_status = 403
                error_message = "Access denied: insufficient permissions"
                raise HTTPException(status_code=403, detail="Access denied: insufficient permissions")
            
            # Check if group exists and get admin_user_id
            cursor.execute("""
                SELECT id, admin_user_id 
                FROM provider_groups 
                WHERE id = %s
            """, (group_id,))
            
            group = cursor.fetchone()
            if not group:
                response_status = 404
                error_message = f"Group {group_id} not found"
                raise HTTPException(status_code=404, detail=f"Group {group_id} not found")
            
            admin_user_id = group.get("admin_user_id")
            
            added_count = 0
            skipped_count = 0
            skipped_users = []
            
            for user_id in body.user_ids:
                # Skip admin user
                if user_id == admin_user_id:
                    skipped_count += 1
                    skipped_users.append({"user_id": user_id, "reason": "Cannot add admin as member"})
                    continue
                
                # Check if user exists
                if not _validate_user_exists(user_id, cursor):
                    skipped_count += 1
                    skipped_users.append({"user_id": user_id, "reason": "User not found or inactive"})
                    continue
                
                # Try to add - will skip if already exists (duplicate key)
                try:
                    cursor.execute("""
                        INSERT INTO provider_group_members (user_id, group_id, added_date)
                        VALUES (%s, %s, CURRENT_TIMESTAMP)
                    """, (user_id, group_id))
                    added_count += 1
                except pymysql.IntegrityError:
                    # Duplicate - user already in group
                    skipped_count += 1
                    skipped_users.append({"user_id": user_id, "reason": "Already in group"})
            
            conn.commit()
            
            business_metrics.record_utility_operation("add_group_members", "success")
            
            response_data = {
                "added_count": added_count,
                "skipped_count": skipped_count,
                "skipped_users": skipped_users
            }
            return response_data
            
    except HTTPException:
        raise
    except Exception as e:
        if conn:
            conn.rollback()
        response_status = 500
        error_message = str(e)
        business_metrics.record_utility_operation("add_group_members", "error")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")
    finally:
        if conn:
            close_db_connection(conn)
        
        execution_time_ms = int((time.time() - start_time) * 1000)
        from endpoints.utility.log_request import log_request_from_endpoint
        log_request_from_endpoint(
            request=request,
            execution_time_ms=execution_time_ms,
            response_status=response_status,
            user_id=requesting_user_id,
            response_data=response_data,
            error_message=error_message
        )

@router.delete("/groups/{group_id}/members")
@track_business_operation("remove", "group_members")
def remove_group_members(
    request: Request,
    group_id: int,
    requesting_user_id: str = Query(..., description="User ID making the request"),
    body: RemoveMembersRequest = Body(...)
):
    """
    Remove multiple providers from a group (batch operation).
    
    Args:
        group_id: ID of the group
        requesting_user_id: User making the request (must have user_type >= 10)
        body: { user_ids: ["user1", "user2", ...] }
        
    Returns:
        dict: { removed_count }
    """
    conn = None
    start_time = time.time()
    response_status = 200
    response_data = None
    error_message = None
    
    try:
        conn = get_db_connection()
        
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            # Validate backoffice access
            if not _validate_backoffice_access(requesting_user_id, cursor):
                response_status = 403
                error_message = "Access denied: insufficient permissions"
                raise HTTPException(status_code=403, detail="Access denied: insufficient permissions")
            
            # Check if group exists
            cursor.execute("SELECT id FROM provider_groups WHERE id = %s", (group_id,))
            if not cursor.fetchone():
                response_status = 404
                error_message = f"Group {group_id} not found"
                raise HTTPException(status_code=404, detail=f"Group {group_id} not found")
            
            # Remove all specified users in one query
            if body.user_ids:
                placeholders = ','.join(['%s'] * len(body.user_ids))
                cursor.execute(f"""
                    DELETE FROM provider_group_members 
                    WHERE group_id = %s AND user_id IN ({placeholders})
                """, [group_id] + body.user_ids)
                
                removed_count = cursor.rowcount
                conn.commit()
            else:
                removed_count = 0
            
            business_metrics.record_utility_operation("remove_group_members", "success")
            
            response_data = {"removed_count": removed_count}
            return response_data
            
    except HTTPException:
        raise
    except Exception as e:
        if conn:
            conn.rollback()
        response_status = 500
        error_message = str(e)
        business_metrics.record_utility_operation("remove_group_members", "error")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")
    finally:
        if conn:
            close_db_connection(conn)
        
        execution_time_ms = int((time.time() - start_time) * 1000)
        from endpoints.utility.log_request import log_request_from_endpoint
        log_request_from_endpoint(
            request=request,
            execution_time_ms=execution_time_ms,
            response_status=response_status,
            user_id=requesting_user_id,
            response_data=response_data,
            error_message=error_message
        )

