# PHI Encryption Testing Quick Start

## Overview

This guide will walk you through testing the PHI encryption infrastructure **before** touching any live data. We've created comprehensive tests that validate every aspect of the system.

---

## 🚀 Quick Start (3 Simple Steps)

### Step 1: Run Setup Script

This will check if prerequisites exist and help you create them if needed:

```bash
cd /home/scadreau/surgicase
python tests/setup_phi_encryption.py
```

The script will:
- ✅ Check if KMS key exists (offer to create if missing)
- ✅ Check if database schema exists (offer to run if missing)
- ✅ Guide you through any missing prerequisites

### Step 2: Run Comprehensive Tests

```bash
python tests/test_phi_encryption.py
```

This will run **9 comprehensive test suites** with **50+ individual tests**:

1. **KMS Key Setup** - Verify key exists and permissions work
2. **Database Schema** - Verify all tables and columns exist
3. **Key Generation** - Generate test encryption keys for 3 test users
4. **Encryption/Decryption** - Test basic encryption and all edge cases
5. **Cache Performance** - Verify caching provides 10x+ speedup
6. **Field-Level Operations** - Test individual field encryption
7. **Multi-User Isolation** - Verify users can't decrypt each other's data
8. **Audit Logging** - Verify all operations are logged
9. **Performance Benchmarks** - Measure actual performance metrics

### Step 3: Review Results

The test will output colored results:
- 🟢 **Green ✓** = Test passed
- 🔴 **Red ✗** = Test failed
- 🟡 **Yellow ⚠** = Warning (not critical)

At the end you'll see a summary:
```
TEST SUMMARY
============
Passed: 52
Failed: 0
Warnings: 0

✓ ALL TESTS PASSED!
```

---

## 📊 What The Tests Cover

### Security Tests
- ✅ Each user has unique encryption key
- ✅ Users cannot decrypt each other's data
- ✅ Tampered data is rejected
- ✅ All operations are audited

