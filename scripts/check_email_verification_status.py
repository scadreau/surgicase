#!/usr/bin/env python3
"""
Check SES email verification status for users
"""

import sys
import os

# Add the project root to the Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

import pymysql.cursors
import boto3
import logging
from typing import List, Dict

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def get_all_plus_tagged_emails() -> List[Dict[str, str]]:
    """Get all users with plus-tagged email addresses"""
    try:
        from core.database import get_db_connection, close_db_connection
        
        conn = None
        conn = get_db_connection()
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            sql = """
                SELECT user_id, user_email, first_name, last_name 
                FROM user_profile 
                WHERE user_email LIKE '%+%' 
                AND active = 1
                AND user_email IS NOT NULL
                ORDER BY user_email
            """
            cursor.execute(sql)
            results = cursor.fetchall()
            return results
    except Exception as e:
        logger.error(f"Error fetching plus-tagged emails: {str(e)}")
        return []
    finally:
        if conn:
            close_db_connection(conn)

def check_specific_email(email_address: str) -> Dict[str, any]:
    """Check verification status for a specific email"""
    try:
        ses_client = boto3.client('ses', region_name='us-east-1')
        
        # Get all verified identities
        response = ses_client.list_identities()
        verified_identities = set(response['Identities'])
        
        # Check if email is directly verified
        if email_address in verified_identities:
            return {
                "email": email_address,
                "verified": True,
                "method": "direct_email"
            }
        
        # Check if domain is verified
        domain = email_address.split('@')[1] if '@' in email_address else ''
        if domain in verified_identities:
            return {
                "email": email_address,
                "verified": True,
                "method": "domain_verified",
                "domain": domain
            }
        
        return {
            "email": email_address,
            "verified": False,
            "method": "not_verified"
        }
        
    except Exception as e:
        return {
            "email": email_address,
            "verified": False,
            "method": "error",
            "error": str(e)
        }

def main():
    """Check verification status for all plus-tagged emails"""
    logger.info("🔍 Checking SES verification status for all plus-tagged emails...")
    
    # Get all plus-tagged emails
    users = get_all_plus_tagged_emails()
    
    if not users:
        logger.info("No plus-tagged email users found.")
        return
    
    logger.info(f"📧 Checking {len(users)} plus-tagged email addresses...")
    
    verified_count = 0
    unverified_count = 0
    
    verified_emails = []
    unverified_emails = []
    
    for user in users:
        email = user['user_email']
        name = f"{user['first_name']} {user['last_name']}".strip()
        
        status = check_specific_email(email)
        
        if status['verified']:
            verified_count += 1
            verified_emails.append({
                "email": email,
                "name": name,
                "method": status['method']
            })
        else:
            unverified_count += 1
            unverified_emails.append({
                "email": email,
                "name": name,
                "reason": status.get('error', 'Not verified')
            })
    
    # Summary
    logger.info(f"\n📊 Verification Status Summary:")
    logger.info(f"   ✅ Verified: {verified_count}")
    logger.info(f"   ❌ Unverified: {unverified_count}")
    logger.info(f"   📈 Verification Rate: {(verified_count/len(users)*100):.1f}%")
    
    if verified_emails:
        logger.info(f"\n✅ VERIFIED EMAILS ({verified_count}):")
        for item in verified_emails:
            method_text = "🌐 Domain" if item['method'] == 'domain_verified' else "📧 Direct"
            logger.info(f"   {method_text} - {item['email']} ({item['name']})")
    
    if unverified_emails:
        logger.info(f"\n❌ UNVERIFIED EMAILS ({unverified_count}):")
        for item in unverified_emails:
            logger.info(f"   - {item['email']} ({item['name']})")
        
        logger.info(f"\n💡 To verify unverified emails, run:")
        logger.info(f"   python3 scripts/bulk_verify_ses_emails.py")

if __name__ == "__main__":
    main()
