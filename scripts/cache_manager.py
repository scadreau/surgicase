#!/usr/bin/env python3
# Created: 2025-09-11 
# Last Modified: 2025-09-11 22:44:26
# Author: Scott Cadreau

"""
SurgiCase Cache Management Python Script
Direct cache management for all application caches using internal functions
"""

import sys
import os
import argparse
import json
from datetime import datetime
from typing import Dict, Any, Optional

# Add the project root to Python path
sys.path.insert(0, '/home/scadreau/surgicase')

def log_info(message: str) -> None:
    """Log info message with timestamp"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"🔧 [{timestamp}] {message}")

def log_success(message: str) -> None:
    """Log success message with timestamp"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"✅ [{timestamp}] {message}")

def log_warning(message: str) -> None:
    """Log warning message with timestamp"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"⚠️  [{timestamp}] {message}")

def log_error(message: str) -> None:
    """Log error message with timestamp"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"❌ [{timestamp}] {message}")

def clear_secrets_cache(secret_name: Optional[str] = None) -> Dict[str, Any]:
    """Clear AWS Secrets Manager cache"""
    try:
        from utils.secrets_manager import clear_secrets_cache as clear_cache
        
        log_info("Clearing secrets cache...")
        clear_cache(secret_name)
        
        if secret_name:
            log_success(f"Cleared secrets cache for: {secret_name}")
            return {"status": "success", "action": "clear_secret", "secret_name": secret_name}
        else:
            log_success("Cleared all secrets cache")
            return {"status": "success", "action": "clear_all_secrets"}
            
    except Exception as e:
        log_error(f"Failed to clear secrets cache: {str(e)}")
        return {"status": "error", "error": str(e)}

def clear_user_environment_cache(user_id: Optional[str] = None) -> Dict[str, Any]:
    """Clear user environment cache"""
    try:
        from endpoints.utility.get_user_environment import clear_user_environment_cache as clear_cache
        
        log_info("Clearing user environment cache...")
        clear_cache(user_id)
        
        if user_id:
            log_success(f"Cleared user environment cache for: {user_id}")
            return {"status": "success", "action": "clear_user_environment", "user_id": user_id}
        else:
            log_success("Cleared all user environment cache")
            return {"status": "success", "action": "clear_all_user_environment"}
            
    except Exception as e:
        log_error(f"Failed to clear user environment cache: {str(e)}")
        return {"status": "error", "error": str(e)}

def clear_user_cases_cache(user_id: Optional[str] = None) -> Dict[str, Any]:
    """Clear user cases cache"""
    try:
        from endpoints.case.filter_cases import clear_user_cases_cache as clear_cache
        
        log_info("Clearing user cases cache...")
        clear_cache(user_id)
        
        if user_id:
            log_success(f"Cleared user cases cache for: {user_id}")
            return {"status": "success", "action": "clear_user_cases", "user_id": user_id}
        else:
            log_success("Cleared all user cases cache")
            return {"status": "success", "action": "clear_all_user_cases"}
            
    except Exception as e:
        log_error(f"Failed to clear user cases cache: {str(e)}")
        return {"status": "error", "error": str(e)}

def clear_global_cases_cache() -> Dict[str, Any]:
    """Clear global cases cache"""
    try:
        from endpoints.backoffice.get_cases_by_status import clear_cases_cache
        
        log_info("Clearing global cases cache...")
        clear_cases_cache()
        log_success("Cleared global cases cache")
        return {"status": "success", "action": "clear_global_cases"}
        
    except Exception as e:
        log_error(f"Failed to clear global cases cache: {str(e)}")
        return {"status": "error", "error": str(e)}

def clear_all_caches() -> Dict[str, Any]:
    """Clear all application caches"""
    log_info("=== CLEARING ALL CACHES ===")
    
    results = {
        "timestamp": datetime.now().isoformat(),
        "operations": [],
        "summary": {"successful": 0, "failed": 0}
    }
    
    # Clear secrets cache
    result = clear_secrets_cache()
    results["operations"].append({"cache_type": "secrets", **result})
    if result["status"] == "success":
        results["summary"]["successful"] += 1
    else:
        results["summary"]["failed"] += 1
    
    # Clear user environment cache
    result = clear_user_environment_cache()
    results["operations"].append({"cache_type": "user_environment", **result})
    if result["status"] == "success":
        results["summary"]["successful"] += 1
    else:
        results["summary"]["failed"] += 1
    
    # Clear user cases cache
    result = clear_user_cases_cache()
    results["operations"].append({"cache_type": "user_cases", **result})
    if result["status"] == "success":
        results["summary"]["successful"] += 1
    else:
        results["summary"]["failed"] += 1
    
    # Clear global cases cache
    result = clear_global_cases_cache()
    results["operations"].append({"cache_type": "global_cases", **result})
    if result["status"] == "success":
        results["summary"]["successful"] += 1
    else:
        results["summary"]["failed"] += 1
    
    log_success(f"Cache clearing completed: {results['summary']['successful']}/{len(results['operations'])} successful")
    return results

