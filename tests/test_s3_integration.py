# Created: 2025-07-17 10:50:00
# Last Modified: 2025-07-17 11:23:07

# test_s3_integration.py
"""
Test script to verify S3 integration with AWS Secrets Manager
Run this script to test the S3 configuration and upload functionality
"""

import os
import sys
import tempfile
from datetime import datetime

# Add the project root to the path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.s3_storage import get_s3_config, upload_file_to_s3, generate_s3_key
from utils.s3_monitoring import S3Monitor

def test_s3_config():
    """Test S3 configuration retrieval from Secrets Manager"""
    print("Testing S3 configuration retrieval...")
    
    try:
        config = get_s3_config()
        print(f"✅ S3 Configuration retrieved successfully:")
        print(f"   Bucket: {config.get('bucket_name')}")
        print(f"   Region: {config.get('region')}")
        print(f"   Folder Prefix: {config.get('folder_prefix')}")
        print(f"   Encryption: {config.get('encryption')}")
        return True
    except Exception as e:
        print(f"❌ Failed to retrieve S3 configuration: {str(e)}")
        return False

def test_s3_upload():
    """Test S3 file upload functionality"""
    print("\nTesting S3 file upload...")
    
    try:
        # Create a test file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            test_content = f"Test file created at {datetime.now().isoformat()}\nThis is a test file for S3 integration."
            f.write(test_content)
            temp_file_path = f.name
        
        # Generate S3 key
        s3_key = generate_s3_key('test', 'test_file.txt')
        print(f"Generated S3 key: {s3_key}")
        
        # Upload to S3
        result = upload_file_to_s3(
            file_path=temp_file_path,
            s3_key=s3_key,
            content_type='text/plain',
            metadata={
                'test_type': 'integration_test',
                'created_by': 'test_script',
                'timestamp': datetime.now().isoformat()
            }
        )
        
        # Record monitoring metrics
        import os
        file_size = os.path.getsize(temp_file_path) if os.path.exists(temp_file_path) else 0
        S3Monitor.record_upload_operation(
            success=result['success'],
            file_type='test',
            file_size=file_size,
            duration=0  # Could calculate actual duration if needed
        )
        
        # Clean up temp file
        os.unlink(temp_file_path)
        
        if result['success']:
            print(f"✅ File uploaded successfully to S3:")
            print(f"   S3 URL: {result['s3_url']}")
            print(f"   S3 Key: {result['s3_key']}")
            return True
        else:
            print(f"❌ File upload failed: {result['message']}")
            return False
            
    except Exception as e:
        print(f"❌ Test failed with exception: {str(e)}")
        return False

def main():
    """Run all S3 integration tests"""
    print("=" * 60)
    print("S3 INTEGRATION TEST")
    print("=" * 60)
    
    # Test configuration
    config_success = test_s3_config()
    
    # Test upload
    upload_success = test_s3_upload()
    
    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    
    if config_success and upload_success:
        print("🎉 All tests passed! S3 integration is working correctly.")
        print("\nNext steps:")
        print("1. Create the AWS Secrets Manager secret 'surgicase/s3-user-reports'")
        print("2. Test the report endpoints to verify S3 storage")
        print("3. Monitor S3 uploads in the AWS console")
    else:
        print("❌ Some tests failed. Check the output above for details.")
        
        if not config_success:
            print("\nConfiguration issues:")
            print("- Ensure AWS credentials are configured")
            print("- Verify the secret 'surgicase/s3-config' exists in AWS Secrets Manager")
            print("- Check AWS region configuration")
            
        if not upload_success:
            print("\nUpload issues:")
            print("- Verify S3 bucket permissions")
            print("- Check IAM roles or access keys")
            print("- Ensure bucket exists and is accessible")

if __name__ == "__main__":
    main() 