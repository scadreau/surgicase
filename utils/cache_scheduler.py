# Created: 2025-09-15 02:21:39
# Last Modified: 2025-09-15 02:22:14
# Author: Scott Cadreau

"""
Cache Scheduler Utility

This module provides scheduled cache refresh functionality for various caches
in the application, including the procedure code auto-fix cache.

Usage:
    from utils.cache_scheduler import start_cache_scheduler, warm_all_caches
    
    # At startup
    warm_all_caches()
    start_cache_scheduler()
"""

import logging
import threading
import time
from typing import Optional

logger = logging.getLogger(__name__)

# Global scheduler thread
_scheduler_thread: Optional[threading.Thread] = None
_scheduler_running = False

def _cache_refresh_worker():
    """
    Background worker that periodically refreshes caches
    """
    global _scheduler_running
    
    logger.info("Cache refresh scheduler started")
    
    while _scheduler_running:
        try:
            # Import here to avoid circular imports
            from utils.procedure_code_auto_fix import CACHE_REFRESH_INTERVAL, _refresh_auto_fix_cache
            from core.database import get_db_connection, close_db_connection
            
            # Sleep for the refresh interval
            time.sleep(CACHE_REFRESH_INTERVAL)
            
            if not _scheduler_running:
                break
            
            logger.info("Starting scheduled cache refresh...")
            
            # Refresh auto-fix cache
            conn = None
            try:
                conn = get_db_connection()
                success = _refresh_auto_fix_cache(conn)
                if success:
                    logger.info("Scheduled auto-fix cache refresh completed successfully")
                else:
                    logger.error("Scheduled auto-fix cache refresh failed")
            except Exception as e:
                logger.error(f"Error during scheduled auto-fix cache refresh: {str(e)}")
            finally:
                if conn:
                    close_db_connection(conn)
            
            # Add other cache refreshes here as needed
            # Example:
            # refresh_other_cache()
            
        except Exception as e:
            logger.error(f"Error in cache refresh worker: {str(e)}")
            # Continue running even if there's an error
            time.sleep(60)  # Wait a minute before retrying
    
    logger.info("Cache refresh scheduler stopped")

def start_cache_scheduler():
    """
    Start the background cache refresh scheduler
    
    This should be called once at application startup after warming caches.
    """
    global _scheduler_thread, _scheduler_running
    
    if _scheduler_running:
        logger.warning("Cache scheduler is already running")
        return
    
    _scheduler_running = True
    _scheduler_thread = threading.Thread(
        target=_cache_refresh_worker,
        name="cache_refresh_scheduler",
        daemon=True
    )
    _scheduler_thread.start()
    
    logger.info("Cache refresh scheduler started in background")

def stop_cache_scheduler():
    """
    Stop the background cache refresh scheduler
    
    This is mainly for testing or graceful shutdown.
    """
    global _scheduler_running, _scheduler_thread
    
    if not _scheduler_running:
        logger.info("Cache scheduler is not running")
        return
    
    logger.info("Stopping cache refresh scheduler...")
    _scheduler_running = False
    
    if _scheduler_thread and _scheduler_thread.is_alive():
        _scheduler_thread.join(timeout=5)
        if _scheduler_thread.is_alive():
            logger.warning("Cache scheduler thread did not stop gracefully")
        else:
            logger.info("Cache scheduler stopped successfully")

def warm_all_caches():
    """
    Warm all application caches at startup
    
    This should be called once during application initialization.
    """
    logger.info("Starting cache warming process...")
    
    # Import here to avoid circular imports
    from utils.procedure_code_auto_fix import warm_auto_fix_cache
    from core.database import get_db_connection, close_db_connection
    
    conn = None
    try:
        conn = get_db_connection()
        
        # Warm auto-fix cache
        success = warm_auto_fix_cache(conn)
        if success:
            logger.info("Auto-fix cache warmed successfully")
        else:
            logger.error("Failed to warm auto-fix cache")
        
        # Add other cache warming here as needed
        # Example:
        # warm_other_cache(conn)
        
        logger.info("Cache warming process completed")
        
    except Exception as e:
        logger.error(f"Error during cache warming: {str(e)}")
    finally:
        if conn:
            close_db_connection(conn)

def get_scheduler_status() -> dict:
    """
    Get the current status of the cache scheduler
    
    Returns:
        Dict with scheduler status information
    """
    global _scheduler_running, _scheduler_thread
    
    return {
        'scheduler_running': _scheduler_running,
        'scheduler_thread_alive': _scheduler_thread.is_alive() if _scheduler_thread else False,
        'scheduler_thread_name': _scheduler_thread.name if _scheduler_thread else None
    }
