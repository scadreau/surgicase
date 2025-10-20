# Scheduler Resilience Improvements

**Created:** 2025-10-20  
**Author:** Scott Cadreau

## Overview

This document describes the resilience improvements implemented to handle AWS service outages and ensure critical scheduled jobs complete successfully even during infrastructure issues.

## Problem Statement

On October 20, 2025 at 08:12:40 UTC, AWS Secrets Manager experienced an internal service error (`InternalServiceError: Dependency exception`) that caused:
- 8 out of 9 secrets to fail during scheduled cache warming
- Critical scheduled jobs (provider payment reports) to fail
- Reports not being sent via email, resulting in a 4-hour delayed discovery

## Implemented Solutions

### 1. Graceful Degradation for Secrets Manager

**File:** `utils/secrets_manager.py`

**What Changed:**
- Modified `get_secret()` method to support stale cache fallback
- When AWS Secrets Manager errors occur (InternalServiceError, ServiceUnavailable, ThrottlingException), the system now:
  - Uses cached secrets even if they've expired (stale cache)
  - Logs warnings with cache age information
  - Continues operations without interruption
  - Only fails if no cache exists at all

**Code Enhancement:**
```python
def get_secret(self, secret_name: str, cache_ttl: int = 3600, allow_stale: bool = True):
    # ... check fresh cache first ...
    
    try:
        # Fetch from AWS
        response = self._client.get_secret_value(SecretId=secret_name)
        # ...
    except ClientError as e:
        error_code = e.response['Error']['Code']
        
        # Use stale cache for AWS service errors
        if allow_stale and has_stale_cache and error_code in ['InternalServiceError', 'ServiceUnavailable', 'ThrottlingException']:
            logger.warning(f"⚠️ AWS error - using stale cache (age: {cache_age:.0f}s)")
            return self._cache[cache_key]
```

**Benefits:**
- Jobs continue running during AWS outages
- No interruption to critical business operations
- Automatic recovery when AWS services restore

### 2. Job Failure Email Notifications

**File:** `utils/job_failure_notifier.py` (NEW)

**What It Does:**
- Sends immediate email alerts when critical scheduled jobs fail
- Provides detailed failure information including:
  - Job name and timestamp
  - Error messages and full tracebacks
  - Job statistics and context
  - Recommended troubleshooting actions
- Two notification types:
  1. **Critical Failures** - Job completely failed
  2. **Partial Failures** - Job completed with warnings

**Email Format:**
- Professional HTML-formatted emails with color-coded alerts
- Plain text fallback for email clients
- Detailed error context and troubleshooting steps
- Full exception tracebacks for debugging

**Functions:**
- `send_job_failure_notification()` - For complete job failures
- `send_job_partial_failure_notification()` - For partial/warning conditions

### 3. Enhanced Scheduler Error Handling

**File:** `utils/scheduler.py`

**What Changed:**

#### Weekly Provider Payment Report
- Added comprehensive error handling with specific exception types
- Sends email notifications on:
  - HTTP errors (non-200 status codes)
  - Timeout errors (>5 minutes)
  - Connection errors (API server down)
  - Any unexpected errors
- Includes error context in notifications

#### Weekly Provider Payment Summary Report
- Same improvements as payment report
- Separate notifications for tracking

#### Secrets Warming Job
- Now sends alerts when >50% of secrets fail to refresh
- Includes list of failed secrets in notification
- Clearly indicates stale cache is being used
- Differentiates between partial and complete failures

**Example Notification Logic:**
```python
except requests.exceptions.Timeout as e:
    error_msg = "Provider payment report timed out (>5 minutes)"
    logger.error(f"❌ {error_msg}")
    
    from utils.job_failure_notifier import send_job_failure_notification
    send_job_failure_notification(
        job_name="Weekly Provider Payment Report",
        error_message=error_msg,
        exception=e
    )
```

## Configuration Required

### Step 1: Configure Notification Recipients

Add the following key to your `surgicase/main` secret in AWS Secrets Manager:

```json
{
  "job_failure_recipients": "admin@example.com,ops@example.com"
}
```

**Multiple Recipients:** Use comma-separated email addresses

**Fallback:** If `job_failure_recipients` is not set, the system falls back to `admin_email` key

### Step 2: Test the Notification System

Run this command to test email notifications:

```bash
python3 -c "
from utils.job_failure_notifier import send_job_failure_notification
send_job_failure_notification(
    job_name='Test Job',
    error_message='This is a test notification',
    job_details={'Test': 'Configuration'}
)
"
```

You should receive an email with subject: **🚨 CRITICAL: Scheduled Job Failed - Test Job**

### Step 3: Verify in Production

The next time a scheduled job runs, check logs for:
- `✅ Secrets warming completed` - All secrets refreshed successfully
- `⚠️ AWS Secrets Manager error - using stale cache` - Graceful degradation active
- `✅ Job failure notification sent successfully` - Alert system working

## Jobs Covered

The following scheduled jobs now have enhanced error handling and email notifications:

### Critical Business Operations (Leader Server Only)
1. ✅ **Weekly Provider Payment Report** (Monday 09:00 UTC)
2. ✅ **Weekly Provider Payment Summary Report** (Monday 09:15 UTC)
3. ⚠️ **Weekly Individual Provider Reports** (Monday 10:00 UTC) - Not yet updated
4. ⚠️ **Weekly Referral Report** (Monday 09:30 UTC) - Not yet updated
5. ⚠️ **Weekly NPI Update** (Tuesday 08:00 UTC) - Not yet updated

