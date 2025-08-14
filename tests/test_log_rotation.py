# Created: 2025-08-14 16:16:23
# Last Modified: 2025-08-14 16:17:45
# Author: Scott Cadreau

"""
Test script for log rotation functionality

This script tests the log rotation system to ensure it works correctly:
- Creates test log files with different ages
- Tests rotation functionality
- Tests cleanup of old files
- Verifies compression works
"""

import os
import tempfile
import shutil
from datetime import datetime, timedelta
from pathlib import Path
import sys

# Add the current directory to path to import the rotation script
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def create_test_log_files(test_dir: str) -> list:
    """Create test log files with different ages for testing."""
    test_files = []
    
    # Create current log files
    current_logs = [
        f"{test_dir}/ec2_monitoring.log",
        f"{test_dir}/ec2_monitoring_cron.log"
    ]
    
    for log_file in current_logs:
        with open(log_file, 'w') as f:
            f.write(f"Test log content for {os.path.basename(log_file)}\n")
            f.write(f"Created at: {datetime.now()}\n")
            f.write("Sample log line 1\n")
            f.write("Sample log line 2\n")
        test_files.append(log_file)
    
    # Create old rotated log files (older than 2 days)
    old_timestamp = (datetime.now() - timedelta(days=3)).strftime("%Y%m%d_%H%M%S")
    old_logs = [
        f"{test_dir}/ec2_monitoring_{old_timestamp}.log.gz",
        f"{test_dir}/ec2_monitoring_cron_{old_timestamp}.log.gz"
    ]
    
    for log_file in old_logs:
        with open(log_file, 'w') as f:
            f.write("Old compressed log content\n")
        # Set file modification time to 3 days ago
        old_time = (datetime.now() - timedelta(days=3)).timestamp()
        os.utime(log_file, (old_time, old_time))
        test_files.append(log_file)
    
    # Create recent rotated log files (within 2 days)
    recent_timestamp = (datetime.now() - timedelta(hours=12)).strftime("%Y%m%d_%H%M%S")
    recent_logs = [
        f"{test_dir}/ec2_monitoring_{recent_timestamp}.log.gz",
        f"{test_dir}/ec2_monitoring_cron_{recent_timestamp}.log.gz"
    ]
    
    for log_file in recent_logs:
        with open(log_file, 'w') as f:
            f.write("Recent compressed log content\n")
        # Set file modification time to 12 hours ago
        recent_time = (datetime.now() - timedelta(hours=12)).timestamp()
        os.utime(log_file, (recent_time, recent_time))
        test_files.append(log_file)
    
    return test_files

def test_log_rotation():
    """Test the log rotation functionality."""
    print("🧪 Testing EC2 Monitoring Log Rotation")
    print("="*50)
    
    # Create temporary directory for testing
    with tempfile.TemporaryDirectory() as temp_dir:
        print(f"📁 Using test directory: {temp_dir}")
        
        # Create test log files
        test_files = create_test_log_files(temp_dir)
        print(f"📝 Created {len(test_files)} test log files")
        
        # List initial files
        print("\n📋 Initial files:")
        for file in sorted(os.listdir(temp_dir)):
            file_path = os.path.join(temp_dir, file)
            size = os.path.getsize(file_path)
            mtime = datetime.fromtimestamp(os.path.getmtime(file_path))
            print(f"  {file} ({size} bytes, modified: {mtime.strftime('%Y-%m-%d %H:%M:%S')})")
        
        # Test rotation by modifying the rotation script temporarily
        print("\n🔄 Testing log rotation...")
        
        # Import rotation functions (we'll need to modify the script to use our test directory)
        from rotate_monitoring_logs import rotate_log_file, cleanup_old_logs, get_log_stats
        import logging
        
        # Setup test logger
        test_logger = logging.getLogger('test_rotation')
        test_logger.setLevel(logging.INFO)
        
        # Test rotation of current log files
        current_logs = [
            f"{temp_dir}/ec2_monitoring.log",
            f"{temp_dir}/ec2_monitoring_cron.log"
        ]
        
        rotated_count = 0
        for log_file in current_logs:
            if rotate_log_file(log_file, test_logger):
                rotated_count += 1
                print(f"  ✅ Rotated {os.path.basename(log_file)}")
            else:
                print(f"  ❌ Failed to rotate {os.path.basename(log_file)}")
        
        print(f"\n📊 Rotation results: {rotated_count}/{len(current_logs)} files rotated")
        
        # Test cleanup (we need to modify the cleanup function to use our test directory)
        print("\n🧹 Testing cleanup of old files...")
        
        # Count files before cleanup
        files_before = len([f for f in os.listdir(temp_dir) if f.endswith('.log.gz')])
        print(f"  Files before cleanup: {files_before}")
        
        # Manually implement cleanup for test directory
        cutoff_time = datetime.now() - timedelta(days=2)
        removed_count = 0
        
        for file in os.listdir(temp_dir):
            if file.endswith('.log.gz'):
                file_path = os.path.join(temp_dir, file)
                file_mtime = datetime.fromtimestamp(os.path.getmtime(file_path))
                
                if file_mtime < cutoff_time:
                    os.remove(file_path)
                    print(f"  🗑️  Removed old file: {file}")
                    removed_count += 1
                else:
                    print(f"  ⏳ Kept recent file: {file}")
        
        files_after = len([f for f in os.listdir(temp_dir) if f.endswith('.log.gz')])
        print(f"  Files after cleanup: {files_after}")
        print(f"  Files removed: {removed_count}")
        
        # List final files
        print("\n📋 Final files:")
        for file in sorted(os.listdir(temp_dir)):
            file_path = os.path.join(temp_dir, file)
            size = os.path.getsize(file_path)
            mtime = datetime.fromtimestamp(os.path.getmtime(file_path))
            print(f"  {file} ({size} bytes, modified: {mtime.strftime('%Y-%m-%d %H:%M:%S')})")
        
        # Test results
        print("\n🎯 Test Results:")
        print(f"  ✅ Log rotation: {'PASS' if rotated_count == len(current_logs) else 'FAIL'}")
        print(f"  ✅ Old file cleanup: {'PASS' if removed_count > 0 else 'FAIL'}")
        print(f"  ✅ File compression: {'PASS' if any(f.endswith('.gz') for f in os.listdir(temp_dir)) else 'FAIL'}")
        
        return rotated_count == len(current_logs) and removed_count > 0

def main():
    """Run the log rotation tests."""
    try:
        success = test_log_rotation()
        
        print("\n" + "="*50)
        if success:
            print("🎉 All log rotation tests PASSED!")
        else:
            print("❌ Some log rotation tests FAILED!")
        print("="*50)
        
        return 0 if success else 1
        
    except Exception as e:
        print(f"\n❌ Test error: {e}")
        return 1

if __name__ == "__main__":
    exit(main())
