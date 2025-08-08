# Created: 2025-08-08 15:37:06
# Last Modified: 2025-08-08 15:50:06
# Author: Scott Cadreau

# endpoints/monitoring/secrets_cache_stats.py
from fastapi import APIRouter, HTTPException, Request
from typing import Dict, Any
import time

# Import monitoring utilities
try:
    from utils.monitoring import track_request_metrics, REQUEST_COUNT, REQUEST_DURATION
except ImportError:
    # Fallback for when utils module is not available
    def track_request_metrics(func):
        return func
    REQUEST_COUNT = None
    REQUEST_DURATION = None

router = APIRouter()

@router.get("/secrets-cache-stats")
@track_request_metrics
def get_secrets_cache_stats(request: Request) -> Dict[str, Any]:
    """
    Get AWS Secrets Manager cache statistics for monitoring and debugging.
    
    This endpoint provides insights into the centralized secrets manager cache performance,
    including cache hit rates, cache sizes, and cache ages. Useful for monitoring
    secrets caching efficiency and troubleshooting performance issues.
    
    **Authentication:**
    - No authentication required for monitoring endpoints
    
    **Response:**
    - `cached_secrets_count`: Number of unique secrets currently cached
    - `total_cache_entries`: Total cache entries (includes timestamps)
    - `oldest_cache_age_seconds`: Age of the oldest cached secret in seconds
    - `newest_cache_age_seconds`: Age of the newest cached secret in seconds
    - `region`: AWS region being used for secrets manager
    - `cache_efficiency`: Calculated cache efficiency metrics
    
    **Example Response:**
    ```json
    {
        "cached_secrets_count": 5,
        "total_cache_entries": 10,
        "oldest_cache_age_seconds": 245.8,
        "newest_cache_age_seconds": 12.3,
        "region": "us-east-1",
        "cache_efficiency": {
            "avg_cache_age_seconds": 129.05,
            "cache_utilization_percent": 50.0,
            "cache_status": "healthy"
        }
    }
    ```
    
    **HTTP Status Codes:**
    - `200`: Success - Cache statistics retrieved
    - `500`: Internal server error - Unable to retrieve cache stats
    
    **Monitoring Integration:**
    - Prometheus metrics: Tracks request count and duration
    - Structured logging: Logs cache access patterns
    
    **Use Cases:**
    - Monitor secrets cache performance
    - Debug slow secrets retrieval
    - Verify cache TTL settings
    - Track secrets usage patterns
    """
    start_time = time.time()
    
    try:
        from utils.secrets_manager import get_secrets_cache_stats
        
        # Get base cache statistics
        cache_stats = get_secrets_cache_stats()
        
        # Calculate additional efficiency metrics
        cache_efficiency = {
            "avg_cache_age_seconds": 0.0,
            "cache_utilization_percent": 0.0,
            "cache_status": "unknown"
        }
        
        if cache_stats["cached_secrets_count"] > 0:
            # Calculate average cache age
            if cache_stats["oldest_cache_age_seconds"] > 0 and cache_stats["newest_cache_age_seconds"] >= 0:
                cache_efficiency["avg_cache_age_seconds"] = (
                    cache_stats["oldest_cache_age_seconds"] + cache_stats["newest_cache_age_seconds"]
                ) / 2
            
            # Calculate cache utilization (assuming max 20 secrets for this calculation)
            max_expected_secrets = 20
            cache_efficiency["cache_utilization_percent"] = min(
                (cache_stats["cached_secrets_count"] / max_expected_secrets) * 100, 100.0
            )
            
            # Determine cache status
            avg_age = cache_efficiency["avg_cache_age_seconds"]
            if avg_age < 60:  # Less than 1 minute
                cache_efficiency["cache_status"] = "very_fresh"
            elif avg_age < 180:  # Less than 3 minutes
                cache_efficiency["cache_status"] = "healthy"
            elif avg_age < 300:  # Less than 5 minutes (TTL limit)
                cache_efficiency["cache_status"] = "aging"
            else:
                cache_efficiency["cache_status"] = "stale"
        else:
            cache_efficiency["cache_status"] = "empty"
        
        # Combine statistics
        response_data = {
            **cache_stats,
            "cache_efficiency": cache_efficiency,
            "timestamp": time.time(),
            "request_duration_ms": round((time.time() - start_time) * 1000, 2)
        }
        
        return response_data
        
    except Exception as e:
        # Track error in metrics if available
        if REQUEST_COUNT is not None:
            REQUEST_COUNT.labels(
                method="GET", 
                endpoint="/secrets-cache-stats", 
                status="error"
            ).inc()
        
        raise HTTPException(
            status_code=500,
            detail=f"Unable to retrieve secrets cache statistics: {str(e)}"
        )
