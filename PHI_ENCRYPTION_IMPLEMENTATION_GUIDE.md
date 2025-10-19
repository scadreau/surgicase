# PHI Field Encryption Implementation Guide

**Created:** 2025-10-19  
**Author:** Scott Cadreau  
**Status:** Phase 1 & 2 Complete - Ready for Testing

## Overview

This document describes the per-user field-level encryption system implemented for PHI (Protected Health Information) data in the SurgiCase application. The system uses AWS KMS with per-user data encryption keys (DEKs) for HIPAA-compliant encryption of patient data.

---

## Architecture Summary

### Encryption Model
- **One AWS KMS Master Key:** `alias/surgicase-phi-master` (to be created)
- **One DEK per user_id:** Each healthcare provider has their own encryption key
- **In-memory caching:** DEKs cached for 24 hours for performance
- **Field-level encryption:** AES-256-GCM encryption for individual PHI fields

### Fields to be Encrypted
The following fields in the `cases` table will be encrypted:
1. `patient_first` - Patient's first name
2. `patient_last` - Patient's last name
3. `patient_dob` - Patient's date of birth
4. `ins_provider` - Insurance provider name

The same fields in `deleted_cases` table will also be encrypted.

---

## Files Created (Phase 1 & 2)

### 1. Database Schema
**File:** `database_phi_encryption_schema.sql`

Creates the following:
- `user_encryption_keys` table - Stores encrypted DEKs per user
- `encryption_key_audit` table - Audit trail for HIPAA compliance
- `phi_encrypted` column in `cases` and `deleted_cases` tables - Tracks encryption status

**⚠️ TO RUN:** This SQL file needs to be executed on your database before testing

### 2. Core Encryption Utility
**File:** `utils/phi_encryption.py`

**Key Functions:**
- `PHIEncryption` class - Core encryption/decryption using AES-256-GCM
- `generate_user_dek(user_id)` - Generate new DEK for a user
- `get_user_dek(user_id, conn)` - Retrieve and cache user's DEK
- `encrypt_patient_data(data, user_id, conn)` - Encrypt all PHI fields in a dict
- `decrypt_patient_data(data, user_id, conn)` - Decrypt all PHI fields in a dict
- `generate_and_store_user_key(user_id, conn)` - Full key generation and storage
- `clear_dek_cache(user_id=None)` - Clear cache for one or all users
- `get_cache_stats()` - Get cache performance statistics

**Features:**
- Automatic key caching (24-hour TTL)
- Thread-safe cache operations
- Audit logging for all key operations
- Handles None/empty field values gracefully

### 3. Key Generation Script
**File:** `utils/generate_encryption_keys.py`

**Usage:**
```bash
# Dry run - see what would happen
python utils/generate_encryption_keys.py --dry-run

# Generate keys for users without them
python utils/generate_encryption_keys.py

# Force regenerate all keys (careful!)
python utils/generate_encryption_keys.py --force
```

**Features:**
- Generates keys for all users missing them
- Shows statistics before and after
- Batch processing with progress indicators
- Error handling and reporting
- Audit logging for each key generation

### 4. Admin Endpoints
**File:** `endpoints/admin/encryption_key_management.py`

**Endpoints Created:**

#### POST `/admin/encryption/generate-key`
Generate encryption key for a specific user
- Parameters: `user_id`, `admin_user_id`
- Requires: user_type >= 100 (admin)
- Logs operation for HIPAA compliance

#### GET `/admin/encryption/key-status`
Get encryption key coverage statistics or specific user status
- Parameters: `admin_user_id`, `target_user_id` (optional)
- Returns overall stats or specific user key info
- Includes cache statistics

#### POST `/admin/encryption/clear-cache`
Clear DEK cache for troubleshooting
- Parameters: `admin_user_id`, `target_user_id` (optional)
- Can clear specific user or all caches
- Useful after key rotation

#### GET `/admin/encryption/audit-log`
Retrieve encryption key operation audit trail
- Parameters: `admin_user_id`, `target_user_id` (optional), `limit` (default: 100)
- Returns audit entries for HIPAA compliance
- Tracks all key generation, rotation, and access

### 5. Main Application Updates
**File:** `main.py`

- Imported and registered the encryption key management router
- New endpoints available under `/admin/encryption/*`
- Tagged as "admin" in API documentation

---

## Setup Instructions (Before Testing)

### Step 1: Create AWS KMS Master Key

You'll need to create the KMS master key manually. Here's the AWS CLI command:

