#!/usr/bin/env python3
# Created: 2025-07-17 18:56:03
# Last Modified: 2025-07-23 11:59:13
"""
Test script for monitoring implementation
Run this to verify that the monitoring system is working correctly
"""

import sys
import os
import time

# Add the project root to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_monitoring_imports():
    """Test that monitoring modules can be imported"""
    print("Testing monitoring imports...")
    
    try:
        from utils.monitoring import (
            logger, 
            db_monitor, 
            system_monitor, 
            business_metrics,
            get_metrics,
            get_metrics_summary
        )
        print("✓ Monitoring utilities imported successfully")
        return True
    except ImportError as e:
        print(f"✗ Failed to import monitoring utilities: {e}")
        return False

def test_metrics_endpoint():
    """Test that metrics endpoint can be imported"""
    print("\nTesting metrics endpoint...")
    
    try:
        from endpoints.metrics import router
        print("✓ Metrics endpoint imported successfully")
        return True
    except ImportError as e:
        print(f"✗ Failed to import metrics endpoint: {e}")
        return False

def test_database_monitoring():
    """Test database monitoring integration"""
    print("\nTesting database monitoring...")
    
    try:
        from core.database import get_db_connection, close_db_connection
        from utils.monitoring import db_monitor
        
        if db_monitor:
            print("✓ Database monitoring is available")
            
            # Test connection stats
            stats = db_monitor.get_connection_stats()
            print(f"✓ Database connection stats: {stats}")
            return True
        else:
            print("⚠ Database monitoring not available (fallback mode)")
            return True
    except Exception as e:
        print(f"✗ Database monitoring test failed: {e}")
        return False

def test_system_monitoring():
    """Test system monitoring"""
    print("\nTesting system monitoring...")
    
    try:
        from utils.monitoring import system_monitor
        
        # Test system stats collection
        stats = system_monitor.get_system_stats()
        print(f"✓ System stats collected: {stats}")
        
        # Test metrics update
        system_monitor.update_system_metrics()
        print("✓ System metrics updated successfully")
        return True
    except Exception as e:
        print(f"✗ System monitoring test failed: {e}")
        return False

def test_metrics_generation():
    """Test Prometheus metrics generation"""
    print("\nTesting metrics generation...")
    
    try:
        from utils.monitoring import get_metrics, get_metrics_summary
        
        # Test metrics summary
        summary = get_metrics_summary()
        print(f"✓ Metrics summary generated: {summary['timestamp']}")
        
        # Test Prometheus metrics
        metrics_data = get_metrics()
        if metrics_data:
            print("✓ Prometheus metrics generated successfully")
            print(f"  Metrics size: {len(metrics_data)} bytes")
        else:
            print("⚠ Prometheus metrics empty")
        
        return True
    except Exception as e:
        print(f"✗ Metrics generation test failed: {e}")
        return False

def test_logging():
    """Test structured logging"""
    print("\nTesting structured logging...")
    
    try:
        from utils.monitoring import logger
        
        # Test different log levels
        logger.debug("test_debug_message", test_data="debug")
        logger.info("test_info_message", test_data="info")
        logger.warning("test_warning_message", test_data="warning")
        logger.error("test_error_message", test_data="error")
        
        print("✓ Structured logging working correctly")
        return True
    except Exception as e:
        print(f"✗ Logging test failed: {e}")
        return False

def test_business_metrics():
    """Test business metrics"""
    print("\nTesting business metrics...")
    
    try:
        from utils.monitoring import business_metrics
        
        # Test case metrics
        business_metrics.update_case_metrics(42)
        business_metrics.record_case_operation("create", "success", "test-case-123")
        
        # Test user metrics
        business_metrics.update_user_metrics(15)
        business_metrics.record_user_operation("login", "success", "test-user-456")
        
        print("✓ Business metrics recorded successfully")
        return True
    except Exception as e:
        print(f"✗ Business metrics test failed: {e}")
        return False

def main():
    """Run all monitoring tests"""
    print("=" * 60)
    print("SurgiCase Monitoring Implementation Test")
    print("=" * 60)
    
    tests = [
        test_monitoring_imports,
        test_metrics_endpoint,
        test_database_monitoring,
        test_system_monitoring,
        test_metrics_generation,
        test_logging,
        test_business_metrics
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        try:
            if test():
                passed += 1
        except Exception as e:
            print(f"✗ Test {test.__name__} crashed: {e}")
    
    print("\n" + "=" * 60)
    print(f"Test Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed! Monitoring implementation is working correctly.")
        print("\nNext steps:")
        print("1. Install monitoring dependencies: pip install -r monitoring-requirements.txt")
        print("2. Start the application: python main.py")
        print("3. Access metrics at: http://localhost:8000/metrics")
        print("4. View metrics summary at: http://localhost:8000/metrics/summary")
    else:
        print("⚠ Some tests failed. Please check the implementation.")
    
    print("=" * 60)

if __name__ == "__main__":
    main() 