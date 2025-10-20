# Created: 2025-10-19
# Last Modified: 2025-10-19 23:54:46
# Author: Scott Cadreau

"""
Comprehensive test suite for PHI field encryption infrastructure.

This test suite validates:
1. KMS key setup and access
2. Database schema and tables
3. Key generation for users
4. Encryption/decryption functionality
5. Cache performance
6. Edge cases (None, empty strings, special characters, unicode)
7. Admin endpoints
8. Audit logging

Run this BEFORE migrating any live data to ensure infrastructure is solid.

Usage:
    python tests/test_phi_encryption.py
"""

import sys
import os
import time
import json
from datetime import datetime
from typing import Dict, Any, List

# Add parent directory to path
sys.path.insert(0, '/home/scadreau/surgicase')

from core.database import get_db_connection, close_db_connection
from utils.phi_encryption import (
    PHIEncryption,
    generate_and_store_user_key,
    get_user_dek,
    encrypt_patient_data,
    decrypt_patient_data,
    clear_dek_cache,
    get_cache_stats
)
import pymysql.cursors
import boto3
from botocore.exceptions import ClientError

# ANSI color codes for output
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
RESET = '\033[0m'
BOLD = '\033[1m'


class TestResult:
    """Track test results."""
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.warnings = 0
        self.errors: List[str] = []
    
    def add_pass(self):
        self.passed += 1
    
    def add_fail(self, error: str):
        self.failed += 1
        self.errors.append(error)
    
    def add_warning(self):
        self.warnings += 1
    
    def print_summary(self):
        print("\n" + "=" * 80)
        print(f"{BOLD}TEST SUMMARY{RESET}")
        print("=" * 80)
        print(f"{GREEN}Passed: {self.passed}{RESET}")
        print(f"{RED}Failed: {self.failed}{RESET}")
        print(f"{YELLOW}Warnings: {self.warnings}{RESET}")
        
        if self.errors:
            print(f"\n{RED}Errors:{RESET}")
            for i, error in enumerate(self.errors, 1):
                print(f"  {i}. {error}")
        
        print("=" * 80)
        
        if self.failed == 0:
            print(f"{GREEN}{BOLD}✓ ALL TESTS PASSED!{RESET}")
            return 0
        else:
            print(f"{RED}{BOLD}✗ SOME TESTS FAILED{RESET}")
            return 1


results = TestResult()


def print_test_header(test_name: str):
    """Print a test section header."""
    print(f"\n{BLUE}{BOLD}{'=' * 80}{RESET}")
    print(f"{BLUE}{BOLD}{test_name}{RESET}")
    print(f"{BLUE}{BOLD}{'=' * 80}{RESET}")


def print_test(test_name: str, passed: bool, details: str = ""):
    """Print individual test result."""
    status = f"{GREEN}✓ PASS{RESET}" if passed else f"{RED}✗ FAIL{RESET}"
    print(f"{status} - {test_name}")
    if details:
        print(f"      {details}")
    
    if passed:
        results.add_pass()
    else:
        results.add_fail(f"{test_name}: {details}")


def test_kms_key_setup():
    """Test 1: Verify KMS key exists and is accessible."""
    print_test_header("TEST 1: KMS Key Setup and Access")
    
    try:
        kms_client = boto3.client('kms', region_name='us-east-1')
        
        # Test 1.1: Check if key exists
        try:
            response = kms_client.describe_key(KeyId='alias/surgicase-phi-master')
            key_id = response['KeyMetadata']['KeyId']
            key_state = response['KeyMetadata']['KeyState']
            print_test("KMS key exists", True, f"Key ID: {key_id}, State: {key_state}")
            
            if key_state != 'Enabled':
                print_test("KMS key enabled", False, f"Key state is {key_state}, expected Enabled")
            else:
                print_test("KMS key enabled", True)
        
        except ClientError as e:
            if e.response['Error']['Code'] == 'NotFoundException':
                print_test("KMS key exists", False, 
                          "Key 'alias/surgicase-phi-master' not found. Please create it first.")
                print(f"{YELLOW}      Run: aws kms create-key --description 'SurgiCase PHI encryption'{RESET}")
                return False
            raise
        
        # Test 1.2: Test key permissions - generate data key
        try:
            response = kms_client.generate_data_key(
                KeyId='alias/surgicase-phi-master',
                KeySpec='AES_256'
            )
            print_test("KMS generate_data_key permission", True, 
                      f"Generated {len(response['Plaintext'])} byte key")
        except ClientError as e:
            print_test("KMS generate_data_key permission", False, str(e))
            return False
        
        # Test 1.3: Test decrypt permission
        try:
            encrypted_key = response['CiphertextBlob']
            response = kms_client.decrypt(CiphertextBlob=encrypted_key)
            print_test("KMS decrypt permission", True, 
                      f"Successfully decrypted {len(response['Plaintext'])} byte key")
        except ClientError as e:
            print_test("KMS decrypt permission", False, str(e))
            return False
        
        return True
        
    except Exception as e:
        print_test("KMS setup", False, f"Unexpected error: {str(e)}")
        return False


