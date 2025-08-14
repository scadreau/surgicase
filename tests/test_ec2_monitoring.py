# Created: 2025-08-14 15:56:21
# Last Modified: 2025-08-14 15:58:57
# Author: Scott Cadreau

"""
Test script for EC2 monitoring functionality

This script tests the EC2 monitoring components to ensure they work correctly
before setting up the automated monitoring.
"""

import sys
import os
import logging

# Add the parent directory to the path to import project modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_imports():
    """Test that all required modules can be imported."""
    print("Testing imports...")
    
    try:
        import boto3
        print("✅ boto3 imported successfully")
    except ImportError as e:
        print(f"❌ Failed to import boto3: {e}")
        return False
    
    try:
        import pymysql
        print("✅ pymysql imported successfully")
    except ImportError as e:
        print(f"❌ Failed to import pymysql: {e}")
        return False
    
    try:
        import psutil
        print("✅ psutil imported successfully")
    except ImportError as e:
        print(f"❌ Failed to import psutil: {e}")
        return False
    
    try:
        from core.database import get_db_connection, close_db_connection
        print("✅ Database module imported successfully")
    except ImportError as e:
        print(f"❌ Failed to import database module: {e}")
        return False
    
    return True

def test_aws_credentials():
    """Test AWS credentials and connectivity."""
    print("\nTesting AWS credentials...")
    
    try:
        import boto3
        
        # Test EC2 client
        ec2 = boto3.client('ec2', region_name='us-east-1')
        response = ec2.describe_regions(RegionNames=['us-east-1'])
        print("✅ AWS EC2 credentials working")
        
        # Test CloudWatch client  
        cloudwatch = boto3.client('cloudwatch', region_name='us-east-1')
        # Try to list metrics (this will fail gracefully if no permissions)
        print("✅ AWS CloudWatch client initialized")
        
        return True
        
    except Exception as e:
        print(f"❌ AWS credentials test failed: {e}")
        print("Please run: aws configure")
        return False

def test_database_connection():
    """Test database connectivity."""
    print("\nTesting database connection...")
    
    try:
        from core.database import get_db_connection, close_db_connection
        
        connection = get_db_connection()
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            result = cursor.fetchone()
            if result:
                print("✅ Database connection successful")
                return True
            else:
                print("❌ Database query failed")
                return False
                
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        return False
    finally:
        if 'connection' in locals():
            close_db_connection(connection)

def test_monitoring_script():
    """Test the monitoring script functionality."""
    print("\nTesting monitoring script...")
    
    try:
        from ec2_monitoring_script import EC2Monitor
        
        # Initialize monitor (this will test AWS connectivity)
        monitor = EC2Monitor("i-099fb57644b0c33ba", "us-east-1")
        print("✅ EC2Monitor initialized successfully")
        
        # Test table creation
        if monitor.create_monitoring_table():
            print("✅ Monitoring table created/verified")
        else:
            print("❌ Failed to create monitoring table")
            return False
        
        # Test instance info retrieval
        info = monitor.get_instance_info()
        if info:
            print(f"✅ Instance info retrieved: {info.get('instance_type', 'Unknown')} in {info.get('state', 'Unknown')} state")
        else:
            print("⚠️  Could not retrieve instance info (check instance ID and permissions)")
        
        # Test metric collection (this might return None values if metrics aren't available yet)
        print("Testing metric collection...")
        cpu = monitor.get_cpu_utilization()
        memory = monitor.get_memory_utilization()
        
        if cpu is not None:
            print(f"✅ CPU metric retrieved: {cpu}%")
        else:
            print("⚠️  CPU metric not available (this is normal for new instances)")
        
        if memory is not None:
            print(f"✅ Memory metric retrieved: {memory}%")
        else:
            print("⚠️  Memory metric not available (requires CloudWatch agent)")
        
        print("✅ Monitoring script tests completed")
        return True
        
    except Exception as e:
        print(f"❌ Monitoring script test failed: {e}")
        return False

def run_sample_monitoring():
    """Run a sample monitoring cycle."""
    print("\nRunning sample monitoring cycle...")
    
    try:
        from ec2_monitoring_script import EC2Monitor
        
        monitor = EC2Monitor("i-099fb57644b0c33ba", "us-east-1")
        
        # Run one monitoring cycle
        if monitor.run_monitoring_cycle():
            print("✅ Sample monitoring cycle completed successfully")
            
            # Show the latest data
            print("\nLatest monitoring data:")
            from ec2_monitoring_script import print_latest_metrics
            print_latest_metrics()
            
            return True
        else:
            print("❌ Sample monitoring cycle failed")
            return False
            
    except Exception as e:
        print(f"❌ Sample monitoring failed: {e}")
        return False

def main():
    """Main test function."""
    print("="*60)
    print("EC2 MONITORING TEST SUITE")
    print("="*60)
    
    tests = [
        ("Import Tests", test_imports),
        ("AWS Credentials", test_aws_credentials),
        ("Database Connection", test_database_connection),
        ("Monitoring Script", test_monitoring_script),
        ("Sample Monitoring", run_sample_monitoring)
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        print(f"\n{'-'*40}")
        print(f"Running: {test_name}")
        print(f"{'-'*40}")
        
        try:
            if test_func():
                passed += 1
                print(f"✅ {test_name} PASSED")
            else:
                print(f"❌ {test_name} FAILED")
        except Exception as e:
            print(f"❌ {test_name} ERROR: {e}")
    
    print("\n" + "="*60)
    print(f"TEST RESULTS: {passed}/{total} tests passed")
    print("="*60)
    
    if passed == total:
        print("\n🎉 All tests passed! Your monitoring system is ready to use.")
        print("\n📝 Next steps:")
        print("1. Run: chmod +x tests/setup_monitoring_cron.sh")
        print("2. Run: ./tests/setup_monitoring_cron.sh")
        print("3. Monitor logs: tail -f tests/ec2_monitoring_cron.log")
    else:
        print(f"\n⚠️  {total - passed} test(s) failed. Please fix the issues before proceeding.")
        
        if not test_imports():
            print("\n💡 To install missing dependencies:")
            print("pip install boto3 pymysql psutil --break-system-packages")

if __name__ == "__main__":
    main()
