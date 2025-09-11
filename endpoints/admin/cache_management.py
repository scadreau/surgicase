# Created: 2025-09-11 
# Last Modified: 2025-09-11 22:54:16
# Author: Scott Cadreau

# endpoints/admin/cache_management.py
from fastapi import APIRouter, HTTPException, Query, Request
from typing import Dict, Any, Optional
import time
import logging

from utils.monitoring import track_business_operation

router = APIRouter()
logger = logging.getLogger(__name__)

@router.post("/admin/cache/clear-all")
@track_business_operation("admin", "cache_clear_all")
def clear_all_caches(request: Request) -> Dict[str, Any]:
    """
    Clear all application caches - administrative endpoint.
    
    This endpoint provides comprehensive cache clearing across all cache types
    in the SurgiCase application. It clears secrets cache, user environment cache,
    user cases cache, and global cases cache.
    
    **Administrative Access Required:**
    - This endpoint is intended for administrative use
    - Should be used during maintenance or troubleshooting
    
    **Cache Types Cleared:**
    - AWS Secrets Manager Cache: All cached secrets
    - User Environment Cache: All user profile and permission data
    - User Cases Cache: All filtered case data per user
    - Global Cases Cache: Administrative case data
    
    **Response:**
    - `timestamp`: ISO timestamp of the operation
    - `operations`: Array of cache clearing results
    - `summary`: Success/failure counts
    - `execution_time_ms`: Total execution time
    
    **Example Response:**
    ```json
    {
        "timestamp": "2025-09-11T22:45:00.000Z",
        "operations": [
            {"cache_type": "secrets", "status": "success", "action": "clear_all_secrets"},
            {"cache_type": "user_environment", "status": "success", "action": "clear_all_user_environment"},
            {"cache_type": "user_cases", "status": "success", "action": "clear_all_user_cases"},
            {"cache_type": "global_cases", "status": "success", "action": "clear_global_cases"}
        ],
        "summary": {"successful": 4, "failed": 0},
        "execution_time_ms": 125
    }
    ```
    
    **HTTP Status Codes:**
    - `200`: Success - All caches cleared successfully
    - `500`: Internal server error - One or more cache operations failed
    
    **Use Cases:**
    - System maintenance and troubleshooting
    - Force refresh of stale cached data
    - Clear caches after configuration changes
    - Performance optimization during low-traffic periods
    
    **Notes:**
    - Cache warming will occur automatically on next access
    - Some operations may take several seconds to complete
    - Monitor application performance after cache clearing
    """
    start_time = time.time()
    
    try:
        results = {
            "timestamp": time.time(),
            "operations": [],
            "summary": {"successful": 0, "failed": 0}
        }
        
        # Clear secrets cache
        try:
            from utils.secrets_manager import clear_secrets_cache
            clear_secrets_cache()
            results["operations"].append({
                "cache_type": "secrets", 
                "status": "success", 
                "action": "clear_all_secrets"
            })
            results["summary"]["successful"] += 1
            logger.info("Successfully cleared secrets cache")
        except Exception as e:
            results["operations"].append({
                "cache_type": "secrets", 
                "status": "error", 
                "error": str(e)
            })
            results["summary"]["failed"] += 1
            logger.error(f"Failed to clear secrets cache: {str(e)}")
        
        # Clear user environment cache
        try:
            from endpoints.utility.get_user_environment import clear_user_environment_cache
            clear_user_environment_cache()
            results["operations"].append({
                "cache_type": "user_environment", 
                "status": "success", 
                "action": "clear_all_user_environment"
            })
            results["summary"]["successful"] += 1
            logger.info("Successfully cleared user environment cache")
        except Exception as e:
            results["operations"].append({
                "cache_type": "user_environment", 
                "status": "error", 
                "error": str(e)
            })
            results["summary"]["failed"] += 1
            logger.error(f"Failed to clear user environment cache: {str(e)}")
        
        # Clear user cases cache
        try:
            from endpoints.case.filter_cases import clear_user_cases_cache
            clear_user_cases_cache()
            results["operations"].append({
                "cache_type": "user_cases", 
                "status": "success", 
                "action": "clear_all_user_cases"
            })
            results["summary"]["successful"] += 1
            logger.info("Successfully cleared user cases cache")
        except Exception as e:
            results["operations"].append({
                "cache_type": "user_cases", 
                "status": "error", 
                "error": str(e)
            })
            results["summary"]["failed"] += 1
            logger.error(f"Failed to clear user cases cache: {str(e)}")
        
        # Clear global cases cache
        try:
            from endpoints.backoffice.get_cases_by_status import clear_cases_cache
            clear_cases_cache()
            results["operations"].append({
                "cache_type": "global_cases", 
                "status": "success", 
                "action": "clear_global_cases"
            })
            results["summary"]["successful"] += 1
            logger.info("Successfully cleared global cases cache")
        except Exception as e:
            results["operations"].append({
                "cache_type": "global_cases", 
                "status": "error", 
                "error": str(e)
            })
            results["summary"]["failed"] += 1
            logger.error(f"Failed to clear global cases cache: {str(e)}")
        
        # Add execution time
        results["execution_time_ms"] = int((time.time() - start_time) * 1000)
        
        if results["summary"]["failed"] > 0:
            logger.warning(f"Cache clearing completed with {results['summary']['failed']} failures")
            raise HTTPException(
                status_code=500,
                detail={
                    "error": "Some cache operations failed",
                    "results": results
                }
            )
        
        logger.info(f"All caches cleared successfully in {results['execution_time_ms']}ms")
        return results
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error during cache clearing: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail={"error": f"Cache clearing failed: {str(e)}"}
        )

