#!/usr/bin/env python3
# Created: 2025-09-15 02:22:00
# Last Modified: 2025-09-15 02:22:14
# Author: Scott Cadreau

"""
Example: Cache Startup Integration

This shows how to integrate the cache warming and scheduling into your main application.
Add this code to your main.py or wherever your FastAPI app starts up.

Example integration:
    # In main.py or app startup
    from utils.cache_scheduler import warm_all_caches, start_cache_scheduler
    
    # At startup (before starting the server)
    warm_all_caches()
    start_cache_scheduler()
"""

import logging
from utils.cache_scheduler import warm_all_caches, start_cache_scheduler, get_scheduler_status
from utils.procedure_code_auto_fix import get_cache_stats

logger = logging.getLogger(__name__)

def startup_cache_initialization():
    """
    Initialize all caches at application startup
    
    Call this function during your FastAPI app startup event or in main.py
    """
    logger.info("=== CACHE INITIALIZATION ===")
    
    # Step 1: Warm all caches
    warm_all_caches()
    
    # Step 2: Start the background refresh scheduler
    start_cache_scheduler()
    
    # Step 3: Log cache status for verification
    auto_fix_stats = get_cache_stats()
    scheduler_status = get_scheduler_status()
    
    logger.info(f"Auto-fix cache: {auto_fix_stats['rules_count']} rules loaded")
    logger.info(f"Cache scheduler: {'Running' if scheduler_status['scheduler_running'] else 'Not running'}")
    
    logger.info("=== CACHE INITIALIZATION COMPLETE ===")

def get_all_cache_status():
    """
    Get status of all caches for monitoring/health checks
    
    Returns:
        Dict with status of all caches
    """
    return {
        'auto_fix_cache': get_cache_stats(),
        'scheduler': get_scheduler_status()
    }

if __name__ == "__main__":
    # Example usage
    logging.basicConfig(level=logging.INFO)
    
    print("Testing cache initialization...")
    startup_cache_initialization()
    
    print("\nCache status:")
    status = get_all_cache_status()
    print(f"Auto-fix rules loaded: {status['auto_fix_cache']['rules_count']}")
    print(f"Cache age: {status['auto_fix_cache']['cache_age_hours']:.2f} hours")
    print(f"Scheduler running: {status['scheduler']['scheduler_running']}")
    
    print("\nCache initialization test complete!")
