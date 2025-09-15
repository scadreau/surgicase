# Created: 2025-09-15 02:15:20
# Last Modified: 2025-09-15 02:22:29
# Author: Scott Cadreau

"""
Procedure Code Auto-Fix Utility

This module provides functionality to automatically correct common procedure code issues
using a database-driven approach. The procedure_code_auto_fix table contains mappings
of commonly entered incorrect codes to their correct equivalents.

Key Features:
- Database-driven corrections (no hardcoded fixes)
- Audit trail logging for all corrections
- Active/inactive flag for enabling/disabling fixes
- Detailed reporting of what was corrected

Usage:
    from utils.procedure_code_auto_fix import auto_fix_procedure_codes
    
    corrected_codes, corrections = auto_fix_procedure_codes(conn, procedure_codes, case_id)
"""

import logging
import time
import threading
from typing import List, Dict, Tuple, Optional

logger = logging.getLogger(__name__)

# Global cache for auto-fix rules
_auto_fix_cache: Dict[str, Dict] = {}
_cache_last_updated: Optional[float] = None
_cache_lock = threading.RLock()
CACHE_TTL_SECONDS = 6 * 60 * 60  # 6 hours
CACHE_REFRESH_INTERVAL = 5.5 * 60 * 60  # 5.5 hours (refresh before TTL expires)

