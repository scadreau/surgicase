# PHI Encryption - Production Rollout Guide

## Overview
This document provides a step-by-step guide for rolling out PHI encryption to all users in production.

---

## Files That Need TEST_USER_ID Check Removed

### Decryption Endpoints (7 files)
1. ✅ `endpoints/case/get_case.py` (line 325)
   - Remove: `if user_id == TEST_USER_ID:`
   - Keep: `if case_data.get('phi_encrypted') == 1:`

2. ✅ `endpoints/case/filter_cases.py` (lines 250-251)
   - Remove: `TEST_USER_ID` and `needs_decryption` check
   - Keep: `if case_data.get('phi_encrypted') == 1:`

3. ✅ `endpoints/backoffice/get_cases_by_status.py` (lines 252, 261)
   - Remove: `and case_owner_user_id == TEST_USER_ID`
   - Keep: Multi-user decryption logic

4. ✅ `endpoints/case/group_cases.py` (lines 151-152, 298, 307)
   - Two functions to update
   - Remove: `needs_decryption` and `TEST_USER_ID` checks
   - Keep: `if case_data.get('phi_encrypted') == 1:`

5. ✅ `endpoints/exports/case_export.py` (lines 239, 251)
   - Remove: `and case_owner_user_id == TEST_USER_ID`
   - Keep: Multi-user decryption logic

6. ✅ `endpoints/backoffice/get_case_images.py` (lines 286-287, 291)
   - Remove: `TEST_USER_ID` check
   - Keep: `if case.get('phi_encrypted') == 1:`

7. ✅ `endpoints/reports/provider_payment_report.py` (lines 506-507, 511, 1071-1072)
   - Two functions to update
   - Remove: `TEST_USER_ID` checks
   - Keep: `if case.get('phi_encrypted') == 1:`

### Encryption Endpoints (2 files)
8. ✅ `endpoints/case/create_case.py` (lines 84, 114, 128, 60)
   - Remove: `TEST_USER_ID` and `use_encryption` check
   - Change: Always encrypt for all users
   - Keep: Duplicate check decryption logic

9. ✅ `endpoints/case/update_case.py` (lines 249, 258)
   - Remove: `TEST_USER_ID` and `use_encryption` check
   - Change: Always encrypt PHI fields for all users

---

## Pre-Migration Checklist

### 1. Database Backups (CRITICAL!)
- [ ] Full database backup to S3
- [ ] Test restore from backup
- [ ] Snapshot RDS instance
- [ ] Document restore procedure
- [ ] Keep backup for at least 90 days

### 2. Generate DEKs for All Users
- [ ] Run script to generate DEKs for all active users
- [ ] Verify `user_encryption_keys` table populated
- [ ] Check KMS key permissions
- [ ] Test DEK generation for new users
- [ ] Warm DEK cache on server startup (already done)

### 3. Testing Phase
- [ ] Test encryption with multiple users
- [ ] Test decryption in all 9 endpoints
- [ ] Test CSV exports
- [ ] Test PDF reports
- [ ] Test ZIP file downloads
- [ ] Test duplicate case detection
- [ ] Test case updates
- [ ] Verify cache warming on startup
- [ ] Load test with encrypted data

### 4. Monitoring Setup
- [ ] Set up CloudWatch alarms for KMS usage
- [ ] Monitor DEK cache hit rates
- [ ] Track decryption errors
- [ ] Set up alerts for encryption failures
- [ ] Monitor performance impact

---

## Migration Strategies

### Option 1: Big Bang (Risky)
**Pros:** Clean cutover, all users encrypted at once  
**Cons:** High risk, hard to rollback

**Steps:**
1. Schedule maintenance window (2-3 hours)
2. Take final backup
3. Generate DEKs for all users
4. Remove TEST_USER_ID checks from all 9 files
5. Deploy updated code
6. Restart server (warms DEK cache)
7. Test critical workflows
8. Monitor for 24 hours

### Option 2: Gradual Rollout (RECOMMENDED)
**Pros:** Lower risk, easier rollback, controlled testing  
**Cons:** Takes longer, requires user list management

**Steps:**
1. Create `encryption_enabled_users` table or config
2. Modify code to check list instead of single TEST_USER_ID
3. Add users to list in small batches (10-20 at a time)
4. Monitor each batch for 24-48 hours
5. Gradually expand to all users over 2-4 weeks
6. Once all users enabled, remove list logic

### Option 3: New-Data-Only (Safest)
**Pros:** Lowest risk, existing data unchanged  
**Cons:** Mixed encrypted/unencrypted forever (unless migrated)

**Steps:**
1. Remove TEST_USER_ID checks from code
2. Deploy - all NEW cases will be encrypted
3. OLD cases remain unencrypted (phi_encrypted=0)
4. System handles both seamlessly
5. Optionally migrate old data later

---

## Code Changes for Production

### Find & Replace Pattern
```bash
# Remove test user checks - DO THIS CAREFULLY!
# Review each file individually to ensure correct removal

# Example for get_case.py:
# BEFORE:
if user_id == TEST_USER_ID:
    logger.info(f"[ENCRYPTION TEST] Decrypting...")
    
# AFTER:
# Remove the if statement, keep the decryption logic
logger.info(f"[ENCRYPTION] Decrypting...")
```

