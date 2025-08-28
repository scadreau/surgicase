# Created: 2025-08-01 20:06:31
# Last Modified: 2025-08-28 20:02:20
# Author: Scott Cadreau

"""
Database backup utility for nightly backups.

This module provides functionality to:
1. Create MySQL dumps of all database tables except npi* and search_* tables
2. Store backups locally in ~/vol2/db_backups
3. Upload backups to S3 bucket under /private/db_backups
4. Compress backups using gzip
5. Add monitoring and error tracking
"""

import os
import sys
import subprocess
import gzip
import shutil
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List
import pymysql.cursors

# Add the project root to the Python path for standalone execution
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(project_root)

from core.database import get_db_connection, close_db_connection, get_db_credentials
from utils.s3_storage import upload_file_to_s3, get_s3_config
from utils.encryption import encrypt_backup_file

# Import monitoring utilities - fallback if not available
try:
    from utils.monitoring import track_database_operation
except ImportError:
    # Fallback decorator if monitoring is not available
    def track_database_operation(operation, table="unknown"):
        def decorator(func):
            return func
        return decorator

logger = logging.getLogger(__name__)

def get_filtered_table_list() -> List[str]:
    """
    Get list of database tables excluding npi* and search_* tables.
    
    Returns:
        List of table names to backup
    """
    conn = None
    filtered_tables = []
    
    try:
        conn = get_db_connection()
        
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            # Get all table names
            cursor.execute("SHOW TABLES")
            tables = cursor.fetchall()
            
            for table_info in tables:
                table_name = list(table_info.values())[0]
                
                # Skip tables that start with 'npi' or 'search_'
                if not (table_name.startswith('npi') or table_name.startswith('search_')):
                    filtered_tables.append(table_name)
            
        logger.info(f"Found {len(filtered_tables)} tables to backup (excluding npi* and search_* tables)")
        return filtered_tables
        
    except Exception as e:
        logger.error(f"Error getting table list: {str(e)}")
        raise
        
    finally:
        if conn:
            close_db_connection(conn)