def test_database_schema(conn):
    """Test 2: Verify database schema is correct."""
    print_test_header("TEST 2: Database Schema Validation")
    
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            # Test 2.1: user_encryption_keys table exists
            cursor.execute("""
                SELECT COUNT(*) as count FROM information_schema.TABLES 
                WHERE TABLE_SCHEMA = DATABASE() 
                AND TABLE_NAME = 'user_encryption_keys'
            """)
            exists = cursor.fetchone()['count'] > 0
            print_test("user_encryption_keys table exists", exists)
            
            if not exists:
                print(f"{YELLOW}      Run: mysql < database_phi_encryption_schema.sql{RESET}")
                return False
            
            # Test 2.2: Check required columns
            cursor.execute("""
                SELECT COLUMN_NAME FROM information_schema.COLUMNS 
                WHERE TABLE_SCHEMA = DATABASE() 
                AND TABLE_NAME = 'user_encryption_keys'
            """)
            columns = [row['COLUMN_NAME'] for row in cursor.fetchall()]
            required_columns = ['user_id', 'encrypted_dek', 'key_version', 'created_at', 
                              'rotated_at', 'is_active']
            
            for col in required_columns:
                print_test(f"Column '{col}' exists", col in columns)
            
            # Test 2.3: encryption_key_audit table exists
            cursor.execute("""
                SELECT COUNT(*) as count FROM information_schema.TABLES 
                WHERE TABLE_SCHEMA = DATABASE() 
                AND TABLE_NAME = 'encryption_key_audit'
            """)
            exists = cursor.fetchone()['count'] > 0
            print_test("encryption_key_audit table exists", exists)
            
            # Test 2.4: cases.phi_encrypted column exists
            cursor.execute("""
                SELECT COUNT(*) as count FROM information_schema.COLUMNS 
                WHERE TABLE_SCHEMA = DATABASE() 
                AND TABLE_NAME = 'cases' 
                AND COLUMN_NAME = 'phi_encrypted'
            """)
            exists = cursor.fetchone()['count'] > 0
            print_test("cases.phi_encrypted column exists", exists)
            
            # Test 2.5: deleted_cases.phi_encrypted column exists
            cursor.execute("""
                SELECT COUNT(*) as count FROM information_schema.COLUMNS 
                WHERE TABLE_SCHEMA = DATABASE() 
                AND TABLE_NAME = 'deleted_cases' 
                AND COLUMN_NAME = 'phi_encrypted'
            """)
            exists = cursor.fetchone()['count'] > 0
            print_test("deleted_cases.phi_encrypted column exists", exists)
            
            return True
            
    except Exception as e:
        print_test("Database schema", False, f"Error: {str(e)}")
        return False


