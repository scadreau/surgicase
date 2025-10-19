# Created: 2025-10-19
# Last Modified: 2025-10-19 23:40:46
# Author: Scott Cadreau

# endpoints/admin/encryption_key_management.py
from fastapi import APIRouter, HTTPException, Query, Request
from typing import Dict, Any, Optional
import time
import logging
import pymysql.cursors

from core.database import get_db_connection, close_db_connection
from utils.monitoring import track_business_operation
from utils.phi_encryption import (
    generate_and_store_user_key,
    get_cache_stats,
    clear_dek_cache
)

router = APIRouter()
logger = logging.getLogger(__name__)


def validate_admin_access(user_id: str, conn) -> bool:
    """
    Validate that the user has user_type >= 100 (admin) to access encryption endpoints.
    
    Args:
        user_id: User ID to validate
        conn: Database connection
        
    Returns:
        True if authorized
        
    Raises:
        HTTPException if not authorized
    """
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute(
                "SELECT user_type FROM user_profile WHERE user_id = %s AND active = 1",
                (user_id,)
            )
            user = cursor.fetchone()
            
            if not user:
                raise HTTPException(status_code=404, detail={"error": "User not found or inactive"})
            
            if user['user_type'] < 100:
                raise HTTPException(status_code=403, detail={"error": "Insufficient privileges. Admin access required (user_type >= 100)"})
            
            return True
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail={"error": f"Error validating user access: {str(e)}"})


@router.post("/admin/encryption/generate-key")
@track_business_operation("admin", "encryption_generate_key")
def generate_user_encryption_key(
    request: Request,
    user_id: str = Query(..., description="The user ID to generate an encryption key for"),
    admin_user_id: str = Query(..., description="Admin user ID performing this operation")
) -> Dict[str, Any]:
    """
    Generate a new encryption key for a specific user - administrative endpoint.
    
    This endpoint generates a new per-user data encryption key (DEK) using AWS KMS
    and stores it in the database for PHI field encryption.
    
    **Administrative Access Required:**
    - Requesting user must have user_type >= 100
    - Operation is logged for HIPAA compliance
    
    **Parameters:**
    - `user_id`: The user ID to generate an encryption key for (required)
    - `admin_user_id`: Admin user ID performing this operation (required)
    
    **Response:**
    - `success`: Boolean indicating operation success
    - `user_id`: The user ID that received the key
    - `key_version`: Version number of the generated key
    - `message`: Status message
    - `execution_time_ms`: Total execution time
    
    **Example Response:**
    ```json
    {
        "success": true,
        "user_id": "USER123",
        "key_version": 1,
        "message": "Encryption key generated successfully",
        "execution_time_ms": 245
    }
    ```
    
    **HTTP Status Codes:**
    - `200`: Success - Encryption key generated
    - `400`: Bad Request - Invalid parameters
    - `403`: Forbidden - Insufficient privileges
    - `404`: Not Found - User not found
    - `500`: Internal server error - Key generation failed
    
    **Use Cases:**
    - Generate keys for newly created users
    - Regenerate keys after security incident
    - Initial key generation during system migration
    
    **Notes:**
    - If user already has a key, this will rotate it (increment version)
    - Operation is audited in encryption_key_audit table
    - DEK cache is cleared for this user after generation
    """
    start_time = time.time()
    conn = None
    
    try:
        # Input validation
        if not user_id or not user_id.strip():
            raise HTTPException(status_code=400, detail={"error": "Invalid user_id parameter"})
        if not admin_user_id or not admin_user_id.strip():
            raise HTTPException(status_code=400, detail={"error": "Invalid admin_user_id parameter"})
        
        user_id = user_id.strip()
        admin_user_id = admin_user_id.strip()
        
        # Get client IP
        client_ip = request.client.host if request.client else None
        
        # Connect to database
        conn = get_db_connection()
        
        # Validate admin access
        validate_admin_access(admin_user_id, conn)
        
        # Validate target user exists
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute(
                "SELECT user_id FROM user_profile WHERE user_id = %s AND active = 1",
                (user_id,)
            )
            if not cursor.fetchone():
                raise HTTPException(status_code=404, detail={"error": f"Target user not found: {user_id}"})
        
        # Generate encryption key
        logger.info(f"Admin {admin_user_id} generating encryption key for user {user_id}")
        result = generate_and_store_user_key(
            user_id=user_id,
            conn=conn,
            performed_by=admin_user_id,
            ip_address=client_ip
        )
        
        # Add execution time
        result['execution_time_ms'] = int((time.time() - start_time) * 1000)
        
        logger.info(f"Successfully generated encryption key for user {user_id} in {result['execution_time_ms']}ms")
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating encryption key for user {user_id}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail={"error": f"Encryption key generation failed: {str(e)}"}
        )
    finally:
        if conn:
            close_db_connection(conn)


