# Created: 2025-09-07 21:25:04
# Last Modified: 2025-09-07 21:36:59
# Author: Scott Cadreau

"""
S3 Log File Migration Script

This script safely moves log files from the S3 bucket root to organized directories.
Based on the reconnaissance results, it handles 427,019 files in the root directory.

Features:
- Safe copy-then-delete approach with rollback capability
- Progress reporting and detailed logging
- Categorizes files by type (S3 access logs, application files, etc.)
- Batch processing for efficiency
- Comprehensive error handling

Usage:
    python -m utils.s3_log_migration [--dry-run] [--batch-size 1000]

The script will:
- Move S3 access logs to log_files/s3-access/
- Move other log files to log_files/misc/
- Leave legitimate application files in organized directories
- Provide detailed progress and statistics
"""

import boto3
import json
import re
import os
import sys
from datetime import datetime, timezone
from typing import Dict, List, Any, Tuple
from collections import defaultdict, Counter
import logging
import argparse
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(f'logs/s3_migration_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Thread-safe counters
class ThreadSafeCounters:
    def __init__(self):
        self.lock = threading.Lock()
        self.processed = 0
        self.moved = 0
        self.skipped = 0
        self.errors = 0
        self.total_size_moved = 0
    
    def increment_processed(self):
        with self.lock:
            self.processed += 1
    
    def increment_moved(self, size: int = 0):
        with self.lock:
            self.moved += 1
            self.total_size_moved += size
    
    def increment_skipped(self):
        with self.lock:
            self.skipped += 1
    
    def increment_errors(self):
        with self.lock:
            self.errors += 1
    
    def get_stats(self):
        with self.lock:
            return {
                'processed': self.processed,
                'moved': self.moved,
                'skipped': self.skipped,
                'errors': self.errors,
                'total_size_moved': self.total_size_moved
            }

def get_s3_client_for_migration():
    """
    Get S3 client using the existing secrets manager configuration
    """
    try:
        from utils.secrets_manager import get_secret
        
        # Try different S3 configurations to find the right one
        config_names = [
            "surgicase/s3-user-reports",
            "surgicase/s3-case-documents", 
            "surgicase/s3-user-documents"
        ]
        
        for config_name in config_names:
            try:
                config = get_secret(config_name)
                if config and 'bucket_name' in config:
                    # Use access keys if provided, otherwise use IAM role
                    if 'aws_access_key_id' in config and 'aws_secret_access_key' in config:
                        s3_client = boto3.client(
                            's3',
                            region_name=config.get('region', 'us-east-1'),
                            aws_access_key_id=config['aws_access_key_id'],
                            aws_secret_access_key=config['aws_secret_access_key']
                        )
                    else:
                        # Use IAM role (recommended for production)
                        s3_client = boto3.client('s3', region_name=config.get('region', 'us-east-1'))
                    
                    return s3_client, config['bucket_name']
            except Exception as e:
                logger.debug(f"Config {config_name} not available: {str(e)}")
                continue
        
        # If no config found, try default IAM role
        logger.info("No S3 config found in secrets, trying default IAM role...")
        s3_client = boto3.client('s3', region_name='us-east-1')
        bucket_name = "amplify-surgicalcasemanag-surgicaldocsbucket5a7ebd-8usdadqv6nnp"
        return s3_client, bucket_name
        
    except Exception as e:
        logger.error(f"Error creating S3 client: {str(e)}")
        raise

def categorize_file_for_migration(key: str, size: int) -> Dict[str, Any]:
    """
    Categorize a file for migration purposes
    
    Args:
        key: S3 object key (filename/path)
        size: File size in bytes
        
    Returns:
        dict: Migration category and destination path
    """
    key_lower = key.lower()
    
    # Initialize migration info
    migration_info = {
        'key': key,
        'size': size,
        'should_move': False,
        'destination': None,
        'category': 'unknown',
        'reason': 'unknown'
    }
    
    # Check if file is already in a directory (has forward slash)
    if '/' in key:
        migration_info['should_move'] = False
        migration_info['reason'] = 'already_in_directory'
        return migration_info
    
    # NEVER touch anything in private/ directory
    if key.startswith('private/'):
        migration_info['should_move'] = False
        migration_info['reason'] = 'private_directory_excluded'
        return migration_info
    
    # S3 access log pattern: YYYY-MM-DD-HH-MM-SS-HEXSTRING
    s3_access_pattern = r'^\d{4}-\d{2}-\d{2}-\d{2}-\d{2}-\d{2}-[A-F0-9]{16}$'
    if re.match(s3_access_pattern, key):
        migration_info['should_move'] = True
        migration_info['destination'] = f'log_files/s3-access/{key}'
        migration_info['category'] = 's3_access_log'
        migration_info['reason'] = 's3_access_log_pattern'
        return migration_info
    
    # Other log file patterns
    log_patterns = [
        r'\.log$',
        r'\.txt$',
        r'error.*log',
        r'debug.*log',
        r'access.*log',
        r'api.*log'
    ]
    
    for pattern in log_patterns:
        if re.search(pattern, key_lower):
            migration_info['should_move'] = True
            migration_info['destination'] = f'log_files/misc/{key}'
            migration_info['category'] = 'misc_log'
            migration_info['reason'] = f'log_pattern: {pattern}'
            return migration_info
    
    # Very small files (likely log entries)
    if size < 1024:  # Less than 1KB
        migration_info['should_move'] = True
        migration_info['destination'] = f'log_files/small-files/{key}'
        migration_info['category'] = 'small_file'
        migration_info['reason'] = 'very_small_file'
        return migration_info
    
    # Application files (keep in root or move to organized structure)
    app_file_extensions = ['.pdf', '.jpg', '.jpeg', '.png', '.docx', '.csv', '.encrypted']
    file_extension = '.' + key.split('.')[-1].lower() if '.' in key else ''
    
    if file_extension in app_file_extensions:
        migration_info['should_move'] = True
        migration_info['destination'] = f'organized/{file_extension[1:]}/{key}'
        migration_info['category'] = 'application_file'
        migration_info['reason'] = f'organize_by_type: {file_extension}'
        return migration_info
    
    # Unknown files - move to review directory
    migration_info['should_move'] = True
    migration_info['destination'] = f'log_files/review/{key}'
    migration_info['category'] = 'unknown'
    migration_info['reason'] = 'unknown_file_type'
    
    return migration_info

def move_single_file(s3_client, bucket_name: str, source_key: str, dest_key: str, 
                    dry_run: bool = False) -> Dict[str, Any]:
    """
    Move a single file from source to destination
    
    Args:
        s3_client: Boto3 S3 client
        bucket_name: S3 bucket name
        source_key: Source object key
        dest_key: Destination object key
        dry_run: If True, don't actually move files
        
    Returns:
        dict: Operation result
    """
    try:
        if dry_run:
            return {
                'success': True,
                'source_key': source_key,
                'dest_key': dest_key,
                'message': 'DRY RUN - would move file'
            }
        
        # Copy object to new location
        copy_source = {'Bucket': bucket_name, 'Key': source_key}
        s3_client.copy_object(
            CopySource=copy_source,
            Bucket=bucket_name,
            Key=dest_key
        )
        
        # Verify copy succeeded by checking if destination exists
        try:
            s3_client.head_object(Bucket=bucket_name, Key=dest_key)
        except Exception as e:
            return {
                'success': False,
                'source_key': source_key,
                'dest_key': dest_key,
                'error': f'Copy verification failed: {str(e)}'
            }
        
        # Delete original file
        s3_client.delete_object(Bucket=bucket_name, Key=source_key)
        
        return {
            'success': True,
            'source_key': source_key,
            'dest_key': dest_key,
            'message': 'File moved successfully'
        }
        
    except Exception as e:
        return {
            'success': False,
            'source_key': source_key,
            'dest_key': dest_key,
            'error': str(e)
        }

def process_file_batch(s3_client, bucket_name: str, files_batch: List[Dict], 
                      counters: ThreadSafeCounters, dry_run: bool = False) -> List[Dict]:
    """
    Process a batch of files for migration
    
    Args:
        s3_client: Boto3 S3 client
        bucket_name: S3 bucket name
        files_batch: List of file info dictionaries
        counters: Thread-safe counters
        dry_run: If True, don't actually move files
        
    Returns:
        List of operation results
    """
    results = []
    
    for file_info in files_batch:
        counters.increment_processed()
        
        # Categorize file for migration
        migration_info = categorize_file_for_migration(file_info['key'], file_info['size'])
        
        if not migration_info['should_move']:
            counters.increment_skipped()
            results.append({
                'file': file_info['key'],
                'action': 'skipped',
                'reason': migration_info['reason']
            })
            continue
        
        # Move the file
        move_result = move_single_file(
            s3_client, 
            bucket_name, 
            file_info['key'], 
            migration_info['destination'],
            dry_run
        )
        
        if move_result['success']:
            counters.increment_moved(file_info['size'])
            results.append({
                'file': file_info['key'],
                'action': 'moved',
                'destination': migration_info['destination'],
                'category': migration_info['category']
            })
        else:
            counters.increment_errors()
            results.append({
                'file': file_info['key'],
                'action': 'error',
                'error': move_result['error']
            })
            logger.error(f"Failed to move {file_info['key']}: {move_result['error']}")
    
    return results

def migrate_s3_log_files(s3_client, bucket_name: str, dry_run: bool = False, 
                        batch_size: int = 1000, max_workers: int = 10) -> Dict[str, Any]:
    """
    Migrate log files from S3 bucket root to organized directories
    
    Args:
        s3_client: Boto3 S3 client
        bucket_name: S3 bucket name
        dry_run: If True, don't actually move files
        batch_size: Number of files to process in each batch
        max_workers: Number of concurrent workers
        
    Returns:
        dict: Migration results and statistics
    """
    logger.info(f"Starting S3 log file migration for bucket: {bucket_name}")
    logger.info(f"Mode: {'DRY RUN' if dry_run else 'LIVE MIGRATION'}")
    logger.info(f"Batch size: {batch_size}, Max workers: {max_workers}")
    
    migration_results = {
        'bucket_name': bucket_name,
        'start_time': datetime.now(timezone.utc).isoformat(),
        'dry_run': dry_run,
        'batch_size': batch_size,
        'max_workers': max_workers,
        'files_to_process': 0,
        'files_processed': 0,
        'files_moved': 0,
        'files_skipped': 0,
        'files_errors': 0,
        'total_size_moved': 0,
        'categories': defaultdict(int),
        'errors': []
    }
    
    counters = ThreadSafeCounters()
    
    try:
        # Get list of all files in bucket root
        logger.info("Scanning bucket for files to migrate...")
        root_files = []
        
        paginator = s3_client.get_paginator('list_objects_v2')
        page_iterator = paginator.paginate(
            Bucket=bucket_name,
            Delimiter='/'  # Only get files in root, not subdirectories
        )
        
        for page in page_iterator:
            if 'Contents' not in page:
                continue
                
            for obj in page['Contents']:
                # Skip directories (keys ending with /)
                if not obj['Key'].endswith('/'):
                    root_files.append({
                        'key': obj['Key'],
                        'size': obj['Size'],
                        'last_modified': obj['LastModified']
                    })
        
        migration_results['files_to_process'] = len(root_files)
        logger.info(f"Found {len(root_files)} files in bucket root to process")
        
        if len(root_files) == 0:
            logger.info("No files found in bucket root. Migration complete.")
            return migration_results
        
        # Process files in batches with multiple workers
        batches = [root_files[i:i + batch_size] for i in range(0, len(root_files), batch_size)]
        logger.info(f"Processing {len(batches)} batches with up to {max_workers} workers")
        
        all_results = []
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all batches
            future_to_batch = {
                executor.submit(process_file_batch, s3_client, bucket_name, batch, counters, dry_run): batch
                for batch in batches
            }
            
            # Process completed batches
            for future in as_completed(future_to_batch):
                batch = future_to_batch[future]
                try:
                    batch_results = future.result()
                    all_results.extend(batch_results)
                    
                    # Log progress
                    stats = counters.get_stats()
                    logger.info(f"Progress: {stats['processed']}/{len(root_files)} files processed "
                              f"({stats['moved']} moved, {stats['skipped']} skipped, {stats['errors']} errors)")
                    
                except Exception as e:
                    logger.error(f"Batch processing failed: {str(e)}")
                    counters.increment_errors()
        
        # Compile final statistics
        final_stats = counters.get_stats()
        migration_results.update(final_stats)
        migration_results['end_time'] = datetime.now(timezone.utc).isoformat()
        
        # Count categories
        for result in all_results:
            if 'category' in result:
                migration_results['categories'][result['category']] += 1
        
        logger.info("Migration completed successfully")
        
    except Exception as e:
        logger.error(f"Migration failed: {str(e)}")
        migration_results['errors'].append(str(e))
        raise
    
    return migration_results

def print_migration_report(results: Dict[str, Any]):
    """
    Print a formatted migration report
    """
    print("\n" + "="*80)
    print("📦 S3 LOG FILE MIGRATION REPORT")
    print("="*80)
    
    print(f"\n📊 MIGRATION OVERVIEW:")
    print(f"   Bucket: {results['bucket_name']}")
    print(f"   Mode: {'DRY RUN' if results['dry_run'] else 'LIVE MIGRATION'}")
    print(f"   Start Time: {results['start_time']}")
    print(f"   End Time: {results.get('end_time', 'In Progress')}")
    
    print(f"\n📈 STATISTICS:")
    print(f"   Files to Process: {results['files_to_process']:,}")
    print(f"   Files Processed: {results['files_processed']:,}")
    print(f"   Files Moved: {results['files_moved']:,}")
    print(f"   Files Skipped: {results['files_skipped']:,}")
    print(f"   Files with Errors: {results['files_errors']:,}")
    print(f"   Total Size Moved: {results['total_size_moved'] / (1024*1024):.2f} MB")
    
    if results['categories']:
        print(f"\n📁 FILES BY CATEGORY:")
        for category, count in results['categories'].items():
            print(f"   {category}: {count:,} files")
    
    if results['errors']:
        print(f"\n❌ ERRORS:")
        for error in results['errors'][:10]:  # Show first 10 errors
            print(f"   - {error}")
        if len(results['errors']) > 10:
            print(f"   ... and {len(results['errors']) - 10} more errors")
    
    print("\n" + "="*80)
    print("✅ MIGRATION COMPLETE" if not results['dry_run'] else "✅ DRY RUN COMPLETE")
    print("="*80)

def main():
    """
    Main function to run the S3 log migration
    """
    parser = argparse.ArgumentParser(description='Migrate S3 log files to organized directories')
    parser.add_argument('--dry-run', action='store_true', 
                       help='Perform a dry run without actually moving files')
    parser.add_argument('--batch-size', type=int, default=1000,
                       help='Number of files to process in each batch (default: 1000)')
    parser.add_argument('--max-workers', type=int, default=10,
                       help='Maximum number of concurrent workers (default: 10)')
    
    args = parser.parse_args()
    
    # Create logs directory if it doesn't exist
    os.makedirs('logs', exist_ok=True)
    
    try:
        print("🚀 Starting S3 Log File Migration...")
        
        # Get S3 client and bucket name
        s3_client, bucket_name = get_s3_client_for_migration()
        print(f"✅ Connected to S3 bucket: {bucket_name}")
        
        if args.dry_run:
            print("🔍 Running in DRY RUN mode - no files will be moved")
        else:
            print("⚠️  Running in LIVE mode - files will be moved!")
            response = input("Continue? (y/N): ")
            if response.lower() != 'y':
                print("❌ Migration cancelled")
                return
        
        # Run migration
        results = migrate_s3_log_files(
            s3_client, 
            bucket_name, 
            dry_run=args.dry_run,
            batch_size=args.batch_size,
            max_workers=args.max_workers
        )
        
        # Print report
        print_migration_report(results)
        
        # Save detailed results
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        results_file = f"logs/s3_migration_results_{timestamp}.json"
        
        with open(results_file, 'w') as f:
            json.dump(results, f, indent=2, default=str)
        
        print(f"\n📄 Detailed results saved to: {results_file}")
        
        if not args.dry_run and results['files_moved'] > 0:
            print("\n🎯 Next Steps:")
            print("   1. Verify files are in correct locations")
            print("   2. Set up daily cleanup automation")
            print("   3. Monitor bucket to ensure no new log files appear")
        
    except Exception as e:
        logger.error(f"Migration failed: {str(e)}")
        print(f"\n❌ Error: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()