def create_mysqldump(backup_file_path: str, tables_to_backup: List[str]) -> bool:
    """
    Create a MySQL dump file for specified tables.
    
    Args:
        backup_file_path: Path where the backup file should be created
        tables_to_backup: List of table names to include in backup
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # Get database credentials
        secretdb = get_db_credentials("arn:aws:secretsmanager:us-east-1:002118831669:secret:rds!cluster-9376049b-abee-46d9-9cdb-95b95d6cdda0-fjhTNH")
        
        # Database connection parameters
        rds_host = "dev1-metoray-aurora-a98fdy.cluster-cahckueig7sf.us-east-1.rds.amazonaws.com"
        db_name = "allstars"
        db_user = secretdb["username"]
        db_pass = secretdb["password"]
        
        # Build mysqldump command
        cmd = [
            "mysqldump",
            f"--host={rds_host}",
            f"--user={db_user}",
            f"--password={db_pass}",
            "--no-tablespaces",     # Skip tablespace info (requires less permissions)
            "--skip-add-locks",     # Skip LOCK TABLES statements  
            "--skip-lock-tables",   # Don't use LOCK TABLES
            "--routines",           # Include stored procedures and functions
            "--triggers",           # Include triggers
            "--quick",             # Retrieve rows one at a time
            "--compress",          # Use compression protocol
            db_name
        ] + tables_to_backup  # Add table names to command
        
        # Execute mysqldump and save to file
        with open(backup_file_path, 'w') as backup_file:
            process = subprocess.run(
                cmd,
                stdout=backup_file,
                stderr=subprocess.PIPE,
                text=True,
                timeout=3600  # 1 hour timeout
            )
        
        if process.returncode != 0:
            logger.error(f"mysqldump failed with return code {process.returncode}")
            logger.error(f"Error output: {process.stderr}")
            return False
        
        # Check if file was created and has content
        if os.path.exists(backup_file_path) and os.path.getsize(backup_file_path) > 0:
            file_size_mb = os.path.getsize(backup_file_path) / (1024 * 1024)
            logger.info(f"Backup file created successfully: {backup_file_path} ({file_size_mb:.2f} MB)")
            return True
        else:
            logger.error("Backup file was not created or is empty")
            return False
            
    except subprocess.TimeoutExpired:
        logger.error("mysqldump timed out after 1 hour")
        return False
    except Exception as e:
        logger.error(f"Error creating mysqldump: {str(e)}")
        return False

def compress_backup_file(backup_file_path: str) -> str:
    """
    Compress backup file using gzip.
    
    Args:
        backup_file_path: Path to the uncompressed backup file
        
    Returns:
        str: Path to the compressed file
    """
    compressed_file_path = f"{backup_file_path}.gz"
    
    try:
        with open(backup_file_path, 'rb') as f_in:
            with gzip.open(compressed_file_path, 'wb') as f_out:
                shutil.copyfileobj(f_in, f_out)
        
        # Remove uncompressed file
        os.remove(backup_file_path)
        
        # Log compression stats
        compressed_size_mb = os.path.getsize(compressed_file_path) / (1024 * 1024)
        logger.info(f"Backup compressed successfully: {compressed_file_path} ({compressed_size_mb:.2f} MB)")
        
        return compressed_file_path
        
    except Exception as e:
        logger.error(f"Error compressing backup file: {str(e)}")
        # If compression fails, return original file path
        return backup_file_path

def upload_backup_to_s3(local_file_path: str, backup_filename: str, 
                        encryption_info_path: str = None) -> Dict[str, Any]:
    """
    Upload encrypted backup file and encryption info to S3 bucket under /private/db_backups.
    
    Args:
        local_file_path: Path to the local backup file
        backup_filename: Name of the backup file
        encryption_info_path: Path to encryption info file (optional)
        
    Returns:
        Dict with upload results
    """
    try:
        # Generate S3 key for private db backups
        s3_key = f"private/db_backups/{backup_filename}"
        
        # Upload encrypted backup to S3 with KMS server-side encryption
        result = upload_file_to_s3(
            file_path=local_file_path,
            s3_key=s3_key,
            content_type='application/octet-stream',  # Encrypted binary data
            metadata={
                'backup_type': 'database_encrypted',
                'backup_date': datetime.now(timezone.utc).isoformat(),
                'excluded_tables': 'npi*,search_*',
                'encryption': 'AES-256-GCM+KMS',
                'compliance': 'HIPAA'
            },
            server_side_encryption='aws:kms'  # Use KMS for additional S3-level encryption
        )
        
        # Also upload encryption info file if provided
        if encryption_info_path and os.path.exists(encryption_info_path):
            encryption_info_filename = f"{backup_filename}.encryption_info"
            encryption_info_s3_key = f"private/db_backups/{encryption_info_filename}"
            
            encryption_info_result = upload_file_to_s3(
                file_path=encryption_info_path,
                s3_key=encryption_info_s3_key,
                content_type='application/json',
                metadata={
                    'backup_type': 'encryption_metadata',
                    'backup_date': datetime.now(timezone.utc).isoformat(),
                    'associated_backup': backup_filename
                },
                server_side_encryption='aws:kms'
            )
            
            result['encryption_info_upload'] = encryption_info_result
        
        return result
        
    except Exception as e:
        logger.error(f"Error uploading backup to S3: {str(e)}")
        return {
            "success": False,
            "message": f"S3 upload failed: {str(e)}"
        }

@track_database_operation("backup", "all_tables")
def perform_database_backup() -> Dict[str, Any]:
    """
    Perform complete database backup operation.
    
    This function:
    1. Gets list of tables to backup (excluding npi* and search_* tables)
    2. Creates mysqldump backup file
    3. Compresses the backup file
    4. Stores backup in ~/vol2/db_backups
    5. Uploads backup to S3 bucket
    6. Returns operation results
    
    Returns:
        Dict containing backup operation results
    """
    start_time = datetime.now(timezone.utc)
    
    try:
        logger.info("Starting database backup operation...")
        
        # Create backup directory if it doesn't exist
        backup_dir = os.path.expanduser("~/vol2/db_backups")
        os.makedirs(backup_dir, exist_ok=True)
        
        # Generate backup filename with timestamp
        timestamp = start_time.strftime("%Y%m%d_%H%M%S")
        backup_filename = f"db_backup_{timestamp}.sql"
        compressed_filename = f"db_backup_{timestamp}.sql.gz"
        local_backup_path = os.path.join(backup_dir, backup_filename)
        
        # Get filtered table list
        tables_to_backup = get_filtered_table_list()
        if not tables_to_backup:
            raise Exception("No tables found to backup")
        
        # Create mysqldump
        logger.info(f"Creating backup of {len(tables_to_backup)} tables...")
        if not create_mysqldump(local_backup_path, tables_to_backup):
            raise Exception("Failed to create mysqldump")
        
        # Compress backup file
        logger.info("Compressing backup file...")
        compressed_file_path = compress_backup_file(local_backup_path)
        
        # Encrypt backup file for HIPAA compliance
        logger.info("Encrypting backup file for HIPAA compliance...")
        encryption_metadata = {
            'backup_date': start_time.isoformat() + "Z",
            'tables_count': len(tables_to_backup),
            'excluded_tables': 'npi*,search_*',
            'backup_type': 'database_dump',
            'compression': 'gzip'
        }
        
        encryption_result = encrypt_backup_file(compressed_file_path, encryption_metadata)
        
        if not encryption_result['success']:
            raise Exception(f"Failed to encrypt backup: {encryption_result.get('error', 'Unknown error')}")
        
        encrypted_file_path = encryption_result['encrypted_file_path']
        encryption_info_path = encryption_result['encryption_info_path']
        
        # Remove unencrypted compressed file for security
        os.remove(compressed_file_path)
        logger.info("Removed unencrypted backup file for security")
        
        # Upload encrypted backup to S3
        logger.info("Uploading encrypted backup to S3...")
        encrypted_filename = f"db_backup_{timestamp}.sql.gz.encrypted"
        s3_result = upload_backup_to_s3(encrypted_file_path, encrypted_filename, encryption_info_path)
        
        # Calculate execution time
        end_time = datetime.now(timezone.utc)
        execution_time = (end_time - start_time).total_seconds()
        
        # Get final encrypted file size
        final_size_mb = os.path.getsize(encrypted_file_path) / (1024 * 1024)
        
        result = {
            "status": "success",
            "backup_file": encrypted_file_path,
            "backup_filename": encrypted_filename,
            "tables_backed_up": len(tables_to_backup),
            "table_names": tables_to_backup,
            "file_size_mb": final_size_mb,
            "execution_time_seconds": execution_time,
            "s3_upload": s3_result,
            "encryption": {
                "enabled": True,
                "algorithm": "AES-256-GCM+KMS",
                "kms_key_id": encryption_result['encryption_info']['kms_key_id'],
                "encryption_info_file": encryption_info_path
            },
            "timestamp": start_time.isoformat() + "Z",
            "hipaa_compliant": True
        }
        
        logger.info(f"Database backup completed successfully in {execution_time:.2f} seconds")
        logger.info(f"Encrypted backup file: {encrypted_file_path} ({final_size_mb:.2f} MB)")
        logger.info(f"Tables backed up: {len(tables_to_backup)}")
        logger.info(f"Encryption: ✅ HIPAA-compliant AES-256-GCM+KMS")
        logger.info(f"S3 upload: {'✅ Success' if s3_result['success'] else '❌ Failed'}")
        
        return result
        
    except Exception as e:
        end_time = datetime.now(timezone.utc)
        execution_time = (end_time - start_time).total_seconds()
        
        error_result = {
            "status": "error",
            "error": str(e),
            "execution_time_seconds": execution_time,
            "timestamp": start_time.isoformat() + "Z"
        }
        
        logger.error(f"Database backup failed after {execution_time:.2f} seconds: {str(e)}")
        return error_result

def cleanup_old_backups(days_to_keep: int = 7) -> Dict[str, Any]:
    """
    Clean up old backup files from local storage.
    
    Args:
        days_to_keep: Number of days of backups to retain
        
    Returns:
        Dict with cleanup results
    """
    try:
        backup_dir = os.path.expanduser("~/vol2/db_backups")
        
        if not os.path.exists(backup_dir):
            return {"status": "success", "message": "Backup directory does not exist"}
        
        current_time = datetime.now(timezone.utc)
        deleted_files = []
        
        for filename in os.listdir(backup_dir):
            # Handle both encrypted files (.gz.encrypted, .encryption_info) and old unencrypted files (.gz)
            if filename.startswith("db_backup_") and (
                filename.endswith(".gz.encrypted") or 
                filename.endswith(".encryption_info") or 
                (filename.endswith(".gz") and not filename.endswith(".gz.encrypted"))
            ):
                file_path = os.path.join(backup_dir, filename)
                file_mtime = datetime.fromtimestamp(os.path.getmtime(file_path), tz=timezone.utc)
                
                # Delete files older than specified days
                if (current_time - file_mtime).days > days_to_keep:
                    os.remove(file_path)
                    deleted_files.append(filename)
        
        result = {
            "status": "success",
            "deleted_files": deleted_files,
            "files_deleted": len(deleted_files),
            "days_to_keep": days_to_keep
        }
        
        if deleted_files:
            logger.info(f"Cleaned up {len(deleted_files)} old backup files")
        else:
            logger.info("No old backup files to clean up")
        
        return result
        
    except Exception as e:
        logger.error(f"Error during backup cleanup: {str(e)}")
        return {
            "status": "error",
            "error": str(e)
        }

def run_backup_now():
    """
    Utility function to run database backup immediately (for testing).
    """
    logger.info("Running database backup immediately...")
    result = perform_database_backup()
    
    # Also run cleanup
    cleanup_result = cleanup_old_backups()
    
    return {
        "backup": result,
        "cleanup": cleanup_result
    }

if __name__ == "__main__":
    # Allow running the backup directly from command line
    print("SurgiCase Database Backup Utility")
    print("=" * 50)
    
    result = run_backup_now()
    
    if result["backup"]["status"] == "success":
        print("✅ Backup completed successfully")
    else:
        print("❌ Backup failed")
        print(f"Error: {result['backup'].get('error', 'Unknown error')}")