@router.get("/admin/encryption/key-status")
@track_business_operation("admin", "encryption_key_status")
def get_encryption_key_status(
    request: Request,
    admin_user_id: str = Query(..., description="Admin user ID requesting status"),
    target_user_id: Optional[str] = Query(None, description="Optional: specific user to check (if not provided, returns overall stats)")
) -> Dict[str, Any]:
    """
    Get encryption key status for users - administrative endpoint.
    
    This endpoint provides information about encryption key coverage and status.
    Can query overall statistics or check a specific user's key status.
    
    **Administrative Access Required:**
    - Requesting user must have user_type >= 100
    
    **Parameters:**
    - `admin_user_id`: Admin user ID requesting status (required)
    - `target_user_id`: Optional user ID to check specific key status
    
    **Response (Overall Stats):**
    ```json
    {
        "total_active_users": 110,
        "users_with_keys": 108,
        "users_without_keys": 2,
        "coverage_percentage": 98.18,
        "cache_stats": {
            "total_cached": 15,
            "active_count": 15,
            "expired_count": 0,
            "cache_ttl_hours": 24
        }
    }
    ```
    
    **Response (Specific User):**
    ```json
    {
        "user_id": "USER123",
        "has_key": true,
        "key_version": 1,
        "created_at": "2025-10-19T12:00:00",
        "rotated_at": null,
        "is_active": true,
        "is_cached": true
    }
    ```
    
    **HTTP Status Codes:**
    - `200`: Success - Status retrieved
    - `403`: Forbidden - Insufficient privileges
    - `404`: Not Found - Target user not found
    - `500`: Internal server error - Failed to retrieve status
    
    **Use Cases:**
    - Monitor encryption key coverage across users
    - Verify specific user has encryption key
    - Check cache performance
    - Audit key management status
    """
    conn = None
    
    try:
        # Input validation
        if not admin_user_id or not admin_user_id.strip():
            raise HTTPException(status_code=400, detail={"error": "Invalid admin_user_id parameter"})
        
        admin_user_id = admin_user_id.strip()
        
        # Connect to database
        conn = get_db_connection()
        
        # Validate admin access
        validate_admin_access(admin_user_id, conn)
        
        if target_user_id:
            # Get status for specific user
            target_user_id = target_user_id.strip()
            
            with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                # Check if user exists
                cursor.execute(
                    "SELECT user_id FROM user_profile WHERE user_id = %s AND active = 1",
                    (target_user_id,)
                )
                if not cursor.fetchone():
                    raise HTTPException(status_code=404, detail={"error": f"User not found: {target_user_id}"})
                
                # Get encryption key info
                cursor.execute("""
                    SELECT user_id, key_version, created_at, rotated_at, is_active
                    FROM user_encryption_keys
                    WHERE user_id = %s
                """, (target_user_id,))
                
                key_info = cursor.fetchone()
                
                # Check if key is cached
                cache_stats = get_cache_stats()
                is_cached = target_user_id in str(cache_stats)  # Simplified check
                
                if key_info:
                    return {
                        "user_id": target_user_id,
                        "has_key": True,
                        "key_version": key_info['key_version'],
                        "created_at": key_info['created_at'].isoformat() if key_info['created_at'] else None,
                        "rotated_at": key_info['rotated_at'].isoformat() if key_info['rotated_at'] else None,
                        "is_active": bool(key_info['is_active']),
                        "is_cached": is_cached
                    }
                else:
                    return {
                        "user_id": target_user_id,
                        "has_key": False,
                        "message": "No encryption key found for this user"
                    }
        else:
            # Get overall statistics
            with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                # Total active users
                cursor.execute("SELECT COUNT(*) as count FROM user_profile WHERE active = 1")
                total_users = cursor.fetchone()['count']
                
                # Users with keys
                cursor.execute("""
                    SELECT COUNT(*) as count 
                    FROM user_encryption_keys uek
                    JOIN user_profile up ON uek.user_id = up.user_id
                    WHERE up.active = 1 AND uek.is_active = 1
                """)
                users_with_keys = cursor.fetchone()['count']
                
                # Users without keys
                users_without_keys = total_users - users_with_keys
                coverage_percentage = round((users_with_keys / total_users * 100) if total_users > 0 else 0, 2)
                
                # Get cache stats
                cache_stats = get_cache_stats()
                
                return {
                    "total_active_users": total_users,
                    "users_with_keys": users_with_keys,
                    "users_without_keys": users_without_keys,
                    "coverage_percentage": coverage_percentage,
                    "cache_stats": cache_stats
                }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting encryption key status: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail={"error": f"Failed to retrieve encryption key status: {str(e)}"}
        )
    finally:
        if conn:
            close_db_connection(conn)


