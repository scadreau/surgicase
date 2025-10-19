# Created: 2025-10-19
# Last Modified: 2025-10-19 23:40:46
# Author: Scott Cadreau

"""
Generate encryption keys for all users in the database.

This script is used to:
1. Generate DEKs for all existing users who don't have encryption keys
2. Validate that all active users have encryption keys
3. Report on key generation status

Usage:
    python utils/generate_encryption_keys.py [--dry-run] [--force]
    
Options:
    --dry-run: Show what would be done without making changes
    --force: Regenerate keys even for users who already have them
"""

import sys
import argparse
import logging
import time
from typing import Dict, List, Any
import pymysql.cursors

# Add parent directory to path for imports
sys.path.insert(0, '/home/scadreau/surgicase')

from core.database import get_db_connection, close_db_connection
from utils.phi_encryption import generate_and_store_user_key

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def get_users_needing_keys(conn, force: bool = False) -> List[Dict[str, Any]]:
    """
    Get list of users who need encryption keys generated.
    
    Args:
        conn: Database connection
        force: If True, return all users (even those with existing keys)
        
    Returns:
        List of user dictionaries with user_id and user_email
    """
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            if force:
                # Get all active users
                cursor.execute("""
                    SELECT user_id, user_email, first_name, last_name
                    FROM user_profile
                    WHERE active = 1
                    ORDER BY user_id
                """)
            else:
                # Get only users without encryption keys
                cursor.execute("""
                    SELECT up.user_id, up.user_email, up.first_name, up.last_name
                    FROM user_profile up
                    LEFT JOIN user_encryption_keys uek ON up.user_id = uek.user_id
                    WHERE up.active = 1 AND uek.user_id IS NULL
                    ORDER BY up.user_id
                """)
            
            return cursor.fetchall()
            
    except Exception as e:
        logger.error(f"Error fetching users: {str(e)}")
        raise


def get_encryption_key_stats(conn) -> Dict[str, Any]:
    """
    Get statistics about encryption keys in the database.
    
    Args:
        conn: Database connection
        
    Returns:
        Dict with statistics
    """
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            # Total active users
            cursor.execute("SELECT COUNT(*) as count FROM user_profile WHERE active = 1")
            total_users = cursor.fetchone()['count']
            
            # Users with encryption keys
            cursor.execute("""
                SELECT COUNT(*) as count 
                FROM user_encryption_keys uek
                JOIN user_profile up ON uek.user_id = up.user_id
                WHERE up.active = 1 AND uek.is_active = 1
            """)
            users_with_keys = cursor.fetchone()['count']
            
            # Users without encryption keys
            cursor.execute("""
                SELECT COUNT(*) as count 
                FROM user_profile up
                LEFT JOIN user_encryption_keys uek ON up.user_id = uek.user_id
                WHERE up.active = 1 AND uek.user_id IS NULL
            """)
            users_without_keys = cursor.fetchone()['count']
            
            return {
                'total_active_users': total_users,
                'users_with_keys': users_with_keys,
                'users_without_keys': users_without_keys,
                'coverage_percentage': round((users_with_keys / total_users * 100) if total_users > 0 else 0, 2)
            }
            
    except Exception as e:
        logger.error(f"Error fetching encryption key stats: {str(e)}")
        raise


def generate_keys_for_users(users: List[Dict[str, Any]], conn, dry_run: bool = False) -> Dict[str, Any]:
    """
    Generate encryption keys for a list of users.
    
    Args:
        users: List of user dictionaries
        conn: Database connection
        dry_run: If True, only simulate the operation
        
    Returns:
        Dict with generation results
    """
    results = {
        'total': len(users),
        'successful': 0,
        'failed': 0,
        'skipped': 0,
        'errors': []
    }
    
    logger.info(f"{'[DRY RUN] ' if dry_run else ''}Starting key generation for {len(users)} users...")
    
    for idx, user in enumerate(users, 1):
        user_id = user['user_id']
        user_email = user.get('user_email', 'unknown')
        user_name = f"{user.get('first_name', '')} {user.get('last_name', '')}".strip()
        
        try:
            logger.info(f"[{idx}/{len(users)}] Processing user: {user_id} ({user_name} - {user_email})")
            
            if dry_run:
                logger.info(f"  [DRY RUN] Would generate encryption key for user: {user_id}")
                results['skipped'] += 1
            else:
                # Generate and store key
                result = generate_and_store_user_key(
                    user_id=user_id,
                    conn=conn,
                    performed_by='system_script',
                    ip_address='127.0.0.1'
                )
                
                if result['success']:
                    logger.info(f"  ✓ Successfully generated key for user: {user_id}")
                    results['successful'] += 1
                else:
                    logger.warning(f"  ✗ Failed to generate key for user: {user_id}")
                    results['failed'] += 1
                    results['errors'].append({
                        'user_id': user_id,
                        'error': 'Key generation returned success=False'
                    })
                
                # Small delay to avoid overwhelming KMS
                time.sleep(0.1)
                
        except Exception as e:
            logger.error(f"  ✗ Error generating key for user {user_id}: {str(e)}")
            results['failed'] += 1
            results['errors'].append({
                'user_id': user_id,
                'error': str(e)
            })
    
    return results


