# Resilience Improvements - Quick Reference Card

**Date:** October 20, 2025  
**Status:** ✅ Production Ready

---

## 🎯 What Changed

AWS Secrets Manager outage on Oct 20 caused jobs to fail silently. Now:
- ✅ **System continues** during AWS outages (uses stale cache)
- ✅ **Email alerts** sent immediately when jobs fail
- ✅ **Detailed errors** for faster troubleshooting

---

## 📧 Who Gets Notified

**Current Recipients:**
- scadreau@metoraymedical.com
- nick@vicisecurity.com

**To Change Recipients:**
```bash
# Add to AWS Secrets Manager: surgicase/main
aws secretsmanager update-secret --secret-id surgicase/main \
  --secret-string '{"job_failure_recipients":"ops@example.com,admin@example.com",...}'
```

---

## 🧪 Test the System

```bash
# Run all verification tests
python3 test_resilience.py

# Send a test email notification
python3 test_resilience.py --send-test-email
```

---

## 📊 What to Monitor

### Good (Normal Operations)
```
✅ Secrets warming completed: 9 secrets refreshed
✅ Weekly provider payment report generated successfully
```

### Warning (AWS Issues - System Still Working)
```
⚠️ AWS Secrets Manager error - using stale cache (age: 1800s)
⚠️ Secrets warming partial: 1/9 secrets refreshed
📧 Email alert sent about high failure rate
```

### Critical (Job Failed - Email Sent)
```
❌ Provider payment report failed with HTTP status 500
✅ Job failure notification sent successfully
```

---

## 🚨 What Emails Look Like

### Critical Failure
- **Subject:** 🚨 CRITICAL: Scheduled Job Failed - [Job Name]
- **When:** Job completely failed to run
- **Action:** Check email for error details and follow recommended steps

### Partial Failure
- **Subject:** ⚠️ WARNING: Scheduled Job Partial Failure - [Job Name]
- **When:** Job completed but with warnings (e.g., >50% secrets failed)
- **Action:** Monitor the situation, may auto-recover

---

## 🔧 Manual Job Re-run

If a job fails and needs to be re-run manually:

```bash
cd /home/scadreau/surgicase

# Provider payment report
python3 -c "from utils.scheduler import run_provider_payment_report_now; run_provider_payment_report_now()"

# Provider payment summary
python3 -c "from utils.scheduler import run_provider_payment_summary_report_now; run_provider_payment_summary_report_now()"

# Individual provider reports
python3 -c "from utils.scheduler import run_individual_provider_reports_now; run_individual_provider_reports_now()"

# NPI update
python3 -c "from utils.scheduler import run_npi_update_now; run_npi_update_now()"

# Database backup
python3 -c "from utils.scheduler import run_backup_now; run_backup_now()"
```

---

## 📅 Next Scheduled Jobs

### This Week
- **Oct 21, 08:00 UTC** - NPI Update
- **Every 30 min** - Secrets Cache Warming ✅ Enhanced

### Next Week (Oct 28)
- **08:00 UTC** - Pending Payment Update
- **09:00 UTC** - Provider Payment Report ✅ Enhanced
- **09:15 UTC** - Provider Payment Summary ✅ Enhanced
- **09:30 UTC** - Referral Report
- **10:00 UTC** - Individual Provider Reports

---

## 🔍 Check Logs

```bash
# Recent scheduler activity
sudo journalctl -u surgicase -n 100 | grep -i scheduler

# Look for failures
sudo journalctl -u surgicase -n 500 | grep -E "❌|⚠️"

# Follow in real-time
sudo journalctl -u surgicase -f | grep -i "scheduler\|report"
```

---

## 📚 Full Documentation

- **Detailed Guide:** `RESILIENCE_IMPROVEMENTS.md`
- **Deployment Summary:** `DEPLOYMENT_SUMMARY.md`
- **This Card:** `QUICK_REFERENCE.md`

---

## ⚡ Emergency Contacts

**Issue?** Check logs first, then contact:
- Scott Cadreau (Implementation)

**Email not received?**
1. Check spam folder
2. Verify `DEV_EMAIL_ADDRESSES` in secrets
3. Test: `python3 test_resilience.py --send-test-email`

---

## ✅ Checklist for Next Monday

When the next scheduled jobs run (Oct 28):

- [ ] Check inbox for any failure notifications
- [ ] Review logs around 09:00 UTC for report generation
- [ ] Confirm reports received via email
- [ ] Verify no AWS service issues occurred
- [ ] If all good: improvements working as designed! 🎉

---

**Remember:** System will now alert you immediately if anything goes wrong. No more 4-hour delays! 🚀