### Verification Command
```bash
# After changes, verify no TEST_USER_ID references remain:
grep -r "TEST_USER_ID" endpoints/ --include="*.py"
grep -r "ENCRYPTION TEST" endpoints/ --include="*.py"
```

---

## Rollback Plan

### If Issues Detected Within 24 Hours
1. **Code Rollback:**
   ```bash
   git revert <commit-hash>
   # Re-deploy previous version
   ```

2. **Database Restoration:**
   - Restore from RDS snapshot (if encryption caused data issues)
   - Keep `user_encryption_keys` table (DEKs still valid)

3. **Verify Rollback:**
   - Test data retrieval
   - Check case creation
   - Verify reports generation

### Emergency Contacts
- AWS Support: [Contact info]
- Database Admin: [Contact info]
- KMS Key Admin: [Contact info]

---

## Post-Migration Verification

### Day 1 Checks
- [ ] All endpoints responding
- [ ] No decryption errors in logs
- [ ] Case creation working
- [ ] Case updates working
- [ ] Exports generating correctly
- [ ] Reports generating correctly
- [ ] DEK cache hit rate > 95%
- [ ] KMS API calls reasonable

### Week 1 Checks
- [ ] Review all encryption logs
- [ ] Check KMS costs
- [ ] Verify no data corruption
- [ ] Test edge cases
- [ ] User feedback collected

### Month 1 Checks
- [ ] Performance metrics stable
- [ ] No data issues reported
- [ ] Cache functioning properly
- [ ] KMS usage as expected
- [ ] Plan old data migration (if needed)

---

## Optional: Migrate Existing Unencrypted Data

### WARNING: EXTREMELY RISKY - ONLY IF NECESSARY

If you need to encrypt existing unencrypted data:

1. **Create Migration Script:**
   ```python
   # migrate_existing_phi.py
   # Fetches unencrypted cases, encrypts them, updates database
   # INCLUDE: Dry-run mode, progress tracking, rollback capability
   ```

2. **Test Migration:**
   - Test on copy of production database
   - Verify all data decrypts correctly
   - Check performance impact
   - Document every step

3. **Execute Migration:**
   - Schedule long maintenance window (4-8 hours)
   - Take snapshot before starting
   - Run migration with monitoring
   - Verify each batch
   - Keep unencrypted backup for 90 days

**RECOMMENDATION:** Skip this. Let new cases be encrypted, old cases stay unencrypted. System handles both.

---

## KMS Considerations

### Cost Monitoring
- Each DEK decryption: 1 KMS API call
- Cache hit: 0 KMS API calls
- Expected: ~110 KMS calls on startup (cache warming)
- Expected daily: <50 KMS calls (cache misses/rotations)
- Cost: $0.03 per 10,000 requests (negligible)

### Key Rotation
- KMS automatically rotates master key annually
- User DEKs remain valid (envelope encryption)
- No action needed for key rotation

---

## Success Metrics

### Performance
- ✅ Decryption latency: <5ms (cached)
- ✅ DEK cache hit rate: >95%
- ✅ Page load time increase: <50ms
- ✅ Export generation time: <10% increase

### Reliability
- ✅ Zero data corruption incidents
- ✅ Zero decryption failures
- ✅ 100% uptime during migration
- ✅ All reports generating successfully

---

## Quick Reference: Line Numbers to Change

```
get_case.py:325               - Remove user_id == TEST_USER_ID
filter_cases.py:250-251       - Remove TEST_USER_ID check
get_cases_by_status.py:261    - Remove TEST_USER_ID check
group_cases.py:152,307        - Remove TEST_USER_ID checks (2 functions)
case_export.py:251            - Remove TEST_USER_ID check
get_case_images.py:291        - Remove TEST_USER_ID check
provider_payment_report.py:511,1072 - Remove TEST_USER_ID checks (2 functions)
create_case.py:85,114,128,60  - Remove TEST_USER_ID, always encrypt
update_case.py:249,258        - Remove TEST_USER_ID, always encrypt
```

---

## Support Resources

- **Encryption Implementation:** `utils/phi_encryption.py`
- **Cache Warming:** `main.py` lines 304-317
- **DEK Table:** `user_encryption_keys`
- **Testing:** Use `get_cache_stats()` to monitor cache
- **Logs:** Search for `[ENCRYPTION]` and `[DECRYPT]`

---

## Final Checklist Before Going Live

- [ ] All backups complete and tested
- [ ] All 9 files updated and tested
- [ ] DEKs generated for all users
- [ ] Monitoring in place
- [ ] Rollback plan documented
- [ ] Team briefed on changes
- [ ] Support team ready
- [ ] Maintenance window scheduled
- [ ] Stakeholders notified
- [ ] Coffee/energy drinks stocked ☕

---

**Document Version:** 1.0  
**Last Updated:** 2025-10-20  
**Author:** AI Assistant  
**Status:** Ready for production rollout planning

**REMEMBER:** When in doubt, go slower. Better to take 2 months rolling out gradually than to have 2 hours of production downtime! 🚀

