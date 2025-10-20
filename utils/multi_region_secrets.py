# Created: 2025-10-20
# Last Modified: 2025-10-20 13:02:39
# Author: Scott Cadreau

"""
Multi-Region Secrets Failover (Optional Enhancement)

This module provides automatic failover to a secondary AWS region if the
primary Secrets Manager region becomes unavailable.

NOTE: This requires secrets to be manually replicated to the failover region.
AWS Secrets Manager does support cross-region replication, but it requires setup.

Usage:
    from utils.multi_region_secrets import get_secret_with_failover
    
    secret = get_secret_with_failover("surgicase/main")
"""

import logging
from typing import Dict, Any, Optional, List
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)

# Configuration
PRIMARY_REGION = "us-east-1"
FAILOVER_REGION = "us-west-2"

# Track failover status
_failover_state = {
    "using_failover": False,
    "failover_count": 0,
    "last_failover_time": 0
}


def get_secret_with_failover(
    secret_name: str,
    cache_ttl: int = 3600,
    allowed_regions: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Get secret with automatic multi-region failover.
    
    Tries primary region first, automatically fails over to secondary region
    if primary is unavailable. Uses existing stale cache before attempting
    failover to minimize cross-region latency.
    
    Args:
        secret_name: Name of the secret to retrieve
        cache_ttl: Cache TTL in seconds
        allowed_regions: List of regions to try (default: [us-east-1, us-west-2])
        
    Returns:
        Secret data dictionary
        
    Raises:
        Exception: If all regions fail and no stale cache available
    """
    from utils.secrets_manager import secrets_manager
    import time
    
    if allowed_regions is None:
        allowed_regions = [PRIMARY_REGION, FAILOVER_REGION]
    
    errors = []
    
    for region_idx, region in enumerate(allowed_regions):
        is_primary = (region_idx == 0)
        
        try:
            if is_primary:
                # Try primary region using existing secrets manager
                # This will use stale cache if available
                return secrets_manager.get_secret(secret_name, cache_ttl=cache_ttl)
            else:
                # Failover to secondary region
                logger.warning(f"🔄 Attempting failover to {region} for secret {secret_name}")
                
                from utils.secrets_manager import SecretsManager
                failover_sm = SecretsManager(region=region)
                
                result = failover_sm.get_secret(secret_name, cache_ttl=cache_ttl, allow_stale=False)
                
                # Track successful failover
                _failover_state["using_failover"] = True
                _failover_state["failover_count"] += 1
                _failover_state["last_failover_time"] = time.time()
                
                logger.info(f"✅ Successfully failed over to {region} for secret {secret_name}")
                
                return result
                
        except Exception as e:
            error_msg = f"{region}: {str(e)}"
            errors.append(error_msg)
            logger.warning(f"Failed to retrieve secret from {region}: {str(e)}")
            continue
    
    # All regions failed
    error_summary = "; ".join(errors)
    raise Exception(f"Failed to retrieve secret {secret_name} from all regions: {error_summary}")


def get_failover_stats() -> Dict[str, Any]:
    """
    Get statistics about failover usage.
    
    Returns:
        Dict with failover statistics
    """
    import time
    
    current_time = time.time()
    time_since_failover = current_time - _failover_state["last_failover_time"] if _failover_state["last_failover_time"] > 0 else None
    
    return {
        "currently_using_failover": _failover_state["using_failover"],
        "total_failovers": _failover_state["failover_count"],
        "last_failover_time": _failover_state["last_failover_time"],
        "seconds_since_last_failover": time_since_failover,
        "primary_region": PRIMARY_REGION,
        "failover_region": FAILOVER_REGION
    }


def reset_failover_state():
    """
    Reset failover state back to primary region.
    Call this after confirming primary region is healthy.
    """
    global _failover_state
    
    if _failover_state["using_failover"]:
        logger.info(f"🔄 Resetting to primary region {PRIMARY_REGION}")
    
    _failover_state["using_failover"] = False
    # Don't reset counters - keep for statistics


def check_region_health(region: str = PRIMARY_REGION) -> bool:
    """
    Check if a specific region's Secrets Manager is healthy.
    
    Args:
        region: AWS region to check
        
    Returns:
        True if region is healthy, False otherwise
    """
    try:
        from utils.secrets_manager import SecretsManager
        import boto3
        
        # Try to list secrets (lightweight operation)
        client = boto3.client("secretsmanager", region_name=region)
        client.list_secrets(MaxResults=1)
        
        return True
        
    except Exception as e:
        logger.warning(f"Region {region} health check failed: {str(e)}")
        return False


# =============================================================================
# Setup Instructions (if implementing multi-region)
# =============================================================================

"""
TO ENABLE MULTI-REGION FAILOVER:

1. Replicate Secrets to Failover Region:
   
   For each secret, enable cross-region replication in AWS Console:
   - Go to AWS Secrets Manager → Select secret
   - Click "Replicate secret to other regions"
   - Select us-west-2
   - Confirm replication
   
   Or use AWS CLI:
   ```bash
   aws secretsmanager replicate-secret-to-regions \
     --secret-id surgicase/main \
     --add-replica-regions Region=us-west-2 \
     --region us-east-1
   ```

2. Test Failover:
   ```python
   from utils.multi_region_secrets import get_secret_with_failover, check_region_health
   
   # Check health
   print(f"Primary region healthy: {check_region_health('us-east-1')}")
   print(f"Failover region healthy: {check_region_health('us-west-2')}")
   
   # Test failover
   secret = get_secret_with_failover("surgicase/main")
   print(secret)
   ```

3. Update Critical Code:
   
   Replace in high-priority areas:
   ```python
   # Before:
   from utils.secrets_manager import get_secret
   secret = get_secret("surgicase/main")
   
   # After:
   from utils.multi_region_secrets import get_secret_with_failover
   secret = get_secret_with_failover("surgicase/main")
   ```

4. Monitor Failover:
   ```python
   from utils.multi_region_secrets import get_failover_stats
   
   stats = get_failover_stats()
   if stats["currently_using_failover"]:
       print("⚠️ Currently using failover region!")
   ```

COST IMPACT:
- Secret storage: ~$0.40/month per secret per region (doubles cost)
- API calls: Minimal (only on failover)
- Total: ~$4-5/month for 10 secrets in 2 regions

WHEN TO USE:
- Your application is mission-critical (healthcare, finance)
- You need protection against regional AWS outages
- You're already planning multi-region deployment
- RTO (Recovery Time Objective) < 5 minutes

WHEN NOT TO USE:
- Stale cache (current solution) is sufficient
- Budget constraints
- Single-region deployment only
- Not planning full DR strategy
"""