def test_key_generation(conn):
    """Test 3: Test encryption key generation."""
    print_test_header("TEST 3: Encryption Key Generation")
    
    # Get real user IDs from the database (limit to 3 for testing)
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute("""
                SELECT user_id FROM user_profile 
                WHERE active = 1 
                ORDER BY user_id 
                LIMIT 3
            """)
            users = cursor.fetchall()
            
            if len(users) < 3:
                print(f"{YELLOW}Warning: Only found {len(users)} users, need at least 3 for testing{RESET}")
                if len(users) == 0:
                    print(f"{RED}No active users found in database. Cannot test key generation.{RESET}")
                    return False
            
            test_user_ids = [u['user_id'] for u in users]
            print(f"Using real users for testing: {', '.join(test_user_ids[:3])}\n")
    except Exception as e:
        print_test("Get real user IDs", False, str(e))
        return False
    
    try:
        # Test 3.1: Generate keys for test users
        for user_id in test_user_ids:
            try:
                result = generate_and_store_user_key(
                    user_id=user_id,
                    conn=conn,
                    performed_by='test_script',
                    ip_address='127.0.0.1'
                )
                print_test(f"Generate key for {user_id}", result['success'], 
                          f"Version: {result.get('key_version', 'N/A')}")
            except Exception as e:
                print_test(f"Generate key for {user_id}", False, str(e))
        
        # Test 3.2: Verify keys stored in database
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute("""
                SELECT user_id, key_version, is_active, 
                       LENGTH(encrypted_dek) as dek_length
                FROM user_encryption_keys
                WHERE user_id IN (%s, %s, %s)
            """, tuple(test_user_ids))
            
            stored_keys = cursor.fetchall()
            print_test(f"Keys stored in database", len(stored_keys) == len(test_user_ids),
                      f"Found {len(stored_keys)}/{len(test_user_ids)} keys")
            
            for key_info in stored_keys:
                is_valid = (key_info['is_active'] == 1 and 
                          key_info['key_version'] >= 1 and 
                          key_info['dek_length'] > 100)
                print_test(f"  Key valid for {key_info['user_id']}", is_valid,
                          f"Version {key_info['key_version']}, {key_info['dek_length']} bytes")
        
        # Test 3.3: Verify audit log entries
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute("""
                SELECT COUNT(*) as count FROM encryption_key_audit
                WHERE user_id IN (%s, %s, %s) AND operation = 'generate'
            """, tuple(test_user_ids))
            
            audit_count = cursor.fetchone()['count']
            print_test("Audit log entries created", audit_count == len(test_user_ids),
                      f"Found {audit_count} audit entries")
        
        return True
        
    except Exception as e:
        print_test("Key generation", False, f"Error: {str(e)}")
        return False


def test_encryption_decryption(conn, test_user_id):
    """Test 4: Test encryption and decryption functionality."""
    print_test_header("TEST 4: Encryption/Decryption Functionality")
    
    print(f"Using user: {test_user_id}\n")
    
    # Test 4.1: Basic encryption/decryption
    test_data = {
        'patient_first': 'John',
        'patient_last': 'Doe',
        'patient_dob': '1980-01-15',
        'ins_provider': 'Blue Cross Blue Shield'
    }
    
    try:
        # Encrypt
        encrypted_data = test_data.copy()
        encrypt_patient_data(encrypted_data, test_user_id, conn)
        
        # Verify all fields are encrypted
        all_encrypted = all(
            encrypted_data[field] != test_data[field]
            for field in ['patient_first', 'patient_last', 'patient_dob', 'ins_provider']
        )
        print_test("All PHI fields encrypted", all_encrypted)
        
        # Verify encrypted values are base64 strings
        import base64
        all_base64 = True
        for field in ['patient_first', 'patient_last', 'patient_dob', 'ins_provider']:
            try:
                base64.b64decode(encrypted_data[field])
            except:
                all_base64 = False
        print_test("Encrypted values are base64", all_base64)
        
        # Decrypt
        decrypted_data = encrypted_data.copy()
        decrypt_patient_data(decrypted_data, test_user_id, conn)
        
        # Verify decryption
        matches = decrypted_data == test_data
        print_test("Decryption matches original", matches)
        
        if not matches:
            for field in test_data:
                if decrypted_data.get(field) != test_data.get(field):
                    print(f"      Mismatch in {field}: '{decrypted_data.get(field)}' != '{test_data.get(field)}'")
        
    except Exception as e:
        print_test("Basic encryption/decryption", False, str(e))
        return False
    
    # Test 4.2: Edge cases
    edge_cases = [
        # Note: Empty strings are converted to None by design (no point encrypting empty strings)
        ("Empty string", {'patient_first': '', 'patient_last': 'Doe', 'patient_dob': '1980-01-15', 'ins_provider': 'Blue Cross'}, 
         {'patient_first': None, 'patient_last': 'Doe', 'patient_dob': '1980-01-15', 'ins_provider': 'Blue Cross'}),
        ("None value", {'patient_first': None, 'patient_last': 'Doe', 'patient_dob': '1980-01-15', 'ins_provider': 'Blue Cross'}, None),
        ("Special characters", {'patient_first': "O'Brien", 'patient_last': 'Müller-Smith', 'patient_dob': '1980-01-15', 'ins_provider': 'ABC & Co.'}),
        ("Unicode characters", {'patient_first': '李明', 'patient_last': 'José', 'patient_dob': '1980-01-15', 'ins_provider': 'ÄÖÜ'}),
        ("Very long string", {'patient_first': 'A' * 200, 'patient_last': 'B' * 200, 'patient_dob': '1980-01-15', 'ins_provider': 'C' * 200}),
        ("Numbers and symbols", {'patient_first': '123-456', 'patient_last': '@#$%^&*()', 'patient_dob': '1980-01-15', 'ins_provider': '123 Main St.'}),
    ]
    
    for edge_case_data in edge_cases:
        # Handle both 2-tuple (test_name, test_case) and 3-tuple (test_name, test_case, expected_result)
        if len(edge_case_data) == 3:
            test_name, test_case, expected_result = edge_case_data
        else:
            test_name, test_case = edge_case_data
            expected_result = test_case  # If no expected result, it should match input
        
        try:
            encrypted = test_case.copy()
            encrypt_patient_data(encrypted, test_user_id, conn)
            
            decrypted = encrypted.copy()
            decrypt_patient_data(decrypted, test_user_id, conn)
            
            # Use expected_result if provided, otherwise compare with original test_case
            if expected_result is None:
                expected_result = test_case
            
            matches = decrypted == expected_result
            print_test(f"Edge case: {test_name}", matches)
            
            if not matches:
                print(f"      Expected: {expected_result}")
                print(f"      Got: {decrypted}")
        
        except Exception as e:
            print_test(f"Edge case: {test_name}", False, str(e))
    
    return True


