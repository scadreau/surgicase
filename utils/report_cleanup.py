# Created: 2025-07-17 16:42:31
# Last Modified: 2025-07-23 11:59:23

# utils/report_cleanup.py
import os
import glob
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

def cleanup_old_reports(reports_dir: str = "reports", days_to_keep: int = 7):
    """
    Clean up report files older than specified days.
    
    Args:
        reports_dir: Directory containing report files
        days_to_keep: Number of days to keep files (default: 7)
    """
    try:
        if not os.path.exists(reports_dir):
            logger.info(f"Reports directory {reports_dir} does not exist, skipping cleanup")
            return
        
        # Calculate cutoff date
        cutoff_date = datetime.now() - timedelta(days=days_to_keep)
        
        # Find all PDF files in the reports directory
        pdf_pattern = os.path.join(reports_dir, "*.pdf")
        pdf_files = glob.glob(pdf_pattern)
        
        deleted_count = 0
        for file_path in pdf_files:
            try:
                # Get file modification time
                file_mtime = datetime.fromtimestamp(os.path.getmtime(file_path))
                
                # Delete if file is older than cutoff date
                if file_mtime < cutoff_date:
                    os.remove(file_path)
                    deleted_count += 1
                    logger.info(f"Deleted old report file: {file_path}")
                    
            except Exception as e:
                logger.error(f"Error processing file {file_path}: {str(e)}")
        
        logger.info(f"Cleanup completed: {deleted_count} old report files deleted")
        
    except Exception as e:
        logger.error(f"Error during report cleanup: {str(e)}")

def get_reports_directory_size(reports_dir: str = "reports") -> int:
    """
    Get the total size of the reports directory in bytes.
    
    Args:
        reports_dir: Directory containing report files
        
    Returns:
        Total size in bytes
    """
    try:
        if not os.path.exists(reports_dir):
            return 0
        
        total_size = 0
        for dirpath, dirnames, filenames in os.walk(reports_dir):
            for filename in filenames:
                file_path = os.path.join(dirpath, filename)
                if os.path.exists(file_path):
                    total_size += os.path.getsize(file_path)
        
        return total_size
        
    except Exception as e:
        logger.error(f"Error calculating reports directory size: {str(e)}")
        return 0 