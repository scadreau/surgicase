# Created: 2025-07-17 11:25:00
# Last Modified: 2025-07-29 01:40:04

# utils/s3_monitoring.py
"""
S3 Monitoring Integration for SurgiCase
Integrates S3 operations with existing Prometheus/Grafana monitoring stack
"""

import time
from typing import Dict, Any
from utils.monitoring import record_utility_operation

def record_s3_upload_operation(success: bool, file_type: str, file_size: int = 0, duration: float = 0):
    """Record S3 upload operation metrics"""
    status = "success" if success else "failure"
    
    # Record business metrics using utility operations
    record_utility_operation("s3_upload", status)
    record_utility_operation(f"s3_upload_{file_type}", status)
    
    # Record file size if available
    if file_size > 0:
        record_utility_operation("s3_upload_size", f"{file_size}")
    
    # Record duration if available
    if duration > 0:
        record_utility_operation("s3_upload_duration", f"{duration:.3f}")

def record_s3_delete_operation(success: bool, file_type: str = "unknown"):
    """Record S3 delete operation metrics"""
    status = "success" if success else "failure"
    record_utility_operation("s3_delete", status)
    record_utility_operation(f"s3_delete_{file_type}", status)

def record_s3_config_error(operation: str, error_type: str):
    """Record S3 configuration errors"""
    record_utility_operation("s3_config_error", f"{operation}_{error_type}")

# Backward compatibility class for existing code
class S3Monitor:
    """Compatibility wrapper for old S3Monitor usage"""
    @staticmethod
    def record_upload_operation(success: bool, file_type: str, file_size: int = 0, duration: float = 0):
        return record_s3_upload_operation(success, file_type, file_size, duration)
    
    @staticmethod
    def record_delete_operation(success: bool, file_type: str = "unknown"):
        return record_s3_delete_operation(success, file_type)
    
    @staticmethod
    def record_config_error(operation: str, error_type: str):
        return record_s3_config_error(operation, error_type)

def monitor_s3_operation(operation_type: str = "upload"):
    """Decorator to monitor S3 operations"""
    def decorator(func):
        def wrapper(*args, **kwargs):
            start_time = time.time()
            success = False
            file_type = "unknown"
            file_size = 0
            
            try:
                # Extract file type from arguments if possible
                if 'file_type' in kwargs:
                    file_type = kwargs['file_type']
                elif 's3_key' in kwargs:
                    s3_key = kwargs['s3_key']
                    if '/' in s3_key:
                        file_type = s3_key.split('/')[-2] if len(s3_key.split('/')) > 1 else "unknown"
                
                # Extract file size if available
                if 'file_path' in kwargs:
                    import os
                    try:
                        file_size = os.path.getsize(kwargs['file_path'])
                    except:
                        pass
                
                # Execute the operation
                result = func(*args, **kwargs)
                
                # Determine success
                if isinstance(result, dict):
                    success = result.get('success', False)
                else:
                    success = True
                
                return result
                
            except Exception as e:
                success = False
                raise
            finally:
                # Record metrics
                duration = time.time() - start_time
                
                if operation_type == "upload":
                    record_s3_upload_operation(success, file_type, file_size, duration)
                elif operation_type == "delete":
                    record_s3_delete_operation(success, file_type)
        
        return wrapper
    return decorator 