```bash
aws kms create-key \
  --description "SurgiCase PHI field encryption master key" \
  --key-usage ENCRYPT_DECRYPT \
  --region us-east-1 \
  --tags TagKey=Application,TagValue=SurgiCase TagKey=Purpose,TagValue=PHIEncryption

# Get the KeyId from the response, then create alias
aws kms create-alias \
  --alias-name alias/surgicase-phi-master \
  --target-key-id <KEY_ID_FROM_ABOVE> \
  --region us-east-1
```

**Alternative:** Use AWS Console:
1. Go to AWS KMS in us-east-1
2. Create symmetric key
3. Name: "surgicase-phi-master"
4. Description: "SurgiCase PHI field encryption master key"
5. Create alias: `alias/surgicase-phi-master`
6. Set key policy to allow your application IAM role

### Step 2: Run Database Schema

```bash
# Connect to your database and run:
mysql -h <your-host> -u <user> -p surgicase < database_phi_encryption_schema.sql
```

Or execute the SQL file through your preferred database client.

### Step 3: Verify Tables Created

```sql
-- Check tables exist
SHOW TABLES LIKE '%encryption%';

-- Should show:
-- user_encryption_keys
-- encryption_key_audit

-- Check columns added
DESCRIBE cases;  -- Should have phi_encrypted column
DESCRIBE deleted_cases;  -- Should have phi_encrypted column
```

### Step 4: Generate Keys for Existing Users

```bash
# First do a dry run to see what will happen
cd /home/scadreau/surgicase
python utils/generate_encryption_keys.py --dry-run

# If it looks good, run for real
python utils/generate_encryption_keys.py
```

Expected output:
```
Current Status:
  Total active users: 110
  Users with keys: 0
  Users without keys: 110
  Coverage: 0.0%

Found 110 users needing encryption keys
Generate encryption keys for 110 users? (yes/no): yes

[1/110] Processing user: USER001 (John Smith - john@example.com)
  ✓ Successfully generated key for user: USER001
...

RESULTS
Total users processed: 110
Successful: 110
Failed: 0
Time elapsed: 11.5 seconds

Updated Status:
  Total active users: 110
  Users with keys: 110
  Users without keys: 0
  Coverage: 100.0%
```

---

## Testing Instructions

### 1. Test Admin Endpoints

```bash
# Check overall key status
curl "http://localhost:8000/admin/encryption/key-status?admin_user_id=YOUR_ADMIN_ID"

# Check specific user
curl "http://localhost:8000/admin/encryption/key-status?admin_user_id=YOUR_ADMIN_ID&target_user_id=TEST_USER"

# Generate key for a test user
curl -X POST "http://localhost:8000/admin/encryption/generate-key?user_id=TEST_USER&admin_user_id=YOUR_ADMIN_ID"

# View audit log
curl "http://localhost:8000/admin/encryption/audit-log?admin_user_id=YOUR_ADMIN_ID&limit=10"
```

### 2. Test Encryption/Decryption Functions

```python
# Create a test script: test_encryption.py
import sys
sys.path.insert(0, '/home/scadreau/surgicase')

from core.database import get_db_connection, close_db_connection
from utils.phi_encryption import encrypt_patient_data, decrypt_patient_data

conn = get_db_connection()

# Test data
test_data = {
    'patient_first': 'John',
    'patient_last': 'Doe',
    'patient_dob': '1980-01-15',
    'ins_provider': 'Blue Cross'
}

user_id = 'YOUR_TEST_USER_ID'

# Encrypt
encrypted = encrypt_patient_data(test_data.copy(), user_id, conn)
print("Encrypted:", encrypted)

# Decrypt
decrypted = decrypt_patient_data(encrypted.copy(), user_id, conn)
print("Decrypted:", decrypted)

# Verify
assert decrypted == test_data
print("✓ Encryption/Decryption test passed!")

close_db_connection(conn)
```

### 3. Test Cache Performance

```python
import sys
import time
sys.path.insert(0, '/home/scadreau/surgicase')

from core.database import get_db_connection, close_db_connection
from utils.phi_encryption import get_user_dek, get_cache_stats, clear_dek_cache

conn = get_db_connection()
user_id = 'YOUR_TEST_USER_ID'

# First call (cache miss)
start = time.time()
dek1 = get_user_dek(user_id, conn)
time1 = time.time() - start
print(f"First call (cache miss): {time1*1000:.2f}ms")

# Second call (cache hit)
start = time.time()
dek2 = get_user_dek(user_id, conn)
time2 = time.time() - start
print(f"Second call (cache hit): {time2*1000:.2f}ms")

print(f"Cache speedup: {time1/time2:.1f}x faster")

# Check cache stats
stats = get_cache_stats()
print(f"Cache stats: {stats}")

close_db_connection(conn)
```