def get_cache_stats() -> Dict[str, Any]:
    """Get comprehensive cache statistics"""
    log_info("=== GATHERING CACHE STATISTICS ===")
    
    stats = {
        "timestamp": datetime.now().isoformat(),
        "caches": {}
    }
    
    # Get secrets cache stats
    try:
        from utils.secrets_manager import get_secrets_cache_stats
        stats["caches"]["secrets"] = get_secrets_cache_stats()
        log_success("Retrieved secrets cache statistics")
    except Exception as e:
        log_error(f"Failed to get secrets cache stats: {str(e)}")
        stats["caches"]["secrets"] = {"error": str(e)}
    
    # Get user environment cache stats (if diagnostics available)
    try:
        from endpoints.utility.cache_diagnostics import get_cache_diagnostics
        stats["caches"]["user_environment"] = get_cache_diagnostics()
        log_success("Retrieved user environment cache statistics")
    except Exception as e:
        log_warning(f"User environment cache diagnostics not available: {str(e)}")
        stats["caches"]["user_environment"] = {"error": str(e)}
    
    return stats

def warm_secrets_cache() -> Dict[str, Any]:
    """Warm the secrets cache"""
    try:
        from utils.secrets_manager import warm_all_secrets
        
        log_info("Warming secrets cache...")
        result = warm_all_secrets()
        log_success(f"Secrets cache warming completed: {result['successful']}/{result['total_secrets']} successful")
        return result
        
    except Exception as e:
        log_error(f"Failed to warm secrets cache: {str(e)}")
        return {"status": "error", "error": str(e)}

def warm_user_environment_caches() -> Dict[str, Any]:
    """Warm user environment caches"""
    try:
        from endpoints.utility.get_user_environment import warm_all_user_environment_caches
        
        log_info("Warming user environment caches...")
        result = warm_all_user_environment_caches()
        log_success(f"User environment cache warming completed: {result.get('successful_users', 0)} users")
        return result
        
    except Exception as e:
        log_error(f"Failed to warm user environment caches: {str(e)}")
        return {"status": "error", "error": str(e)}

def clear_and_warm_all() -> Dict[str, Any]:
    """Clear all caches and then warm them"""
    log_info("=== CLEAR AND WARM ALL CACHES ===")
    
    # Clear all caches first
    clear_result = clear_all_caches()
    
    # Warm caches
    warm_results = {
        "secrets": warm_secrets_cache(),
        "user_environment": warm_user_environment_caches()
    }
    
    return {
        "timestamp": datetime.now().isoformat(),
        "clear_results": clear_result,
        "warm_results": warm_results
    }

def main():
    """Main function with argument parsing"""
    parser = argparse.ArgumentParser(
        description="SurgiCase Cache Management - Direct Python access to all cache functions",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s clear-all                    # Clear all caches
  %(prog)s clear-secrets               # Clear secrets cache only
  %(prog)s clear-user-env USER123      # Clear user environment cache for USER123
  %(prog)s clear-user-cases USER123    # Clear user cases cache for USER123
  %(prog)s stats                       # Show cache statistics
  %(prog)s warm-secrets                # Warm secrets cache
  %(prog)s clear-and-warm              # Clear all and warm caches
        """
    )
    
    parser.add_argument('command', choices=[
        'clear-all', 'clear-secrets', 'clear-user-env', 'clear-user-cases', 
        'clear-global-cases', 'stats', 'warm-secrets', 'warm-user-env', 
        'clear-and-warm'
    ], help='Cache management command to execute')
    
    parser.add_argument('user_id', nargs='?', help='User ID for user-specific operations')
    parser.add_argument('--secret-name', help='Specific secret name to clear (for clear-secrets)')
    parser.add_argument('--json', action='store_true', help='Output results as JSON')
    parser.add_argument('--verbose', '-v', action='store_true', help='Enable verbose output')
    
    args = parser.parse_args()
    
    print("=== SurgiCase Cache Manager (Python) ===")
    print(f"Command: {args.command}")
    print(f"Timestamp: {datetime.now()}")
    print()
    
    result = None
    
    try:
        if args.command == 'clear-all':
            result = clear_all_caches()
        elif args.command == 'clear-secrets':
            result = clear_secrets_cache(args.secret_name)
        elif args.command == 'clear-user-env':
            result = clear_user_environment_cache(args.user_id)
        elif args.command == 'clear-user-cases':
            result = clear_user_cases_cache(args.user_id)
        elif args.command == 'clear-global-cases':
            result = clear_global_cases_cache()
        elif args.command == 'stats':
            result = get_cache_stats()
        elif args.command == 'warm-secrets':
            result = warm_secrets_cache()
        elif args.command == 'warm-user-env':
            result = warm_user_environment_caches()
        elif args.command == 'clear-and-warm':
            result = clear_and_warm_all()
        
        if args.json and result:
            print("\n=== JSON RESULT ===")
            print(json.dumps(result, indent=2, default=str))
        
        log_success("Cache management operation completed successfully!")
        
    except Exception as e:
        log_error(f"Cache management operation failed: {str(e)}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