### Functionality Tests
- ✅ Basic encryption/decryption works
- ✅ Empty strings handled correctly
- ✅ None values handled correctly
- ✅ Special characters (O'Brien, Müller)
- ✅ Unicode characters (李明, José)
- ✅ Very long strings (200+ chars)
- ✅ Numbers and symbols

### Performance Tests
- ✅ Cache provides 10x+ speedup
- ✅ Encryption < 10ms per case (4 fields)
- ✅ Decryption < 10ms per case (4 fields)
- ✅ First access ~50-100ms (KMS call)
- ✅ Cached access ~0.1-1ms

### Infrastructure Tests
- ✅ KMS key exists and accessible
- ✅ Database tables created correctly
- ✅ Audit logging works
- ✅ Cache management works

---

## 🔍 Detailed Test Output Example

```
================================================================================
TEST 1: KMS Key Setup and Access
================================================================================
✓ PASS - KMS key exists
      Key ID: abc123..., State: Enabled
✓ PASS - KMS key enabled
✓ PASS - KMS generate_data_key permission
      Generated 32 byte key
✓ PASS - KMS decrypt permission
      Successfully decrypted 32 byte key

================================================================================
TEST 4: Encryption/Decryption Functionality
================================================================================
✓ PASS - All PHI fields encrypted
✓ PASS - Encrypted values are base64
✓ PASS - Decryption matches original
✓ PASS - Edge case: Empty string
✓ PASS - Edge case: None value
✓ PASS - Edge case: Special characters
✓ PASS - Edge case: Unicode characters
✓ PASS - Edge case: Very long string
✓ PASS - Edge case: Numbers and symbols

================================================================================
TEST 5: Cache Performance
================================================================================
✓ PASS - Cache miss (first access)
      52.34ms
✓ PASS - Cache hit (second access)
      0.23ms
✓ PASS - Cache provides speedup
      227.6x faster
```

---

## 🧪 Manual Testing (Optional)

If you want to test manually in addition to the automated tests:

### Test 1: Generate Keys for Real Users

```bash
# Dry run first - see what would happen
python utils/generate_encryption_keys.py --dry-run

# If it looks good, generate for real
python utils/generate_encryption_keys.py
```

Expected output:
```
Current Status:
  Total active users: 110
  Users with keys: 0
  Users without keys: 110
  Coverage: 0.0%

Generate encryption keys for 110 users? (yes/no): yes

[1/110] Processing user: USER001 (John Doe - john@example.com)
  ✓ Successfully generated key for user: USER001
...

Updated Status:
  Total active users: 110
  Users with keys: 110
  Users without keys: 0
  Coverage: 100.0%
```

### Test 2: Check Admin Endpoints

```bash
# Get key status (replace YOUR_ADMIN_ID with your user_id)
curl "http://localhost:8000/admin/encryption/key-status?admin_user_id=YOUR_ADMIN_ID"

# Expected output:
{
  "total_active_users": 110,
  "users_with_keys": 110,
  "users_without_keys": 0,
  "coverage_percentage": 100.0,
  "cache_stats": {
    "total_cached": 5,
    "active_count": 5,
    "cache_ttl_hours": 24
  }
}
```

### Test 3: Manual Encryption/Decryption

```python
# Create test_manual_encryption.py
import sys
sys.path.insert(0, '/home/scadreau/surgicase')

from core.database import get_db_connection, close_db_connection
from utils.phi_encryption import encrypt_patient_data, decrypt_patient_data

# Connect
conn = get_db_connection()

# Test data
original = {
    'patient_first': 'John',
    'patient_last': 'Doe',
    'patient_dob': '1980-01-15',
    'ins_provider': 'Blue Cross'
}

# Use a real user_id from your system
user_id = 'YOUR_REAL_USER_ID'

# Encrypt
encrypted = original.copy()
encrypt_patient_data(encrypted, user_id, conn)
print("Encrypted:", encrypted)

# Decrypt
decrypted = encrypted.copy()
decrypt_patient_data(decrypted, user_id, conn)
print("Decrypted:", decrypted)

# Verify
assert decrypted == original
print("✓ Success! Encryption/Decryption works!")

close_db_connection(conn)
```

---

## ⚠️ Important Notes

### Test Data Cleanup
The automated test script automatically cleans up its test data:
- Removes test encryption keys (TEST_USER_001, TEST_USER_002, TEST_USER_003)
- Removes test audit entries
- Clears DEK cache

Your real user data is **never touched** by the test script.

### What Gets Created
During testing, the following are created:
- 3 test encryption keys (cleaned up after)
- Several audit log entries (cleaned up after)
- Cache entries in memory (cleared after)

### Safe to Run Multiple Times
The test script is idempotent - you can run it as many times as you want. Each run:
- Creates fresh test keys
- Runs all tests
- Cleans up after itself

---

## 🚨 Troubleshooting

### KMS Key Not Found
```
✗ FAIL - KMS key exists
      Key 'alias/surgicase-phi-master' not found. Please create it first.
```

**Solution:** Run `python tests/setup_phi_encryption.py` and choose to create the key.

### Database Schema Missing
```
✗ FAIL - user_encryption_keys table exists
```

**Solution:** Run `python tests/setup_phi_encryption.py` and choose to run the schema.

### Permission Denied
```
Error: User does not have sufficient permissions to perform: kms:Decrypt
```

**Solution:** Update your IAM role to include KMS permissions:
```json
{
  "Effect": "Allow",
  "Action": [
    "kms:Decrypt",
    "kms:Encrypt",
    "kms:GenerateDataKey",
    "kms:DescribeKey"
  ],
  "Resource": "arn:aws:kms:us-east-1:*:key/*"
}
```

### Tests Fail with Database Error
Make sure your database connection works:
```bash
python -c "from core.database import get_db_connection; conn = get_db_connection(); print('✓ Connected')"
```

---

## 📈 Success Criteria

Before proceeding to Phase 3 (integrating with case endpoints), ensure:

- ✅ All automated tests pass (50+ tests)
- ✅ Performance is acceptable (< 10ms per operation)
- ✅ Cache provides significant speedup (10x+)
- ✅ Edge cases handled correctly
- ✅ Audit logging works
- ✅ Multi-user isolation verified

---

## 🎯 Next Steps After Successful Testing

Once all tests pass:

1. **Review Performance Metrics**
   - Check if encryption/decryption times are acceptable
   - Verify cache hit rates are good

2. **Generate Keys for All Real Users**
   ```bash
   python utils/generate_encryption_keys.py
   ```

3. **Test Admin Endpoints**
   - Use the admin endpoints to verify key coverage
   - Check audit logs

4. **Proceed to Phase 3**
   - Update case endpoints to use encryption
   - Test with non-production data first

5. **Backup Before Migration**
   ```bash
   mysqldump surgicase cases > cases_backup_$(date +%Y%m%d_%H%M%S).sql
   mysqldump surgicase deleted_cases > deleted_cases_backup_$(date +%Y%m%d_%H%M%S).sql
   ```

---

## 📞 Support

If tests fail or you encounter issues:
1. Check the detailed error messages in the test output
2. Review CloudWatch logs for AWS KMS operations
3. Check application logs for encryption errors
4. Verify AWS credentials and permissions

---

## Summary

**The test suite validates everything before you touch live data:**
- 9 comprehensive test suites
- 50+ individual test cases
- All edge cases covered
- Performance benchmarked
- Security verified
- Audit logging validated

Run the tests, verify they pass, and you can proceed with confidence! 🚀