def main():
    """Main execution function."""
    parser = argparse.ArgumentParser(description='Generate encryption keys for users')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be done without making changes')
    parser.add_argument('--force', action='store_true', help='Regenerate keys even for users who already have them')
    args = parser.parse_args()
    
    conn = None
    
    try:
        logger.info("=" * 80)
        logger.info("ENCRYPTION KEY GENERATION SCRIPT")
        logger.info("=" * 80)
        
        if args.dry_run:
            logger.info("*** DRY RUN MODE - No changes will be made ***")
        if args.force:
            logger.warning("*** FORCE MODE - Will regenerate ALL user keys ***")
        
        logger.info("")
        
        # Connect to database
        logger.info("Connecting to database...")
        conn = get_db_connection()
        
        # Get current statistics
        logger.info("Fetching current encryption key statistics...")
        stats = get_encryption_key_stats(conn)
        
        logger.info("")
        logger.info("Current Status:")
        logger.info(f"  Total active users: {stats['total_active_users']}")
        logger.info(f"  Users with keys: {stats['users_with_keys']}")
        logger.info(f"  Users without keys: {stats['users_without_keys']}")
        logger.info(f"  Coverage: {stats['coverage_percentage']}%")
        logger.info("")
        
        # Get users needing keys
        logger.info("Fetching users needing encryption keys...")
        users = get_users_needing_keys(conn, force=args.force)
        
        if not users:
            logger.info("✓ All users already have encryption keys. Nothing to do!")
            return 0
        
        logger.info(f"Found {len(users)} users needing encryption keys")
        logger.info("")
        
        # Confirm if not dry-run
        if not args.dry_run:
            response = input(f"Generate encryption keys for {len(users)} users? (yes/no): ")
            if response.lower() != 'yes':
                logger.info("Operation cancelled by user")
                return 0
            logger.info("")
        
        # Generate keys
        start_time = time.time()
        results = generate_keys_for_users(users, conn, dry_run=args.dry_run)
        elapsed_time = time.time() - start_time
        
        # Print results
        logger.info("")
        logger.info("=" * 80)
        logger.info("RESULTS")
        logger.info("=" * 80)
        logger.info(f"Total users processed: {results['total']}")
        logger.info(f"Successful: {results['successful']}")
        logger.info(f"Failed: {results['failed']}")
        logger.info(f"Skipped (dry-run): {results['skipped']}")
        logger.info(f"Time elapsed: {elapsed_time:.2f} seconds")
        
        if results['errors']:
            logger.info("")
            logger.info("Errors:")
            for error in results['errors']:
                logger.error(f"  - User {error['user_id']}: {error['error']}")
        
        # Get updated statistics if not dry-run
        if not args.dry_run:
            logger.info("")
            logger.info("Fetching updated statistics...")
            updated_stats = get_encryption_key_stats(conn)
            
            logger.info("")
            logger.info("Updated Status:")
            logger.info(f"  Total active users: {updated_stats['total_active_users']}")
            logger.info(f"  Users with keys: {updated_stats['users_with_keys']}")
            logger.info(f"  Users without keys: {updated_stats['users_without_keys']}")
            logger.info(f"  Coverage: {updated_stats['coverage_percentage']}%")
        
        logger.info("")
        logger.info("=" * 80)
        
        return 0 if results['failed'] == 0 else 1
        
    except Exception as e:
        logger.error(f"Fatal error: {str(e)}")
        return 1
        
    finally:
        if conn:
            close_db_connection(conn)
            logger.info("Database connection closed")


if __name__ == '__main__':
    sys.exit(main())