def _load_auto_fix_rules_from_db(conn) -> Dict[str, Dict]:
    """
    Load auto-fix rules from database and return as dictionary
    
    Args:
        conn: Database connection object
        
    Returns:
        Dict mapping entered_code to fix rule data
    """
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT entered_code, fixed_code, reason, created_date
                FROM procedure_code_auto_fix 
                WHERE active = 1
                ORDER BY entered_code
            """)
            rules = cursor.fetchall()
            
            # Convert to dictionary for fast lookups
            rule_dict = {}
            for rule in rules:
                rule_dict[rule['entered_code']] = {
                    'fixed_code': rule['fixed_code'],
                    'reason': rule['reason'],
                    'created_date': rule['created_date']
                }
            
            logger.info(f"Loaded {len(rule_dict)} auto-fix rules from database")
            return rule_dict
            
    except Exception as e:
        logger.error(f"Error loading auto-fix rules from database: {str(e)}")
        return {}

def _refresh_auto_fix_cache(conn) -> bool:
    """
    Refresh the global auto-fix cache from database
    
    Args:
        conn: Database connection object
        
    Returns:
        bool: True if cache was successfully refreshed
    """
    global _auto_fix_cache, _cache_last_updated
    
    try:
        with _cache_lock:
            new_rules = _load_auto_fix_rules_from_db(conn)
            _auto_fix_cache = new_rules
            _cache_last_updated = time.time()
            
            logger.info(f"Auto-fix cache refreshed with {len(new_rules)} rules")
            return True
            
    except Exception as e:
        logger.error(f"Failed to refresh auto-fix cache: {str(e)}")
        return False

def _get_cached_auto_fix_rules(conn) -> Dict[str, Dict]:
    """
    Get auto-fix rules from cache, refreshing if necessary
    
    Args:
        conn: Database connection object
        
    Returns:
        Dict mapping entered_code to fix rule data
    """
    global _auto_fix_cache, _cache_last_updated
    
    with _cache_lock:
        # Check if cache needs refresh
        current_time = time.time()
        cache_age = current_time - (_cache_last_updated or 0)
        
        if _cache_last_updated is None or cache_age > CACHE_TTL_SECONDS:
            logger.info(f"Auto-fix cache expired (age: {cache_age:.1f}s), refreshing...")
            if not _refresh_auto_fix_cache(conn):
                # If refresh failed and we have stale cache, use it with warning
                if _auto_fix_cache:
                    logger.warning("Using stale auto-fix cache due to refresh failure")
                else:
                    logger.error("No auto-fix cache available and refresh failed")
                    return {}
        
        return _auto_fix_cache.copy()  # Return copy to prevent external modification

def warm_auto_fix_cache(conn) -> bool:
    """
    Warm the auto-fix cache at startup
    
    Args:
        conn: Database connection object
        
    Returns:
        bool: True if cache was successfully warmed
    """
    logger.info("Warming auto-fix cache at startup...")
    success = _refresh_auto_fix_cache(conn)
    if success:
        logger.info("Auto-fix cache warmed successfully")
    else:
        logger.error("Failed to warm auto-fix cache at startup")
    return success

def get_cache_stats() -> Dict[str, any]:
    """
    Get cache statistics for monitoring/debugging
    
    Returns:
        Dict with cache statistics
    """
    global _auto_fix_cache, _cache_last_updated
    
    with _cache_lock:
        current_time = time.time()
        cache_age = current_time - (_cache_last_updated or 0) if _cache_last_updated else None
        
        return {
            'rules_count': len(_auto_fix_cache),
            'last_updated': _cache_last_updated,
            'cache_age_seconds': cache_age,
            'cache_age_hours': cache_age / 3600 if cache_age else None,
            'is_expired': cache_age > CACHE_TTL_SECONDS if cache_age else True,
            'ttl_seconds': CACHE_TTL_SECONDS,
            'refresh_interval_seconds': CACHE_REFRESH_INTERVAL
        }

def auto_fix_procedure_codes(conn, procedure_codes: List[str], case_id: str = None) -> Tuple[List[str], List[Dict]]:
    """
    Auto-fix common procedure code issues using the procedure_code_auto_fix table
    
    This function checks each procedure code against the auto_fix table and replaces
    commonly incorrect codes with their correct equivalents. All corrections are
    logged for audit purposes.
    
    Args:
        conn: Database connection object
        procedure_codes: List of procedure codes to check and potentially fix
        case_id: Optional case ID for logging purposes
        
    Returns:
        Tuple containing:
            - corrected_codes (List[str]): List of procedure codes with fixes applied
            - corrections_made (List[Dict]): List of corrections that were applied, each containing:
                - original (str): The original incorrect code
                - corrected (str): The corrected code
                - reason (str): Explanation of why the correction was made
                
    Example:
        corrected_codes, corrections = auto_fix_procedure_codes(conn, ['59510', '12345'], 'CASE-001')
        # Returns: (['59514', '12345'], [{'original': '59510', 'corrected': '59514', 'reason': '...'}])
        
    Database Table Structure:
        procedure_code_auto_fix:
            - entered_code (VARCHAR): The incorrect code that users commonly enter
            - fixed_code (VARCHAR): The correct code to use instead
            - reason (VARCHAR): Explanation of the correction
            - active (TINYINT): Whether this fix is currently active (1) or disabled (0)
    """
    if not procedure_codes:
        return [], []
    
    corrections_made = []
    corrected_codes = []
    
    try:
        # Get auto-fix rules from cache (with automatic refresh if needed)
        auto_fix_rules = _get_cached_auto_fix_rules(conn)
        
        for code in procedure_codes:
            # Check if this code needs auto-fixing using cached rules
            fix_rule = auto_fix_rules.get(code)
            
            if fix_rule:
                # Apply the fix
                fixed_code = fix_rule['fixed_code']
                reason = fix_rule['reason']
                
                corrected_codes.append(fixed_code)
                corrections_made.append({
                    'original': code,
                    'corrected': fixed_code,
                    'reason': reason
                })
                
                # Log the correction for audit trail
                log_message = f"Auto-corrected procedure code: {code} -> {fixed_code}"
                if case_id:
                    log_message += f" for case {case_id}"
                log_message += f" (Reason: {reason})"
                logger.info(log_message)
                
            else:
                # No fix needed, keep original code
                corrected_codes.append(code)
        
        # Log summary if corrections were made
        if corrections_made:
            summary_msg = f"Applied {len(corrections_made)} procedure code auto-fixes"
            if case_id:
                summary_msg += f" for case {case_id}"
            logger.info(summary_msg)
        
        return corrected_codes, corrections_made
        
    except Exception as e:
        # Log error but don't fail the entire operation
        error_msg = f"Error during procedure code auto-fix: {str(e)}"
        if case_id:
            error_msg += f" for case {case_id}"
        logger.error(error_msg)
        
        # Return original codes unchanged if there's an error
        return procedure_codes, []

def get_active_auto_fixes(conn) -> List[Dict]:
    """
    Get all currently active auto-fix rules for reporting/debugging purposes
    
    Args:
        conn: Database connection object
        
    Returns:
        List of dictionaries containing active auto-fix rules
    """
    try:
        # Use cached rules for better performance
        auto_fix_rules = _get_cached_auto_fix_rules(conn)
        
        # Convert back to list format for compatibility
        rules_list = []
        for entered_code, rule_data in auto_fix_rules.items():
            rules_list.append({
                'entered_code': entered_code,
                'fixed_code': rule_data['fixed_code'],
                'reason': rule_data['reason'],
                'created_date': rule_data['created_date']
            })
        
        # Sort by entered_code for consistent ordering
        rules_list.sort(key=lambda x: x['entered_code'])
        return rules_list
            
    except Exception as e:
        logger.error(f"Error retrieving active auto-fix rules: {str(e)}")
        return []

def format_corrections_for_response(corrections: List[Dict]) -> List[str]:
    """
    Format correction information for inclusion in API responses
    
    Args:
        corrections: List of correction dictionaries from auto_fix_procedure_codes
        
    Returns:
        List of human-readable correction messages
    """
    if not corrections:
        return []
    
    messages = []
    for correction in corrections:
        message = f"Auto-corrected {correction['original']} to {correction['corrected']}"
        if correction.get('reason'):
            message += f" ({correction['reason']})"
        messages.append(message)
    
    return messages