@router.post("/admin/cache/clear-user")
@track_business_operation("admin", "cache_clear_user")
def clear_user_cache(
    request: Request, 
    user_id: str = Query(..., description="User ID to clear cache for")
) -> Dict[str, Any]:
    """
    Clear cache for a specific user - administrative endpoint.
    
    This endpoint clears user-specific cached data including user environment
    and user cases cache for the specified user ID.
    
    **Administrative Access Required:**
    - This endpoint is intended for administrative use
    - Use when a specific user reports stale data issues
    
    **Cache Types Cleared:**
    - User Environment Cache: User profile and permission data for specified user
    - User Cases Cache: Filtered case data for specified user
    
    **Parameters:**
    - `user_id`: The user ID to clear cache for (required)
    
    **Response:**
    - `timestamp`: ISO timestamp of the operation
    - `user_id`: The user ID that was processed
    - `operations`: Array of cache clearing results for this user
    - `summary`: Success/failure counts
    - `execution_time_ms`: Total execution time
    
    **Example Response:**
    ```json
    {
        "timestamp": "2025-09-11T22:45:00.000Z",
        "user_id": "USER123",
        "operations": [
            {"cache_type": "user_environment", "status": "success", "action": "clear_user_environment"},
            {"cache_type": "user_cases", "status": "success", "action": "clear_user_cases"}
        ],
        "summary": {"successful": 2, "failed": 0},
        "execution_time_ms": 45
    }
    ```
    
    **HTTP Status Codes:**
    - `200`: Success - User cache cleared successfully
    - `400`: Bad Request - Invalid user_id parameter
    - `500`: Internal server error - Cache operation failed
    
    **Use Cases:**
    - User reports seeing stale data
    - After updating user permissions or profile
    - Troubleshooting user-specific issues
    """
    start_time = time.time()
    
    try:
        # INPUT VALIDATION -- Validate user_id parameter
        if not user_id or not user_id.strip():
            raise HTTPException(
                status_code=400,
                detail={"error": "Invalid user_id parameter"}
            )
        
        user_id = user_id.strip()
        
        results = {
            "timestamp": time.time(),
            "user_id": user_id,
            "operations": [],
            "summary": {"successful": 0, "failed": 0}
        }
        
        # Clear user environment cache
        try:
            from endpoints.utility.get_user_environment import clear_user_environment_cache
            clear_user_environment_cache(user_id)
            results["operations"].append({
                "cache_type": "user_environment", 
                "status": "success", 
                "action": "clear_user_environment"
            })
            results["summary"]["successful"] += 1
            logger.info(f"Successfully cleared user environment cache for user: {user_id}")
        except Exception as e:
            results["operations"].append({
                "cache_type": "user_environment", 
                "status": "error", 
                "error": str(e)
            })
            results["summary"]["failed"] += 1
            logger.error(f"Failed to clear user environment cache for {user_id}: {str(e)}")
        
        # Clear user cases cache
        try:
            from endpoints.case.filter_cases import clear_user_cases_cache
            clear_user_cases_cache(user_id)
            results["operations"].append({
                "cache_type": "user_cases", 
                "status": "success", 
                "action": "clear_user_cases"
            })
            results["summary"]["successful"] += 1
            logger.info(f"Successfully cleared user cases cache for user: {user_id}")
        except Exception as e:
            results["operations"].append({
                "cache_type": "user_cases", 
                "status": "error", 
                "error": str(e)
            })
            results["summary"]["failed"] += 1
            logger.error(f"Failed to clear user cases cache for {user_id}: {str(e)}")
        
        # Add execution time
        results["execution_time_ms"] = int((time.time() - start_time) * 1000)
        
        if results["summary"]["failed"] > 0:
            logger.warning(f"User cache clearing completed with {results['summary']['failed']} failures for user: {user_id}")
            raise HTTPException(
                status_code=500,
                detail={
                    "error": "Some user cache operations failed",
                    "results": results
                }
            )
        
        logger.info(f"User cache cleared successfully for {user_id} in {results['execution_time_ms']}ms")
        return results
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error during user cache clearing for {user_id}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail={"error": f"User cache clearing failed: {str(e)}"}
        )