@router.post("/admin/encryption/clear-cache")
@track_business_operation("admin", "encryption_clear_cache")
def clear_encryption_cache(
    request: Request,
    admin_user_id: str = Query(..., description="Admin user ID performing this operation"),
    target_user_id: Optional[str] = Query(None, description="Optional: specific user to clear cache for (if not provided, clears all)")
) -> Dict[str, Any]:
    """
    Clear the DEK cache - administrative endpoint.
    
    This endpoint clears the in-memory cache of decrypted data encryption keys.
    Can clear cache for a specific user or all users.
    
    **Administrative Access Required:**
    - Requesting user must have user_type >= 100
    
    **Parameters:**
    - `admin_user_id`: Admin user ID performing this operation (required)
    - `target_user_id`: Optional user ID to clear cache for (if not provided, clears all)
    
    **Response:**
    ```json
    {
        "success": true,
        "action": "cleared_all" | "cleared_user",
        "target_user_id": "USER123",
        "message": "DEK cache cleared successfully",
        "cache_stats_after": {
            "total_cached": 0,
            "active_count": 0
        }
    }
    ```
    
    **HTTP Status Codes:**
    - `200`: Success - Cache cleared
    - `403`: Forbidden - Insufficient privileges
    - `500`: Internal server error - Cache clearing failed
    
    **Use Cases:**
    - Force reload of encryption keys after rotation
    - Clear stale keys from memory
    - Troubleshooting encryption issues
    - Security incident response
    
    **Notes:**
    - Keys will be automatically re-cached on next use
    - Small performance impact on next encryption/decryption
    - Cache will repopulate naturally as users access data
    """
    conn = None
    
    try:
        # Input validation
        if not admin_user_id or not admin_user_id.strip():
            raise HTTPException(status_code=400, detail={"error": "Invalid admin_user_id parameter"})
        
        admin_user_id = admin_user_id.strip()
        
        # Connect to database
        conn = get_db_connection()
        
        # Validate admin access
        validate_admin_access(admin_user_id, conn)
        
        if target_user_id:
            # Clear cache for specific user
            target_user_id = target_user_id.strip()
            logger.info(f"Admin {admin_user_id} clearing DEK cache for user {target_user_id}")
            clear_dek_cache(target_user_id)
            
            result = {
                "success": True,
                "action": "cleared_user",
                "target_user_id": target_user_id,
                "message": f"DEK cache cleared for user {target_user_id}"
            }
        else:
            # Clear all caches
            logger.info(f"Admin {admin_user_id} clearing all DEK caches")
            clear_dek_cache()
            
            result = {
                "success": True,
                "action": "cleared_all",
                "message": "All DEK caches cleared"
            }
        
        # Get cache stats after clearing
        result["cache_stats_after"] = get_cache_stats()
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error clearing DEK cache: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail={"error": f"Failed to clear DEK cache: {str(e)}"}
        )
    finally:
        if conn:
            close_db_connection(conn)