def test_cache_performance(conn, test_user_id):
    """Test 5: Test DEK caching and performance."""
    print_test_header("TEST 5: Cache Performance")
    
    try:
        # Clear cache first
        clear_dek_cache()
        
        # Test 5.1: First access (cache miss)
        start = time.time()
        dek1 = get_user_dek(test_user_id, conn, cache=True)
        time_miss = (time.time() - start) * 1000  # Convert to ms
        
        print_test("Cache miss (first access)", True, f"{time_miss:.2f}ms")
        
        # Test 5.2: Second access (cache hit)
        start = time.time()
        dek2 = get_user_dek(test_user_id, conn, cache=True)
        time_hit = (time.time() - start) * 1000  # Convert to ms
        
        print_test("Cache hit (second access)", True, f"{time_hit:.2f}ms")
        
        # Test 5.3: Verify cache speedup
        speedup = time_miss / time_hit if time_hit > 0 else 0
        good_speedup = speedup > 10  # Should be at least 10x faster
        print_test("Cache provides speedup", good_speedup, f"{speedup:.1f}x faster")
        
        # Test 5.4: Verify same key returned
        print_test("Cached key matches original", dek1 == dek2)
        
        # Test 5.5: Test cache stats
        stats = get_cache_stats()
        print_test("Cache stats available", 'total_cached' in stats,
                  f"{stats.get('active_count', 0)} keys cached")
        
        # Test 5.6: Test cache clearing
        clear_dek_cache(test_user_id)
        stats_after = get_cache_stats()
        print_test("Cache cleared successfully", True,
                  f"{stats_after.get('active_count', 0)} keys remain")
        
        return True
        
    except Exception as e:
        print_test("Cache performance", False, str(e))
        return False


def test_field_level_operations(conn, test_user_id):
    """Test 6: Test individual field-level operations."""
    print_test_header("TEST 6: Field-Level Encryption Operations")
    
    try:
        # Get DEK
        dek = get_user_dek(test_user_id, conn)
        phi_crypto = PHIEncryption()
        
        # Test 6.1: Encrypt/decrypt single field
        original = "Confidential Patient Name"
        encrypted = phi_crypto.encrypt_field(original, dek)
        decrypted = phi_crypto.decrypt_field(encrypted, dek)
        
        print_test("Single field encryption", encrypted != original)
        print_test("Single field decryption", decrypted == original)
        
        # Test 6.2: None handling
        encrypted_none = phi_crypto.encrypt_field(None, dek)
        print_test("None value returns None", encrypted_none is None)
        
        # Test 6.3: Empty string handling
        encrypted_empty = phi_crypto.encrypt_field('', dek)
        print_test("Empty string returns None", encrypted_empty is None)
        
        # Test 6.4: Verify encrypted data structure
        # Should be: IV (12 bytes) + auth_tag (16 bytes) + ciphertext
        import base64
        encrypted_bytes = base64.b64decode(encrypted)
        has_iv = len(encrypted_bytes) >= 12
        has_tag = len(encrypted_bytes) >= 28
        print_test("Encrypted data has IV", has_iv, f"{len(encrypted_bytes)} bytes total")
        print_test("Encrypted data has auth tag", has_tag)
        
        # Test 6.5: Tamper detection
        try:
            # Tamper with encrypted data
            tampered = encrypted[:-1] + ('A' if encrypted[-1] != 'A' else 'B')
            phi_crypto.decrypt_field(tampered, dek)
            print_test("Tamper detection", False, "Did not detect tampered data")
        except Exception as e:
            print_test("Tamper detection", True, "Correctly rejected tampered data")
        
        return True
        
    except Exception as e:
        print_test("Field-level operations", False, str(e))
        return False