### Maintenance Tasks (All Servers)
1. ✅ **Secrets Cache Warming** (Every 30 minutes)
2. ⚠️ **Database Backup** (Daily 08:00 UTC) - Not yet updated
3. ⚠️ **Pool Cleanup/Stats** - Not yet updated

**Legend:**
- ✅ Enhanced with failure notifications
- ⚠️ Has basic error handling, notifications not yet added

## Testing Performed

### 1. Manual Job Execution
```bash
# Successfully ran missed jobs from Oct 20, 2025
python3 -c "from utils.scheduler import run_provider_payment_report_now; run_provider_payment_report_now()"
# ✅ Success - 46,015 bytes (45KB PDF)

python3 -c "from utils.scheduler import run_provider_payment_summary_report_now; run_provider_payment_summary_report_now()"
# ✅ Success - 7,374 bytes (7.2KB PDF)
```

### 2. Code Quality
- ✅ All Python linter checks passed
- ✅ No syntax errors
- ✅ Type hints maintained
- ✅ Logging standards followed

## How It Prevents Future Issues

### Scenario 1: AWS Secrets Manager Outage
**Before:** Jobs fail immediately, no secrets available, no reports sent
**After:** 
- Stale cached secrets continue to work
- Jobs complete successfully
- If >50% secrets fail, email alert sent
- Business operations continue uninterrupted

### Scenario 2: Job Execution Failure
**Before:** Job fails silently, discovered hours later when reports missing
**After:**
- Immediate email notification sent
- Detailed error context provided
- Administrator can respond within minutes
- Can manually re-run jobs if needed

### Scenario 3: API Server Down
**Before:** Connection errors logged, no notification
**After:**
- Email notification with "Check if FastAPI server is running"
- Clear action items provided
- Full exception traceback for debugging

## Monitoring and Alerts

### Log Messages to Watch For

**Success:**
```
✅ Secrets warming completed: 9 secrets refreshed in 1.23s
✅ Weekly provider payment report generated successfully
```

**Graceful Degradation (Warning):**
```
⚠️ AWS Secrets Manager error (InternalServiceError) for surgicase/main - using stale cache (age: 3720s)
⚠️ Secrets warming partial: 1/9 secrets refreshed
```

**Critical Failures (Error):**
```
❌ Provider payment report failed with HTTP status 500
✅ Job failure notification sent successfully for Weekly Provider Payment Report
```

### Email Alerts

You'll receive emails for:
1. **Complete job failures** - Red header with 🚨
2. **Partial failures (>50% error rate)** - Orange header with ⚠️
3. **High secrets warming failure rate** - When AWS is having issues

## Benefits

### Immediate
- ✅ No more silent job failures
- ✅ Instant email notifications
- ✅ Jobs continue during AWS outages
- ✅ Detailed error context for troubleshooting

### Long-term
- 📊 Better visibility into system health
- 🔧 Faster incident response
- 💪 More resilient infrastructure
- 📈 Improved uptime for business operations

## Next Steps (Recommended)

### Phase 2 - Extend to All Critical Jobs
1. Add notifications to remaining report jobs:
   - Weekly Individual Provider Reports
   - Weekly Referral Report
   - Weekly NPI Update
2. Add notifications to maintenance jobs:
   - Database Backup
   - Pool Management

### Phase 3 - Enhanced Monitoring
1. Create CloudWatch dashboard for job metrics
2. Add Slack integration for alerts
3. Implement retry logic with exponential backoff
4. Create job execution history dashboard

### Phase 4 - Advanced Features
1. Circuit breaker pattern for dependent services
2. Health check endpoint showing job status
3. Manual job retry UI in admin panel
4. Automatic recovery procedures

## Troubleshooting

### Email Notifications Not Working

**Check 1:** Verify secret configuration
```bash
aws secretsmanager get-secret-value --secret-id surgicase/main --query SecretString --output text | jq .job_failure_recipients
```

**Check 2:** Test email service
```python
from utils.email_service import send_email
result = send_email(
    to_addresses="your@email.com",
    subject="Test",
    body="Testing email service"
)
print(result)
```

**Check 3:** Check SES sending limits
- Verify SES is not in sandbox mode
- Check for bounced emails
- Verify sender email is verified

### Stale Cache Warnings Persisting

If you see repeated stale cache warnings for >1 hour:
1. Check AWS Service Health Dashboard
2. Verify IAM permissions for Secrets Manager
3. Check network connectivity to AWS endpoints
4. Review CloudTrail logs for API errors

### Jobs Still Failing Despite Improvements

1. Check if stale cache exists (first-time failures will still occur)
2. Verify FastAPI server is running
3. Check database connectivity
4. Review full error logs for root cause

## Rollback Plan

If issues arise, revert to previous version:

```bash
# Revert secrets_manager.py
git checkout HEAD~1 utils/secrets_manager.py

# Revert scheduler.py
git checkout HEAD~1 utils/scheduler.py

# Remove new notification system
rm utils/job_failure_notifier.py

# Restart application
sudo systemctl restart surgicase
```

## Contact

For questions or issues with these improvements:
- Check application logs: `/var/log/surgicase/`
- Review CloudWatch Logs
- Contact: Scott Cadreau

---

**Document Version:** 1.0  
**Last Updated:** 2025-10-20  
**Status:** ✅ Deployed to Production

