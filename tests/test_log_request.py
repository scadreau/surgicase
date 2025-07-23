# Created: 2025-07-15 21:27:56
# Last Modified: 2025-07-23 11:59:14

"""
Test script for the log_request endpoint
Tests various scenarios including valid requests, edge cases, and error conditions
"""

import requests
import json
import time
from datetime import datetime
import uuid

# Configuration
BASE_URL = "http://localhost:8000"  # Adjust this to match your server URL
LOG_ENDPOINT = f"{BASE_URL}/log_request"

# Add the parent directory to the path for imports
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_valid_log_request():
    """Test a valid log request with all required fields and a full JSON payload"""
    print("Testing valid log request...")
    
    # Create a comprehensive JSON payload for testing
    test_payload = {
        "user_id": "test_user_123",
        "case_id": "case_456",
        "action": "create_case",
        "data": {
            "patient": {
                "first": "John",
                "last": "Doe",
                "ins_provider": "Blue Cross Blue Shield"
            },
            "surgeon_id": "surgeon_789",
            "facility_id": "facility_101",
            "procedure_codes": ["12345", "67890"],
            "files": {
                "demo_file": "demo_2024_01_15.pdf",
                "note_file": "surgical_notes.docx",
                "misc_file": "additional_info.pdf"
            },
            "metadata": {
                "created_at": datetime.now().isoformat(),
                "version": "1.0",
                "tags": ["cardiac", "emergency", "high_priority"]
            }
        }
    }
    
    # Create query parameters
    query_params = {
        "user_id": "test_user_123",
        "status": "active",
        "limit": "50",
        "offset": "0",
        "sort_by": "created_date",
        "sort_order": "desc"
    }
    
    # Create response payload
    response_payload = {
        "success": True,
        "data": {
            "case_id": "case_456",
            "status": "created",
            "created_at": datetime.now().isoformat(),
            "message": "Case created successfully"
        },
        "metadata": {
            "total_records": 1,
            "processing_time_ms": 245
        }
    }
    
    log_data = {
        "timestamp": datetime.now().isoformat(),
        "user_id": "test_user_123",
        "endpoint": "/api/case/create",
        "method": "POST",
        "request_payload": json.dumps(test_payload, indent=2),
        "query_params": json.dumps(query_params, indent=2),
        "response_status": 201,
        "response_payload": json.dumps(response_payload, indent=2),
        "execution_time_ms": 245,
        "error_message": None,
        "client_ip": "192.168.1.100"
    }
    
    try:
        response = requests.post(LOG_ENDPOINT, json=log_data)
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.json()}")
        return response.status_code == 200
    except Exception as e:
        print(f"Error: {e}")
        return False

def test_log_request_with_error():
    """Test logging a request that resulted in an error"""
    print("\nTesting log request with error...")
    
    error_payload = {
        "user_id": "test_user_456",
        "case_id": "invalid_case",
        "invalid_field": "this_should_fail"
    }
    
    log_data = {
        "timestamp": datetime.now().isoformat(),
        "user_id": "test_user_456",
        "endpoint": "/api/case/update",
        "method": "PUT",
        "request_payload": json.dumps(error_payload, indent=2),
        "query_params": None,
        "response_status": 400,
        "response_payload": json.dumps({
            "error": "Validation failed",
            "details": "Invalid field 'invalid_field' not allowed"
        }, indent=2),
        "execution_time_ms": 89,
        "error_message": "ValidationError: Invalid field 'invalid_field' not allowed",
        "client_ip": "10.0.0.50"
    }
    
    try:
        response = requests.post(LOG_ENDPOINT, json=log_data)
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.json()}")
        return response.status_code == 200
    except Exception as e:
        print(f"Error: {e}")
        return False

def test_log_request_minimal_fields():
    """Test logging with minimal required fields"""
    print("\nTesting log request with minimal fields...")
    
    log_data = {
        "timestamp": datetime.now().isoformat(),
        "endpoint": "/api/health",
        "method": "GET",
        "response_status": 200,
        "execution_time_ms": 12
    }
    
    try:
        response = requests.post(LOG_ENDPOINT, json=log_data)
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.json()}")
        return response.status_code == 200
    except Exception as e:
        print(f"Error: {e}")
        return False

def test_log_request_large_payload():
    """Test logging with a very large JSON payload"""
    print("\nTesting log request with large payload...")
    
    # Create a large payload with many records
    large_payload = {
        "user_id": "admin_user",
        "action": "bulk_import",
        "records": []
    }
    
    # Generate 1000 sample records
    for i in range(1000):
        record = {
            "id": f"record_{i}",
            "name": f"Patient {i}",
            "data": {
                "medical_history": f"History for patient {i}",
                "diagnosis": f"Diagnosis {i}",
                "treatment": f"Treatment plan {i}",
                "medications": [f"med_{j}" for j in range(5)],
                "notes": f"Detailed notes for patient {i} with extensive medical information"
            },
            "metadata": {
                "created": datetime.now().isoformat(),
                "updated": datetime.now().isoformat(),
                "tags": [f"tag_{j}" for j in range(3)]
            }
        }
        large_payload["records"].append(record)
    
    log_data = {
        "timestamp": datetime.now().isoformat(),
        "user_id": "admin_user",
        "endpoint": "/api/bulk/import",
        "method": "POST",
        "request_payload": json.dumps(large_payload, indent=2),
        "query_params": None,
        "response_status": 200,
        "response_payload": json.dumps({
            "success": True,
            "imported_count": 1000,
            "failed_count": 0,
            "processing_time_ms": 5000
        }, indent=2),
        "execution_time_ms": 5000,
        "error_message": None,
        "client_ip": "172.16.0.100"
    }
    
    try:
        response = requests.post(LOG_ENDPOINT, json=log_data)
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.json()}")
        return response.status_code == 200
    except Exception as e:
        print(f"Error: {e}")
        return False