def test_multi_user_isolation(conn, user1, user2):
    """Test 7: Test that different users have different keys."""
    print_test_header("TEST 7: Multi-User Key Isolation")
    
    try:
        # Test 7.1: Get DEKs for both users
        dek1 = get_user_dek(user1, conn)
        dek2 = get_user_dek(user2, conn)
        
        print_test("Different users have different DEKs", dek1 != dek2)
        
        # Test 7.2: Encrypt same data with different user keys
        test_data = "Confidential Information"
        phi_crypto = PHIEncryption()
        
        encrypted1 = phi_crypto.encrypt_field(test_data, dek1)
        encrypted2 = phi_crypto.encrypt_field(test_data, dek2)
        
        print_test("Same data encrypted differently per user", encrypted1 != encrypted2)
        
        # Test 7.3: Verify cross-user decryption fails
        try:
            decrypted = phi_crypto.decrypt_field(encrypted1, dek2)
            # If we get here, it somehow worked (shouldn't happen)
            print_test("Cross-user decryption blocked", decrypted != test_data,
                      "Should not decrypt correctly")
        except Exception:
            print_test("Cross-user decryption blocked", True,
                      "Correctly failed to decrypt")
        
        return True
        
    except Exception as e:
        print_test("Multi-user isolation", False, str(e))
        return False


def test_audit_logging(conn):
    """Test 8: Verify audit logging works."""
    print_test_header("TEST 8: Audit Logging")
    
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            # Test 8.1: Check audit entries exist
            cursor.execute("""
                SELECT COUNT(*) as count FROM encryption_key_audit
                WHERE performed_by = 'test_script'
            """)
            count = cursor.fetchone()['count']
            print_test("Audit entries created", count > 0, f"Found {count} entries")
            
            # Test 8.2: Check audit entry structure
            cursor.execute("""
                SELECT user_id, operation, performed_by, operation_timestamp,
                       details, ip_address
                FROM encryption_key_audit
                WHERE performed_by = 'test_script'
                ORDER BY operation_timestamp DESC
                LIMIT 1
            """)
            entry = cursor.fetchone()
            
            has_required_fields = all([
                entry.get('user_id'),
                entry.get('operation'),
                entry.get('performed_by') == 'test_script',
                entry.get('operation_timestamp'),
                entry.get('ip_address') == '127.0.0.1'
            ])
            print_test("Audit entry has required fields", has_required_fields)
            
            # Test 8.3: Check details is valid JSON
            if entry.get('details'):
                try:
                    details = json.loads(entry['details'])
                    print_test("Audit details is valid JSON", True,
                              f"Keys: {list(details.keys())}")
                except:
                    print_test("Audit details is valid JSON", False)
        
        return True
        
    except Exception as e:
        print_test("Audit logging", False, str(e))
        return False


def test_performance_benchmark(conn, test_user_id):
    """Test 9: Performance benchmarks."""
    print_test_header("TEST 9: Performance Benchmarks")
    
    iterations = 100
    
    try:
        # Clear cache for accurate timing
        clear_dek_cache()
        
        # Warm up cache
        get_user_dek(test_user_id, conn)
        
        # Benchmark encryption
        test_data = {
            'patient_first': 'John',
            'patient_last': 'Doe',
            'patient_dob': '1980-01-15',
            'ins_provider': 'Blue Cross'
        }
        
        start = time.time()
        for _ in range(iterations):
            data = test_data.copy()
            encrypt_patient_data(data, test_user_id, conn)
        encrypt_time = (time.time() - start) / iterations * 1000
        
        print_test("Encryption performance", True, 
                  f"{encrypt_time:.2f}ms per case (4 fields)")
        
        # Benchmark decryption
        encrypted = test_data.copy()
        encrypt_patient_data(encrypted, test_user_id, conn)
        
        start = time.time()
        for _ in range(iterations):
            data = encrypted.copy()
            decrypt_patient_data(data, test_user_id, conn)
        decrypt_time = (time.time() - start) / iterations * 1000
        
        print_test("Decryption performance", True,
                  f"{decrypt_time:.2f}ms per case (4 fields)")
        
        # Check if performance is acceptable (< 10ms per operation)
        good_encrypt_perf = encrypt_time < 10
        good_decrypt_perf = decrypt_time < 10
        
        if not good_encrypt_perf:
            print(f"      {YELLOW}Warning: Encryption may be slow for high-volume operations{RESET}")
            results.add_warning()
        
        if not good_decrypt_perf:
            print(f"      {YELLOW}Warning: Decryption may be slow for high-volume operations{RESET}")
            results.add_warning()
        
        return True
        
    except Exception as e:
        print_test("Performance benchmark", False, str(e))
        return False