---

## Performance Considerations

### Cache Performance
- **First access:** ~50-100ms (KMS decrypt + database fetch)
- **Cached access:** ~0.1-1ms (memory lookup)
- **Cache TTL:** 24 hours
- **Expected cache hit rate:** >95% in normal operation

### KMS Costs
- **Per-user keys:** 110-750 keys stored
- **KMS API calls:** ~100-750 per day (with caching)
- **Estimated cost:** <$0.10/day for 750 users with 24-hour cache

### Encryption Overhead
- **Per field:** ~0.5-1ms additional time
- **Per case (4 fields):** ~2-4ms additional time
- **Negligible impact** on overall API response time

---

## Security Features

### HIPAA Compliance
✅ Encryption at rest (AES-256-GCM)  
✅ Key management (AWS KMS)  
✅ Audit trails (encryption_key_audit table)  
✅ Access controls (admin-only key management)  
✅ Per-user data isolation  

### Data Integrity
- GCM mode provides authentication (prevents tampering)
- Each encrypted value includes IV + auth tag
- Decryption fails if data is modified

### Key Security
- Master key never leaves AWS KMS
- DEKs encrypted at rest in database
- DEKs cached in memory only (cleared on restart)
- Thread-safe cache operations

---

## Next Steps (Phase 3+)

After testing Phases 1 & 2, the following phases remain:

### Phase 3: Update Case Endpoints
- Modify `create_case.py` to encrypt PHI on insert
- Modify `get_case.py` to decrypt PHI on select
- Modify `update_case.py` to handle PHI updates
- Update `filter_cases.py`, `group_cases.py` for decryption
- Update `delete_case.py` for encrypted deletions

### Phase 4: Data Migration
- Backup `cases` and `deleted_cases` tables
- Migrate existing unencrypted data to encrypted format
- Validate migration success
- Update `phi_encrypted` flag to 1

### Phase 5: Testing & Validation
- Unit tests for encryption functions
- Integration tests for endpoints
- Performance testing
- Security validation

### Phase 6: Monitoring & Documentation
- CloudWatch metrics for KMS usage
- Cache performance monitoring
- API documentation updates
- Runbook for key rotation

---

## Backup Recommendation

**⚠️ CRITICAL: Before running any migration (Phase 4), create full backups:**

```bash
# Backup cases table
mysqldump -h <host> -u <user> -p surgicase cases > cases_backup_pre_encryption.sql

# Backup deleted_cases table
mysqldump -h <host> -u <user> -p surgicase deleted_cases > deleted_cases_backup_pre_encryption.sql

# Verify backups
ls -lh *_backup_pre_encryption.sql
```

---

## Troubleshooting

### KMS Key Not Found
```
Error: Alias/surgicase-phi-master is not found
Solution: Create the KMS master key (see Step 1)
```

### Permission Denied
```
Error: User does not have sufficient permissions to perform: kms:Decrypt
Solution: Update IAM role to include KMS permissions
```

### Cache Issues
```bash
# Clear all caches via API
curl -X POST "http://localhost:8000/admin/encryption/clear-cache?admin_user_id=ADMIN_ID"

# Or programmatically
from utils.phi_encryption import clear_dek_cache
clear_dek_cache()
```

### Database Schema Issues
```sql
-- Check if tables exist
SELECT TABLE_NAME FROM information_schema.TABLES 
WHERE TABLE_SCHEMA = 'surgicase' 
AND TABLE_NAME LIKE '%encryption%';

-- Check if column exists
SELECT COLUMN_NAME FROM information_schema.COLUMNS 
WHERE TABLE_SCHEMA = 'surgicase' 
AND TABLE_NAME = 'cases' 
AND COLUMN_NAME = 'phi_encrypted';
```

---

## Support

For issues or questions:
1. Check CloudWatch logs for KMS operations
2. Check application logs for encryption errors
3. Review audit log via admin endpoint
4. Test with `--dry-run` flags when available

---

## Summary

**Phase 1 & 2 are now complete and ready for testing.** The infrastructure is in place to:
- Generate per-user encryption keys
- Manage keys via admin endpoints
- Cache keys for performance
- Audit all key operations
- Support 750+ users with minimal cost

Once you've tested and validated these phases in your sandbox environment, we can proceed with Phases 3-6 to integrate encryption into the case endpoints and migrate existing data.