@router.get("/admin/encryption/audit-log")
@track_business_operation("admin", "encryption_audit_log")
def get_encryption_audit_log(
    request: Request,
    admin_user_id: str = Query(..., description="Admin user ID requesting audit log"),
    target_user_id: Optional[str] = Query(None, description="Optional: filter by specific user"),
    limit: int = Query(100, description="Maximum number of records to return", ge=1, le=1000)
) -> Dict[str, Any]:
    """
    Get encryption key audit log - administrative endpoint.
    
    This endpoint retrieves the audit trail of all encryption key operations
    for HIPAA compliance and security monitoring.
    
    **Administrative Access Required:**
    - Requesting user must have user_type >= 100
    
    **Parameters:**
    - `admin_user_id`: Admin user ID requesting audit log (required)
    - `target_user_id`: Optional user ID to filter logs
    - `limit`: Maximum number of records to return (default: 100, max: 1000)
    
    **Response:**
    ```json
    {
        "total_records": 245,
        "returned_records": 100,
        "audit_entries": [
            {
                "audit_id": 1,
                "user_id": "USER123",
                "operation": "generate",
                "performed_by": "ADMIN456",
                "operation_timestamp": "2025-10-19T12:00:00",
                "details": {"operation": "generate_key", "key_version": 1},
                "ip_address": "192.168.1.1"
            }
        ]
    }
    ```
    
    **HTTP Status Codes:**
    - `200`: Success - Audit log retrieved
    - `403`: Forbidden - Insufficient privileges
    - `500`: Internal server error - Failed to retrieve audit log
    
    **Use Cases:**
    - HIPAA compliance auditing
    - Security incident investigation
    - Key operation monitoring
    - Access pattern analysis
    """
    conn = None
    
    try:
        # Input validation
        if not admin_user_id or not admin_user_id.strip():
            raise HTTPException(status_code=400, detail={"error": "Invalid admin_user_id parameter"})
        
        admin_user_id = admin_user_id.strip()
        
        # Connect to database
        conn = get_db_connection()
        
        # Validate admin access
        validate_admin_access(admin_user_id, conn)
        
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            if target_user_id:
                target_user_id = target_user_id.strip()
                # Get audit log for specific user
                cursor.execute("""
                    SELECT audit_id, user_id, operation, performed_by, 
                           operation_timestamp, details, ip_address
                    FROM encryption_key_audit
                    WHERE user_id = %s
                    ORDER BY operation_timestamp DESC
                    LIMIT %s
                """, (target_user_id, limit))
            else:
                # Get audit log for all users
                cursor.execute("""
                    SELECT audit_id, user_id, operation, performed_by, 
                           operation_timestamp, details, ip_address
                    FROM encryption_key_audit
                    ORDER BY operation_timestamp DESC
                    LIMIT %s
                """, (limit,))
            
            audit_entries = cursor.fetchall()
            
            # Get total count
            if target_user_id:
                cursor.execute("SELECT COUNT(*) as count FROM encryption_key_audit WHERE user_id = %s", (target_user_id,))
            else:
                cursor.execute("SELECT COUNT(*) as count FROM encryption_key_audit")
            
            total_count = cursor.fetchone()['count']
            
            # Format dates and parse JSON details
            for entry in audit_entries:
                if entry['operation_timestamp']:
                    entry['operation_timestamp'] = entry['operation_timestamp'].isoformat()
                if entry['details']:
                    try:
                        import json
                        entry['details'] = json.loads(entry['details'])
                    except:
                        pass  # Leave as string if JSON parsing fails
            
            return {
                "total_records": total_count,
                "returned_records": len(audit_entries),
                "audit_entries": audit_entries
            }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving encryption audit log: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail={"error": f"Failed to retrieve encryption audit log: {str(e)}"}
        )
    finally:
        if conn:
            close_db_connection(conn)