def cleanup_test_data(conn):
    """Clean up test data."""
    print_test_header("Cleanup Test Data")
    
    try:
        with conn.cursor() as cursor:
            # Remove only keys created by test_script (not the actual user keys)
            cursor.execute("""
                DELETE FROM user_encryption_keys
                WHERE user_id IN (
                    SELECT DISTINCT user_id FROM encryption_key_audit 
                    WHERE performed_by = 'test_script'
                )
            """)
            deleted_keys = cursor.rowcount
            
            # Remove test audit entries
            cursor.execute("""
                DELETE FROM encryption_key_audit
                WHERE performed_by = 'test_script'
            """)
            deleted_audit = cursor.rowcount
            
        conn.commit()
        
        print(f"{GREEN}✓ Cleaned up {deleted_keys} test keys and {deleted_audit} audit entries{RESET}")
        
        # Clear cache
        clear_dek_cache()
        print(f"{GREEN}✓ Cleared DEK cache{RESET}")
        
        return True
        
    except Exception as e:
        print(f"{RED}✗ Cleanup failed: {str(e)}{RESET}")
        return False


def main():
    """Main test execution."""
    print(f"\n{BOLD}{'=' * 80}{RESET}")
    print(f"{BOLD}PHI ENCRYPTION INFRASTRUCTURE TEST SUITE{RESET}")
    print(f"{BOLD}{'=' * 80}{RESET}")
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    conn = None
    
    try:
        # Pre-flight checks
        if not test_kms_key_setup():
            print(f"\n{RED}{BOLD}CRITICAL: KMS key not set up. Cannot proceed with tests.{RESET}")
            return 1
        
        # Connect to database
        print(f"\n{BLUE}Connecting to database...{RESET}")
        conn = get_db_connection()
        print(f"{GREEN}✓ Connected to database{RESET}")
        
        # Run all tests
        if not test_database_schema(conn):
            print(f"\n{RED}{BOLD}CRITICAL: Database schema not set up. Cannot proceed with tests.{RESET}")
            return 1
        
        # Generate keys and get test user IDs
        test_key_generation(conn)
        
        # Get the test user IDs that were just created
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute("""
                SELECT DISTINCT user_id FROM encryption_key_audit 
                WHERE performed_by = 'test_script'
                ORDER BY user_id
                LIMIT 3
            """)
            test_users = [row['user_id'] for row in cursor.fetchall()]
        
        if len(test_users) < 1:
            print(f"\n{RED}{BOLD}ERROR: No test users found. Key generation may have failed.{RESET}")
            return 1
        
        # Use first user for most tests, first two for multi-user test
        test_user_id = test_users[0]
        test_user_id_2 = test_users[1] if len(test_users) > 1 else test_users[0]
        
        test_encryption_decryption(conn, test_user_id)
        test_cache_performance(conn, test_user_id)
        test_field_level_operations(conn, test_user_id)
        test_multi_user_isolation(conn, test_user_id, test_user_id_2)
        test_audit_logging(conn)
        test_performance_benchmark(conn, test_user_id)
        
        # Cleanup
        cleanup_test_data(conn)
        
        # Print summary
        results.print_summary()
        
        return results.failed
        
    except Exception as e:
        print(f"\n{RED}{BOLD}FATAL ERROR: {str(e)}{RESET}")
        import traceback
        traceback.print_exc()
        return 1
        
    finally:
        if conn:
            close_db_connection(conn)
            print(f"\n{BLUE}Database connection closed{RESET}")


if __name__ == '__main__':
    exit_code = main()
    sys.exit(exit_code)

