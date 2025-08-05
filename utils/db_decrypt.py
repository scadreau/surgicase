# Created: 2025-08-05 22:50:39
# Last Modified: 2025-08-05 22:53:23
# Author: Scott Cadreau

"""
Database backup decryption utility for HIPAA-encrypted backups.

This module provides functionality to:
1. Decrypt database backup files encrypted with the encryption.py module
2. Download encrypted backups from S3 
3. Restore database backups from encrypted files
4. Verify backup integrity after decryption
"""

import os
import sys
import gzip
import logging
import subprocess
from datetime import datetime, timezone
from typing import Dict, Any, Optional
import boto3
from botocore.exceptions import ClientError

# Add the project root to the Python path for standalone execution
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(project_root)

from core.database import get_db_credentials
from utils.encryption import decrypt_backup_file, HIPAAEncryption
from utils.s3_storage import download_file_from_s3, list_s3_objects

logger = logging.getLogger(__name__)

def list_encrypted_backups(max_results: int = 20) -> Dict[str, Any]:
    """
    List available encrypted backups in S3.
    
    Args:
        max_results: Maximum number of backups to return
        
    Returns:
        Dict with list of available backups
    """
    try:
        logger.info("Listing encrypted backups from S3...")
        
        # List objects in the backup directory
        backup_objects = list_s3_objects(
            prefix="private/db_backups/",
            max_keys=max_results * 2  # Get more to filter encrypted files
        )
        
        encrypted_backups = []
        
        for obj in backup_objects.get('objects', []):
            key = obj['Key']
            
            # Only include encrypted backup files (not encryption_info files)
            if key.endswith('.gz.encrypted'):
                backup_info = {
                    'filename': os.path.basename(key),
                    's3_key': key,
                    'size_mb': obj['Size'] / (1024 * 1024),
                    'last_modified': obj['LastModified'].isoformat(),
                    'encryption_info_key': f"{key}.encryption_info"
                }
                encrypted_backups.append(backup_info)
        
        # Sort by last modified (newest first)
        encrypted_backups.sort(key=lambda x: x['last_modified'], reverse=True)
        
        # Limit results
        encrypted_backups = encrypted_backups[:max_results]
        
        logger.info(f"Found {len(encrypted_backups)} encrypted backups")
        
        return {
            'success': True,
            'backups': encrypted_backups,
            'count': len(encrypted_backups)
        }
        
    except Exception as e:
        logger.error(f"Error listing encrypted backups: {str(e)}")
        return {
            'success': False,
            'error': str(e),
            'backups': [],
            'count': 0
        }

def download_encrypted_backup(s3_key: str, local_dir: str = None) -> Dict[str, Any]:
    """
    Download an encrypted backup and its encryption info from S3.
    
    Args:
        s3_key: S3 key of the encrypted backup file
        local_dir: Local directory to download to (optional)
        
    Returns:
        Dict with download results
    """
    try:
        if local_dir is None:
            local_dir = os.path.expanduser("~/vol2/db_restore")
        
        os.makedirs(local_dir, exist_ok=True)
        
        # Download encrypted backup file
        backup_filename = os.path.basename(s3_key)
        local_backup_path = os.path.join(local_dir, backup_filename)
        
        logger.info(f"Downloading encrypted backup: {s3_key}")
        backup_result = download_file_from_s3(s3_key, local_backup_path)
        
        if not backup_result['success']:
            raise Exception(f"Failed to download backup: {backup_result.get('message', 'Unknown error')}")
        
        # Download encryption info file
        encryption_info_key = f"{s3_key}.encryption_info"
        encryption_info_filename = f"{backup_filename}.encryption_info"
        local_encryption_info_path = os.path.join(local_dir, encryption_info_filename)
        
        logger.info(f"Downloading encryption info: {encryption_info_key}")
        encryption_info_result = download_file_from_s3(encryption_info_key, local_encryption_info_path)
        
        if not encryption_info_result['success']:
            logger.warning(f"Failed to download encryption info: {encryption_info_result.get('message', 'Unknown error')}")
            # Continue without encryption info file (it's embedded in the file path)
        
        return {
            'success': True,
            'backup_file': local_backup_path,
            'encryption_info_file': local_encryption_info_path if encryption_info_result['success'] else None,
            'download_dir': local_dir
        }
        
    except Exception as e:
        logger.error(f"Error downloading encrypted backup: {str(e)}")
        return {
            'success': False,
            'error': str(e)
        }

