# Created: 2025-08-14 16:14:56
# Last Modified: 2025-08-14 16:17:45
# Author: Scott Cadreau

"""
EC2 Monitoring Log Rotation Script

This script handles log rotation for the EC2 monitoring system:
- Creates new log files every 6 hours
- Deletes log files older than 2 days
- Compresses rotated logs to save space
- Maintains a clean log directory

Usage:
    python rotate_monitoring_logs.py

The script should be run via cron every 6 hours:
    0 */6 * * * cd /home/scadreau/surgicase && python tests/rotate_monitoring_logs.py
"""

import os
import glob
import gzip
import shutil
import logging
from datetime import datetime, timedelta
from pathlib import Path

# Configuration
LOG_DIR = "/home/scadreau/surgicase/tests"
LOG_BASENAME = "ec2_monitoring"
ROTATION_HOURS = 6
RETENTION_DAYS = 2
COMPRESS_AFTER_ROTATION = True

# Log files to rotate
LOG_FILES = [
    f"{LOG_DIR}/{LOG_BASENAME}.log",
    f"{LOG_DIR}/{LOG_BASENAME}_cron.log"
]

def setup_logging():
    """Setup logging for the rotation script itself."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(f'{LOG_DIR}/log_rotation.log'),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger(__name__)

def get_timestamp():
    """Get formatted timestamp for log file naming."""
    return datetime.now().strftime("%Y%m%d_%H%M%S")

def rotate_log_file(log_file_path: str, logger: logging.Logger) -> bool:
    """
    Rotate a single log file.
    
    Args:
        log_file_path: Path to the log file to rotate
        logger: Logger instance for this script
        
    Returns:
        bool: True if rotation was successful
    """
    try:
        if not os.path.exists(log_file_path):
            logger.info(f"Log file {log_file_path} does not exist, skipping rotation")
            return True
        
        # Check if file has content
        if os.path.getsize(log_file_path) == 0:
            logger.info(f"Log file {log_file_path} is empty, skipping rotation")
            return True
        
        # Create rotated filename with timestamp
        timestamp = get_timestamp()
        base_name = os.path.basename(log_file_path)
        name_without_ext = os.path.splitext(base_name)[0]
        rotated_name = f"{name_without_ext}_{timestamp}.log"
        rotated_path = os.path.join(os.path.dirname(log_file_path), rotated_name)
        
        # Copy the log file to rotated name
        shutil.copy2(log_file_path, rotated_path)
        logger.info(f"Rotated {log_file_path} to {rotated_path}")
        
        # Truncate the original log file (keep it open for writing processes)
        with open(log_file_path, 'w') as f:
            f.truncate(0)
        logger.info(f"Truncated original log file {log_file_path}")
        
        # Compress the rotated file if enabled
        if COMPRESS_AFTER_ROTATION:
            compressed_path = f"{rotated_path}.gz"
            with open(rotated_path, 'rb') as f_in:
                with gzip.open(compressed_path, 'wb') as f_out:
                    shutil.copyfileobj(f_in, f_out)
            
            # Remove the uncompressed rotated file
            os.remove(rotated_path)
            logger.info(f"Compressed rotated log to {compressed_path}")
        
        return True
        
    except Exception as e:
        logger.error(f"Failed to rotate log file {log_file_path}: {str(e)}")
        return False

def cleanup_old_logs(logger: logging.Logger) -> int:
    """
    Remove log files older than the retention period.
    
    Args:
        logger: Logger instance for this script
        
    Returns:
        int: Number of files removed
    """
    try:
        cutoff_time = datetime.now() - timedelta(days=RETENTION_DAYS)
        removed_count = 0
        
        # Look for rotated log files (both compressed and uncompressed)
        pattern_base = f"{LOG_DIR}/{LOG_BASENAME}*_[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]_[0-9][0-9][0-9][0-9][0-9][0-9].log*"
        old_log_files = glob.glob(pattern_base)
        
        for log_file in old_log_files:
            try:
                # Get file modification time
                file_mtime = datetime.fromtimestamp(os.path.getmtime(log_file))
                
                if file_mtime < cutoff_time:
                    os.remove(log_file)
                    logger.info(f"Removed old log file: {log_file}")
                    removed_count += 1
                    
            except Exception as e:
                logger.error(f"Failed to remove old log file {log_file}: {str(e)}")
        
        logger.info(f"Cleanup completed. Removed {removed_count} old log files")
        return removed_count
        
    except Exception as e:
        logger.error(f"Failed during log cleanup: {str(e)}")
        return 0

def get_log_stats(logger: logging.Logger) -> dict:
    """
    Get statistics about current log files.
    
    Args:
        logger: Logger instance for this script
        
    Returns:
        dict: Statistics about log files
    """
    stats = {
        'active_logs': 0,
        'rotated_logs': 0,
        'compressed_logs': 0,
        'total_size_mb': 0.0
    }
    
    try:
        # Count active log files
        for log_file in LOG_FILES:
            if os.path.exists(log_file):
                stats['active_logs'] += 1
                stats['total_size_mb'] += os.path.getsize(log_file) / (1024 * 1024)
        
        # Count rotated log files
        rotated_pattern = f"{LOG_DIR}/{LOG_BASENAME}*_[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]_[0-9][0-9][0-9][0-9][0-9][0-9].log"
        rotated_logs = glob.glob(rotated_pattern)
        stats['rotated_logs'] = len(rotated_logs)
        
        for log_file in rotated_logs:
            stats['total_size_mb'] += os.path.getsize(log_file) / (1024 * 1024)
        
        # Count compressed log files
        compressed_pattern = f"{rotated_pattern}.gz"
        compressed_logs = glob.glob(compressed_pattern)
        stats['compressed_logs'] = len(compressed_logs)
        
        for log_file in compressed_logs:
            stats['total_size_mb'] += os.path.getsize(log_file) / (1024 * 1024)
        
    except Exception as e:
        logger.error(f"Failed to get log statistics: {str(e)}")
    
    return stats

def should_rotate() -> bool:
    """
    Check if logs should be rotated based on the 6-hour schedule.
    
    Returns:
        bool: True if logs should be rotated
    """
    # For this implementation, we'll rotate every time the script runs
    # The cron job should be set to run every 6 hours
    return True

def main():
    """Main function to handle log rotation."""
    logger = setup_logging()
    
    logger.info("="*60)
    logger.info("Starting EC2 monitoring log rotation")
    logger.info("="*60)
    
    # Get initial statistics
    initial_stats = get_log_stats(logger)
    logger.info(f"Initial log statistics: {initial_stats}")
    
    # Check if rotation is needed
    if not should_rotate():
        logger.info("Log rotation not needed at this time")
        return
    
    # Rotate each log file
    rotation_success = True
    rotated_files = 0
    
    for log_file in LOG_FILES:
        if rotate_log_file(log_file, logger):
            rotated_files += 1
        else:
            rotation_success = False
    
    logger.info(f"Rotated {rotated_files} log files")
    
    # Clean up old log files
    removed_files = cleanup_old_logs(logger)
    
    # Get final statistics
    final_stats = get_log_stats(logger)
    logger.info(f"Final log statistics: {final_stats}")
    
    # Summary
    logger.info("="*60)
    logger.info("Log rotation summary:")
    logger.info(f"- Files rotated: {rotated_files}")
    logger.info(f"- Old files removed: {removed_files}")
    logger.info(f"- Compression enabled: {COMPRESS_AFTER_ROTATION}")
    logger.info(f"- Retention period: {RETENTION_DAYS} days")
    logger.info(f"- Total log size: {final_stats['total_size_mb']:.2f} MB")
    
    if rotation_success:
        logger.info("✅ Log rotation completed successfully")
    else:
        logger.error("❌ Some log rotation operations failed")
    
    logger.info("="*60)

if __name__ == "__main__":
    main()
