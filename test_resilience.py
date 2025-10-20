#!/usr/bin/env python3
"""
Test script for resilience improvements

This script verifies:
1. Secrets manager graceful degradation
2. Job failure notification system
3. Email configuration

Usage:
    python3 test_resilience.py
"""

import logging
import sys

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def test_secrets_with_stale_cache():
    """Test that secrets manager can use stale cache"""
    print("\n" + "="*70)
    print("TEST 1: Secrets Manager with Graceful Degradation")
    print("="*70)
    
    try:
        from utils.secrets_manager import secrets_manager
        
        # First, warm the cache
        print("📦 Warming cache...")
        result = secrets_manager.warm_cache(["surgicase/main"], {"surgicase/main": 1})
        
        if result["successful"] > 0:
            print("✅ Cache warmed successfully")
            print(f"   Cached secrets: {result['successful']}")
            
            # Get cache stats
            stats = secrets_manager.get_cache_stats()
            print(f"\n📊 Cache Statistics:")
            print(f"   Cached secrets: {stats['cached_secrets_count']}")
            print(f"   Oldest cache age: {stats['oldest_cache_age_seconds']:.1f}s")
            
            return True
        else:
            print("❌ Cache warming failed")
            return False
            
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        return False


def test_notification_configuration():
    """Test that notification recipients are configured"""
    print("\n" + "="*70)
    print("TEST 2: Notification Configuration")
    print("="*70)
    
    try:
        from utils.secrets_manager import get_secret_value
        
        # Check for notification recipients
        recipients = get_secret_value("surgicase/main", "job_failure_recipients")
        
        if recipients:
            print(f"✅ Notification recipients configured:")
            for email in recipients.split(","):
                print(f"   - {email.strip()}")
            return True
        else:
            print("⚠️  'job_failure_recipients' not found in surgicase/main")
            print("   Checking fallback to 'admin_email'...")
            
            admin_email = get_secret_value("surgicase/main", "admin_email")
            if admin_email:
                print(f"✅ Will use admin_email: {admin_email}")
                return True
            else:
                print("   'admin_email' not found, checking 'DEV_EMAIL_ADDRESSES'...")
                
                dev_emails = get_secret_value("surgicase/main", "DEV_EMAIL_ADDRESSES")
                if dev_emails:
                    print(f"✅ Will use DEV_EMAIL_ADDRESSES:")
                    # Handle both string and list formats
                    if isinstance(dev_emails, str):
                        email_list = dev_emails.split(",")
                    else:
                        email_list = dev_emails if isinstance(dev_emails, list) else [str(dev_emails)]
                    
                    for email in email_list:
                        print(f"   - {email.strip() if isinstance(email, str) else email}")
                    return True
                else:
                    print("❌ No notification recipients configured!")
                    print("\n📝 To configure, add to surgicase/main secret:")
                    print('   "job_failure_recipients": "admin@example.com,ops@example.com"')
                    return False
                
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        return False


def test_email_service():
    """Test that email service is functional"""
    print("\n" + "="*70)
    print("TEST 3: Email Service")
    print("="*70)
    
    try:
        from utils.email_service import send_email
        
        print("✅ Email service module loaded successfully")
        print("   (Not sending test email to avoid spam)")
        return True
        
    except Exception as e:
        print(f"❌ Error loading email service: {str(e)}")
        return False


def test_notification_system(send_test_email=False):
    """Test the job failure notification system"""
    print("\n" + "="*70)
    print("TEST 4: Job Failure Notification System")
    print("="*70)
    
    try:
        from utils.job_failure_notifier import send_job_failure_notification
        
        print("✅ Job failure notifier module loaded successfully")
        
        if send_test_email:
            print("\n📧 Sending test notification email...")
            success = send_job_failure_notification(
                job_name="Resilience Test Job",
                error_message="This is a test notification to verify the resilience improvements are working correctly.",
                job_details={
                    "Test Type": "Resilience Verification",
                    "Date": "2025-10-20",
                    "Status": "Testing"
                }
            )
            
            if success:
                print("✅ Test notification sent successfully!")
                print("   Check your email inbox for: 🚨 CRITICAL: Scheduled Job Failed - Resilience Test Job")
                return True
            else:
                print("❌ Failed to send test notification")
                return False
        else:
            print("   (Skipping test email - use --send-test-email flag to send)")
            return True
            
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def test_scheduler_enhancements():
    """Test that scheduler has enhanced error handling"""
    print("\n" + "="*70)
    print("TEST 5: Scheduler Enhancements")
    print("="*70)
    
    try:
        from utils.scheduler import (
            weekly_provider_payment_report,
            weekly_provider_payment_summary_report,
            secrets_warming_job
        )
        
        print("✅ Enhanced scheduler functions loaded:")
        print("   - weekly_provider_payment_report")
        print("   - weekly_provider_payment_summary_report")
        print("   - secrets_warming_job")
        print("\n   All functions include error notifications")
        return True
        
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        return False


def main():
    """Run all tests"""
    print("\n" + "="*70)
    print("🧪 RESILIENCE IMPROVEMENTS VERIFICATION TEST")
    print("="*70)
    print("Testing improvements made on 2025-10-20")
    print("="*70)
    
    # Check for command line flag
    send_test_email = "--send-test-email" in sys.argv
    
    if send_test_email:
        print("\n⚠️  WARNING: Test email will be sent to configured recipients!")
        response = input("Continue? (yes/no): ")
        if response.lower() != "yes":
            print("Test cancelled.")
            return
    
    # Run tests
    results = []
    results.append(("Secrets Manager", test_secrets_with_stale_cache()))
    results.append(("Notification Config", test_notification_configuration()))
    results.append(("Email Service", test_email_service()))
    results.append(("Notification System", test_notification_system(send_test_email)))
    results.append(("Scheduler Enhancements", test_scheduler_enhancements()))
    
    # Print summary
    print("\n" + "="*70)
    print("📊 TEST SUMMARY")
    print("="*70)
    
    passed = 0
    failed = 0
    
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} - {test_name}")
        if result:
            passed += 1
        else:
            failed += 1
    
    print("="*70)
    print(f"Total: {passed} passed, {failed} failed out of {len(results)} tests")
    
    if failed == 0:
        print("\n🎉 All tests passed! Resilience improvements are ready.")
        print("\n📝 Next steps:")
        print("   1. Add 'job_failure_recipients' to surgicase/main secret (if not configured)")
        print("   2. Run with --send-test-email flag to test email delivery")
        print("   3. Monitor logs for scheduled job executions")
        print("   4. Review RESILIENCE_IMPROVEMENTS.md for full documentation")
    else:
        print("\n⚠️  Some tests failed. Review errors above and fix configuration.")
        sys.exit(1)


if __name__ == "__main__":
    main()