def decrypt_database_backup(encrypted_file_path: str, output_dir: str = None) -> Dict[str, Any]:
    """
    Decrypt a database backup file.
    
    Args:
        encrypted_file_path: Path to the encrypted backup file
        output_dir: Directory for decrypted output (optional)
        
    Returns:
        Dict with decryption results
    """
    try:
        if output_dir is None:
            output_dir = os.path.dirname(encrypted_file_path)
        
        os.makedirs(output_dir, exist_ok=True)
        
        # Generate output filename (remove .encrypted extension)
        if encrypted_file_path.endswith('.encrypted'):
            decrypted_filename = os.path.basename(encrypted_file_path)[:-10]  # Remove .encrypted
        else:
            decrypted_filename = f"{os.path.basename(encrypted_file_path)}.decrypted"
        
        decrypted_file_path = os.path.join(output_dir, decrypted_filename)
        
        logger.info(f"Decrypting backup file: {encrypted_file_path}")
        
        # Decrypt the file
        decryption_result = decrypt_backup_file(encrypted_file_path, decrypted_file_path)
        
        if not decryption_result['success']:
            raise Exception(f"Decryption failed: {decryption_result.get('error', 'Unknown error')}")
        
        # Verify the decrypted file is a valid gzip file
        if decrypted_filename.endswith('.gz'):
            try:
                with gzip.open(decrypted_file_path, 'rt') as f:
                    # Try to read first few lines to verify it's a valid SQL dump
                    first_lines = []
                    for i, line in enumerate(f):
                        first_lines.append(line.strip())
                        if i >= 10:  # Read first 10 lines
                            break
                    
                    # Check if it looks like a MySQL dump
                    sql_indicators = ['-- MySQL dump', 'CREATE TABLE', 'INSERT INTO', 'DROP TABLE']
                    is_valid_sql = any(indicator in ' '.join(first_lines) for indicator in sql_indicators)
                    
                    if not is_valid_sql:
                        logger.warning("Decrypted file may not be a valid SQL dump")
                    else:
                        logger.info("✅ Decrypted file appears to be a valid SQL dump")
                        
            except Exception as e:
                logger.warning(f"Could not verify decrypted file format: {str(e)}")
        
        return {
            'success': True,
            'decrypted_file': decrypted_file_path,
            'original_size_mb': decryption_result['original_file_size'] / (1024 * 1024),
            'encryption_info': decryption_result['encryption_info']
        }
        
    except Exception as e:
        logger.error(f"Error decrypting backup: {str(e)}")
        return {
            'success': False,
            'error': str(e)
        }

