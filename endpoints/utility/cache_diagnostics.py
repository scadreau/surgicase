# Created: 2025-01-27
# Author: Assistant
# Cache diagnostics endpoint for monitoring user environment cache health

from fastapi import APIRouter, Query
from typing import Dict, Any, Optional
import time
from endpoints.utility.get_user_environment import (
    _user_environment_cache,
    _user_environment_cache_lock,
    _user_environment_cache_keys,
    _generate_user_environment_cache_key,
    _is_user_environment_cache_valid
)

router = APIRouter()

@router.get("/cache_diagnostics")
def get_cache_diagnostics(user_id: Optional[str] = Query(None, description="Optional user ID to check specific cache entry")):
    """
    Get diagnostics information about the user environment cache.
    
    This endpoint provides insights into cache health, including:
    - Total cache entries
    - Cache validation status
    - Specific user cache information
    - Cache data integrity checks
    
    Args:
        user_id (str, optional): Specific user ID to check cache for
        
    Returns:
        dict: Cache diagnostic information
    """
    with _user_environment_cache_lock:
        # Basic cache statistics
        total_entries = len(_user_environment_cache)
        data_entries = total_entries // 2  # Divide by 2 because we store data + time keys
        
        diagnostics = {
            "cache_stats": {
                "total_cache_entries": total_entries,
                "estimated_data_entries": data_entries,
                "tracked_users": len(_user_environment_cache_keys),
                "timestamp": time.time()
            },
            "cache_health": {
                "valid_entries": 0,
                "invalid_entries": 0,
                "null_entries": 0,
                "malformed_entries": 0
            }
        }
        
        # Check cache health
        checked_keys = set()
        for key in _user_environment_cache.keys():
            if key.endswith("_time") or key in checked_keys:
                continue
                
            checked_keys.add(key)
            data = _user_environment_cache.get(key)
            
            if data is None:
                diagnostics["cache_health"]["null_entries"] += 1
            elif not isinstance(data, dict):
                diagnostics["cache_health"]["malformed_entries"] += 1
            elif (data.get("user_profile") is None or 
                  data.get("case_statuses") is None):
                diagnostics["cache_health"]["invalid_entries"] += 1
            else:
                diagnostics["cache_health"]["valid_entries"] += 1
        
        # If specific user requested, provide detailed info
        if user_id:
            cache_key = _generate_user_environment_cache_key(user_id)
            user_info = {
                "user_id": user_id,
                "cache_key": cache_key,
                "has_cache_entry": cache_key in _user_environment_cache,
                "has_time_entry": f"{cache_key}_time" in _user_environment_cache,
                "is_cache_valid": _is_user_environment_cache_valid(cache_key),
                "data_type": None,
                "data_structure": None
            }
            
            if cache_key in _user_environment_cache:
                cached_data = _user_environment_cache[cache_key]
                user_info["data_type"] = str(type(cached_data))
                
                if isinstance(cached_data, dict):
                    user_info["data_structure"] = {
                        "keys": list(cached_data.keys()),
                        "user_profile_exists": "user_profile" in cached_data,
                        "case_statuses_exists": "case_statuses" in cached_data,
                        "user_profile_is_null": cached_data.get("user_profile") is None,
                        "case_statuses_is_null": cached_data.get("case_statuses") is None
                    }
            
            diagnostics["user_specific"] = user_info
        
        return diagnostics

@router.post("/clear_cache")
def clear_cache_endpoint(user_id: Optional[str] = Query(None, description="Optional user ID to clear specific cache, or leave empty to clear all")):
    """
    Clear user environment cache entries.
    
    Args:
        user_id (str, optional): Specific user ID to clear, or None to clear all cache
        
    Returns:
        dict: Clear operation results
    """
    from endpoints.utility.get_user_environment import clear_user_environment_cache
    
    if user_id:
        clear_user_environment_cache(user_id)
        return {
            "success": True,
            "action": "cleared_user_cache",
            "user_id": user_id
        }
    else:
        clear_user_environment_cache()
        return {
            "success": True,
            "action": "cleared_all_cache"
        }