@router.post("/admin/cache/warm-secrets")
@track_business_operation("admin", "cache_warm_secrets")
def warm_secrets_cache(request: Request) -> Dict[str, Any]:
    """
    Warm the AWS Secrets Manager cache - administrative endpoint.
    
    This endpoint pre-loads all known application secrets into the cache
    to improve performance and eliminate cold start latency.
    
    **Administrative Access Required:**
    - This endpoint is intended for administrative use
    - Useful after cache clearing or during maintenance
    
    **Response:**
    - `total_secrets`: Number of secrets attempted to warm
    - `successful`: Number of secrets successfully cached
    - `failed`: Number of secrets that failed to cache
    - `details`: Array of per-secret warming results
    - `duration_seconds`: Total warming time
    
    **Example Response:**
    ```json
    {
        "total_secrets": 9,
        "successful": 9,
        "failed": 0,
        "details": [
            {"secret_name": "surgicase/main", "status": "success", "ttl": 3600, "keys_count": 5},
            {"secret_name": "surgicase/ses_keys", "status": "success", "ttl": 3600, "keys_count": 3}
        ],
        "duration_seconds": 2.45
    }
    ```
    
    **HTTP Status Codes:**
    - `200`: Success - Cache warming completed (may include partial failures)
    - `500`: Internal server error - Cache warming system failure
    
    **Use Cases:**
    - After clearing secrets cache
    - During application startup optimization
    - Before expected high-traffic periods
    """
    try:
        from utils.secrets_manager import warm_all_secrets
        
        logger.info("Starting secrets cache warming via admin endpoint")
        result = warm_all_secrets()
        
        logger.info(f"Secrets cache warming completed: {result['successful']}/{result['total_secrets']} successful")
        return result
        
    except Exception as e:
        logger.error(f"Secrets cache warming failed: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail={"error": f"Secrets cache warming failed: {str(e)}"}
        )

@router.get("/admin/cache/stats")
@track_business_operation("admin", "cache_stats")
def get_comprehensive_cache_stats(request: Request) -> Dict[str, Any]:
    """
    Get comprehensive cache statistics - administrative endpoint.
    
    This endpoint provides detailed statistics about all cache types
    in the SurgiCase application for monitoring and troubleshooting.
    
    **Administrative Access Required:**
    - This endpoint is intended for administrative use
    - Provides detailed cache health information
    
    **Response:**
    - `timestamp`: ISO timestamp of the statistics
    - `caches`: Object containing stats for each cache type
    - `overall_health`: Summary of cache system health
    
    **Example Response:**
    ```json
    {
        "timestamp": "2025-09-11T22:45:00.000Z",
        "caches": {
            "secrets": {
                "cached_secrets_count": 9,
                "total_cache_entries": 18,
                "oldest_cache_age_seconds": 245.8,
                "region": "us-east-1"
            },
            "user_environment": {
                "cache_stats": {
                    "total_cache_entries": 24,
                    "estimated_data_entries": 12,
                    "tracked_users": 6
                },
                "cache_health": {
                    "valid_entries": 12,
                    "invalid_entries": 0
                }
            }
        },
        "overall_health": "healthy"
    }
    ```
    
    **HTTP Status Codes:**
    - `200`: Success - Cache statistics retrieved
    - `500`: Internal server error - Unable to retrieve cache stats
    
    **Use Cases:**
    - System monitoring and health checks
    - Performance troubleshooting
    - Cache optimization analysis
    """
    try:
        stats = {
            "timestamp": time.time(),
            "caches": {}
        }
        
        # Get secrets cache stats
        try:
            from utils.secrets_manager import get_secrets_cache_stats
            stats["caches"]["secrets"] = get_secrets_cache_stats()
        except Exception as e:
            logger.warning(f"Failed to get secrets cache stats: {str(e)}")
            stats["caches"]["secrets"] = {"error": str(e)}
        
        # Get user environment cache stats - simplified approach
        try:
            stats["caches"]["user_environment"] = {
                "status": "available_via_cache_diagnostics_endpoint",
                "note": "Use /cache_diagnostics endpoint for detailed user environment cache stats"
            }
        except Exception as e:
            logger.warning(f"Failed to get user environment cache stats: {str(e)}")
            stats["caches"]["user_environment"] = {"error": str(e)}
        
        # Determine overall health
        healthy_caches = 0
        total_caches = len([k for k in stats["caches"].keys() if not stats["caches"][k].get("error")])
        
        for cache_name, cache_stats in stats["caches"].items():
            if not cache_stats.get("error"):
                healthy_caches += 1
        
        if total_caches == 0:
            stats["overall_health"] = "unknown"
        elif healthy_caches == total_caches:
            stats["overall_health"] = "healthy"
        elif healthy_caches > 0:
            stats["overall_health"] = "partial"
        else:
            stats["overall_health"] = "unhealthy"
        
        logger.info(f"Cache statistics retrieved: {healthy_caches}/{total_caches} caches healthy")
        return stats
        
    except Exception as e:
        logger.error(f"Failed to get comprehensive cache stats: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail={"error": f"Cache statistics retrieval failed: {str(e)}"}
        )