def test_log_request_special_characters():
    """Test logging with special characters and unicode in payloads"""
    print("\nTesting log request with special characters...")
    
    special_payload = {
        "user_id": "user_with_special_chars",
        "message": "Special characters: !@#$%^&*()_+-=[]{}|;':\",./<>?",
        "unicode_text": "Unicode: 你好世界 🌍 🚀 💻",
        "sql_injection_attempt": "'; DROP TABLE users; --",
        "xss_attempt": "<script>alert('xss')</script>",
        "json_breaking": '{"key": "value with "quotes" inside"}',
        "newlines": "Line 1\nLine 2\r\nLine 3",
        "tabs": "Tab\tseparated\tvalues"
    }
    
    log_data = {
        "timestamp": datetime.now().isoformat(),
        "user_id": "user_with_special_chars",
        "endpoint": "/api/test/special_chars",
        "method": "POST",
        "request_payload": json.dumps(special_payload, indent=2, ensure_ascii=False),
        "query_params": json.dumps({
            "search": "test & special chars",
            "filter": "status='active'"
        }, indent=2),
        "response_status": 200,
        "response_payload": json.dumps({
            "success": True,
            "message": "Special characters handled correctly",
            "sanitized": True
        }, indent=2),
        "execution_time_ms": 156,
        "error_message": None,
        "client_ip": "127.0.0.1"
    }
    
    try:
        response = requests.post(LOG_ENDPOINT, json=log_data)
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.json()}")
        return response.status_code == 200
    except Exception as e:
        print(f"Error: {e}")
        return False

def test_log_request_performance():
    """Test logging multiple requests to check performance"""
    print("\nTesting log request performance (10 requests)...")
    
    start_time = time.time()
    success_count = 0
    
    for i in range(10):
        log_data = {
            "timestamp": datetime.now().isoformat(),
            "user_id": f"perf_test_user_{i}",
            "endpoint": f"/api/test/performance/{i}",
            "method": "GET",
            "request_payload": json.dumps({"test_id": i, "timestamp": datetime.now().isoformat()}),
            "query_params": None,
            "response_status": 200,
            "response_payload": json.dumps({"success": True, "test_id": i}),
            "execution_time_ms": 50 + i,
            "error_message": None,
            "client_ip": f"192.168.1.{i + 1}"
        }
        
        try:
            response = requests.post(LOG_ENDPOINT, json=log_data)
            if response.status_code == 200:
                success_count += 1
        except Exception as e:
            print(f"Request {i} failed: {e}")
    
    end_time = time.time()
    total_time = end_time - start_time
    
    print(f"Performance Test Results:")
    print(f"Total requests: 10")
    print(f"Successful requests: {success_count}")
    print(f"Total time: {total_time:.2f} seconds")
    print(f"Average time per request: {total_time/10:.2f} seconds")
    
    return success_count == 10

def test_invalid_log_request():
    """Test logging with invalid/missing required fields"""
    print("\nTesting invalid log request...")
    
    # Missing required fields
    invalid_log_data = {
        "timestamp": datetime.now().isoformat(),
        "user_id": "test_user",
        # Missing endpoint, method, response_status, execution_time_ms
    }
    
    try:
        response = requests.post(LOG_ENDPOINT, json=invalid_log_data)
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.json()}")
        return response.status_code == 422  # Validation error expected
    except Exception as e:
        print(f"Error: {e}")
        return False

def main():
    """Run all tests"""
    print("=" * 60)
    print("LOG REQUEST ENDPOINT TEST SUITE")
    print("=" * 60)
    
    tests = [
        ("Valid Log Request", test_valid_log_request),
        ("Log Request with Error", test_log_request_with_error),
        ("Minimal Fields Log Request", test_log_request_minimal_fields),
        ("Large Payload Log Request", test_log_request_large_payload),
        ("Special Characters Log Request", test_log_request_special_characters),
        ("Performance Test", test_log_request_performance),
        ("Invalid Log Request", test_invalid_log_request)
    ]
    
    results = []
    
    for test_name, test_func in tests:
        print(f"\n{'='*20} {test_name} {'='*20}")
        try:
            result = test_func()
            results.append((test_name, result))
            status = "PASS" if result else "FAIL"
            print(f"{test_name}: {status}")
        except Exception as e:
            print(f"{test_name}: ERROR - {e}")
            results.append((test_name, False))
    
    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "PASS" if result else "FAIL"
        print(f"{test_name}: {status}")
    
    print(f"\nOverall: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed!")
    else:
        print("❌ Some tests failed. Check the output above for details.")

if __name__ == "__main__":
    main() 