def restore_database_from_backup(decrypted_backup_path: str, 
                                target_database: str = None,
                                dry_run: bool = True) -> Dict[str, Any]:
    """
    Restore database from a decrypted backup file.
    
    Args:
        decrypted_backup_path: Path to decrypted SQL backup file
        target_database: Target database name (optional, defaults to 'allstars')
        dry_run: If True, only validate the backup without restoring
        
    Returns:
        Dict with restoration results
    """
    try:
        if target_database is None:
            target_database = "allstars"
        
        logger.info(f"{'Validating' if dry_run else 'Restoring'} database backup: {decrypted_backup_path}")
        
        # Get database credentials
        secretdb = get_db_credentials("arn:aws:secretsmanager:us-east-1:002118831669:secret:rds!cluster-9376049b-abee-46d9-9cdb-95b95d6cdda0-fjhTNH")
        
        # Database connection parameters
        rds_host = "dev1-metoray-aurora-a98fdy.cluster-cahckueig7sf.us-east-1.rds.amazonaws.com"
        db_user = secretdb["username"]
        db_pass = secretdb["password"]
        
        if dry_run:
            # Validate the backup file without actually restoring
            logger.info("Performing dry run validation...")
            
            # Check if file exists and is readable
            if not os.path.exists(decrypted_backup_path):
                raise FileNotFoundError(f"Backup file not found: {decrypted_backup_path}")
            
            file_size_mb = os.path.getsize(decrypted_backup_path) / (1024 * 1024)
            logger.info(f"Backup file size: {file_size_mb:.2f} MB")
            
            # Try to read and parse the file
            if decrypted_backup_path.endswith('.gz'):
                open_func = gzip.open
                mode = 'rt'
            else:
                open_func = open
                mode = 'r'
            
            table_count = 0
            insert_count = 0
            
            with open_func(decrypted_backup_path, mode) as f:
                for line_num, line in enumerate(f):
                    if line.startswith('CREATE TABLE'):
                        table_count += 1
                    elif line.startswith('INSERT INTO'):
                        insert_count += 1
                    
                    # Don't read the entire file for validation
                    if line_num > 10000:
                        break
            
            return {
                'success': True,
                'dry_run': True,
                'file_size_mb': file_size_mb,
                'tables_found': table_count,
                'insert_statements_found': insert_count,
                'message': 'Backup file validation successful'
            }
        
        else:
            # Actually restore the database
            logger.warning("🚨 PERFORMING ACTUAL DATABASE RESTORE - THIS WILL OVERWRITE EXISTING DATA!")
            
            # Build mysql restore command
            if decrypted_backup_path.endswith('.gz'):
                cmd = f"gunzip -c {decrypted_backup_path} | mysql --host={rds_host} --user={db_user} --password={db_pass} {target_database}"
            else:
                cmd = f"mysql --host={rds_host} --user={db_user} --password={db_pass} {target_database} < {decrypted_backup_path}"
            
            # Execute restore
            process = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=7200  # 2 hour timeout
            )
            
            if process.returncode != 0:
                logger.error(f"Database restore failed with return code {process.returncode}")
                logger.error(f"Error output: {process.stderr}")
                return {
                    'success': False,
                    'error': f"Database restore failed: {process.stderr}",
                    'return_code': process.returncode
                }
            
            logger.info("✅ Database restore completed successfully")
            
            return {
                'success': True,
                'dry_run': False,
                'target_database': target_database,
                'message': 'Database restore completed successfully'
            }
        
    except subprocess.TimeoutExpired:
        logger.error("Database restore timed out after 2 hours")
        return {
            'success': False,
            'error': 'Database restore timed out after 2 hours'
        }
    except Exception as e:
        logger.error(f"Error restoring database: {str(e)}")
        return {
            'success': False,
            'error': str(e)
        }

def full_backup_recovery(s3_key: str = None, backup_filename: str = None, 
                        restore_to_db: bool = False, dry_run: bool = True) -> Dict[str, Any]:
    """
    Complete backup recovery process: download, decrypt, and optionally restore.
    
    Args:
        s3_key: S3 key of backup to recover (optional, will list if not provided)
        backup_filename: Alternative to s3_key, specify just the filename
        restore_to_db: Whether to actually restore to database
        dry_run: If True, only validate without restoring
        
    Returns:
        Dict with complete recovery results
    """
    recovery_start = datetime.now(timezone.utc)
    
    try:
        logger.info("Starting full backup recovery process...")
        
        # If no specific backup specified, list available backups
        if not s3_key and not backup_filename:
            logger.info("No specific backup specified, listing available backups...")
            backup_list = list_encrypted_backups(10)
            
            if not backup_list['success'] or not backup_list['backups']:
                raise Exception("No encrypted backups found")
            
            # Use the most recent backup
            s3_key = backup_list['backups'][0]['s3_key']
            logger.info(f"Using most recent backup: {s3_key}")
        
        elif backup_filename and not s3_key:
            s3_key = f"private/db_backups/{backup_filename}"
        
        # Download encrypted backup
        logger.info("Step 1: Downloading encrypted backup...")
        download_result = download_encrypted_backup(s3_key)
        
        if not download_result['success']:
            raise Exception(f"Download failed: {download_result.get('error', 'Unknown error')}")
        
        # Decrypt backup
        logger.info("Step 2: Decrypting backup...")
        decryption_result = decrypt_database_backup(download_result['backup_file'])
        
        if not decryption_result['success']:
            raise Exception(f"Decryption failed: {decryption_result.get('error', 'Unknown error')}")
        
        # Validate/Restore database
        if restore_to_db:
            logger.info("Step 3: Restoring to database...")
            restore_result = restore_database_from_backup(
                decryption_result['decrypted_file'],
                dry_run=dry_run
            )
            
            if not restore_result['success']:
                raise Exception(f"Restore failed: {restore_result.get('error', 'Unknown error')}")
        else:
            logger.info("Step 3: Validating decrypted backup...")
            restore_result = restore_database_from_backup(
                decryption_result['decrypted_file'],
                dry_run=True
            )
        
        # Calculate total time
        recovery_end = datetime.now(timezone.utc)
        total_time = (recovery_end - recovery_start).total_seconds()
        
        result = {
            'success': True,
            'backup_s3_key': s3_key,
            'download_result': download_result,
            'decryption_result': decryption_result,
            'restore_result': restore_result,
            'total_time_seconds': total_time,
            'recovery_complete': True
        }
        
        logger.info(f"✅ Backup recovery completed successfully in {total_time:.2f} seconds")
        
        return result
        
    except Exception as e:
        recovery_end = datetime.now(timezone.utc)
        total_time = (recovery_end - recovery_start).total_seconds()
        
        logger.error(f"❌ Backup recovery failed after {total_time:.2f} seconds: {str(e)}")
        
        return {
            'success': False,
            'error': str(e),
            'total_time_seconds': total_time
        }

if __name__ == "__main__":
    # Allow running recovery operations from command line
    import argparse
    
    parser = argparse.ArgumentParser(description='SurgiCase Database Backup Recovery Utility')
    parser.add_argument('--list', action='store_true', help='List available encrypted backups')
    parser.add_argument('--decrypt', type=str, help='Decrypt specific backup file (local path)')
    parser.add_argument('--recover', type=str, help='Full recovery from S3 (S3 key or filename)')
    parser.add_argument('--restore', action='store_true', help='Actually restore to database (not dry run)')
    parser.add_argument('--output-dir', type=str, help='Output directory for decrypted files')
    
    args = parser.parse_args()
    
    print("SurgiCase Database Backup Recovery Utility")
    print("=" * 60)
    
    if args.list:
        print("📋 Listing available encrypted backups...")
        result = list_encrypted_backups()
        
        if result['success']:
            print(f"\n✅ Found {result['count']} encrypted backups:")
            for i, backup in enumerate(result['backups'], 1):
                print(f"{i:2d}. {backup['filename']}")
                print(f"    Size: {backup['size_mb']:.2f} MB")
                print(f"    Date: {backup['last_modified']}")
                print()
        else:
            print(f"❌ Error: {result['error']}")
    
    elif args.decrypt:
        print(f"🔓 Decrypting backup: {args.decrypt}")
        result = decrypt_database_backup(args.decrypt, args.output_dir)
        
        if result['success']:
            print(f"✅ Decryption successful!")
            print(f"   Decrypted file: {result['decrypted_file']}")
            print(f"   Size: {result['original_size_mb']:.2f} MB")
        else:
            print(f"❌ Decryption failed: {result['error']}")
    
    elif args.recover:
        print(f"🔄 Starting full recovery: {args.recover}")
        result = full_backup_recovery(
            s3_key=args.recover if args.recover.startswith('private/') else None,
            backup_filename=args.recover if not args.recover.startswith('private/') else None,
            restore_to_db=args.restore,
            dry_run=not args.restore
        )
        
        if result['success']:
            print("✅ Recovery completed successfully!")
            if args.restore:
                print("🚨 Database has been restored!")
            else:
                print("📝 Dry run completed - no changes made to database")
        else:
            print(f"❌ Recovery failed: {result['error']}")
    
    else:
        parser.print_help()