#!/usr/bin/env python3
"""
Bulk verify email addresses in AWS SES for users with +tag emails
"""

import sys
import os

# Add the project root to the Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import pymysql.cursors
import boto3
import logging
from typing import List, Dict
from core.database import get_db_connection, close_db_connection

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def get_plus_tagged_emails() -> List[Dict[str, str]]:
    """
    Get all active users with plus-tagged email addresses from the database
    
    Returns:
        List of dictionaries with user_id, user_email, first_name, last_name
    """
    conn = None
    try:
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
            logger.info(f"Found {len(results)} users with plus-tagged email addresses")
            return results
    except Exception as e:
        logger.error(f"Error fetching plus-tagged emails: {str(e)}")
        return []
    finally:
        if conn:
            close_db_connection(conn)

def check_ses_verification_status(email_addresses: List[str], aws_region: str = "us-east-1") -> Dict[str, bool]:
    """
    Check which email addresses are already verified in SES
    
    Args:
        email_addresses: List of email addresses to check
        aws_region: AWS region for SES
        
    Returns:
        Dictionary mapping email addresses to verification status (True = verified)
    """
    try:
        ses_client = boto3.client('ses', region_name=aws_region)
        
        # Get all verified identities (includes both emails and domains)
        response = ses_client.list_identities()
        verified_identities = set(response['Identities'])
        
        verification_status = {}
        
        for email in email_addresses:
            # Check if email is directly verified
            if email in verified_identities:
                verification_status[email] = True
            else:
                # Check if the domain is verified
                domain = email.split('@')[1] if '@' in email else ''
                if domain in verified_identities:
                    verification_status[email] = True
                else:
                    verification_status[email] = False
        
        return verification_status
        
    except Exception as e:
        logger.error(f"Error checking SES verification status: {str(e)}")
        return {}

def bulk_verify_emails(email_addresses: List[str], aws_region: str = "us-east-1") -> Dict[str, Dict]:
    """
    Send verification emails for multiple addresses
    
    Args:
        email_addresses: List of email addresses to verify
        aws_region: AWS region for SES
        
    Returns:
        Dictionary with results for each email address
    """
    try:
        ses_client = boto3.client('ses', region_name=aws_region)
        results = {}
        
        for email in email_addresses:
            try:
                response = ses_client.verify_email_identity(EmailAddress=email)
                results[email] = {
                    "success": True,
                    "message": "Verification email sent successfully",
                    "request_id": response['ResponseMetadata']['RequestId']
                }
                logger.info(f"✅ Verification email sent to: {email}")
                
            except Exception as e:
                results[email] = {
                    "success": False,
                    "message": f"Failed to send verification email: {str(e)}"
                }
                logger.error(f"❌ Failed to send verification email to {email}: {str(e)}")
        
        return results
        
    except Exception as e:
        logger.error(f"Error in bulk verification: {str(e)}")
        return {}

def main():
    """Main function to run the bulk verification process"""
    logger.info("🚀 Starting bulk email verification process...")
    
    # Get all plus-tagged emails from database
    users = get_plus_tagged_emails()
    
    if not users:
        logger.info("No users with plus-tagged emails found.")
        return
    
    # Extract email addresses
    email_addresses = [user['user_email'] for user in users if user['user_email']]
    
    logger.info(f"📧 Found {len(email_addresses)} plus-tagged email addresses:")
    for user in users:
        logger.info(f"   - {user['user_email']} ({user['first_name']} {user['last_name']})")
    
    # Check current verification status
    logger.info("\n🔍 Checking current SES verification status...")
    verification_status = check_ses_verification_status(email_addresses)
    
    # Separate verified from unverified
    verified_emails = [email for email, is_verified in verification_status.items() if is_verified]
    unverified_emails = [email for email, is_verified in verification_status.items() if not is_verified]
    
    logger.info(f"\n📊 Verification Status Summary:")
    logger.info(f"   ✅ Already verified: {len(verified_emails)}")
    logger.info(f"   ❌ Need verification: {len(unverified_emails)}")
    
    if verified_emails:
        logger.info(f"\n✅ Already verified emails:")
        for email in verified_emails:
            logger.info(f"   - {email}")
    
    if unverified_emails:
        logger.info(f"\n❌ Emails needing verification:")
        for email in unverified_emails:
            logger.info(f"   - {email}")
        
        # Ask for confirmation
        print(f"\n🤔 Do you want to send verification emails to {len(unverified_emails)} addresses? (y/N): ", end="")
        response = input().strip().lower()
        
        if response in ['y', 'yes']:
            logger.info(f"\n📤 Sending verification emails to {len(unverified_emails)} addresses...")
            results = bulk_verify_emails(unverified_emails)
            
            # Summary
            successful = sum(1 for result in results.values() if result['success'])
            failed = len(results) - successful
            
            logger.info(f"\n📈 Bulk Verification Results:")
            logger.info(f"   ✅ Successfully sent: {successful}")
            logger.info(f"   ❌ Failed to send: {failed}")
            
            if failed > 0:
                logger.info(f"\n❌ Failed emails:")
                for email, result in results.items():
                    if not result['success']:
                        logger.info(f"   - {email}: {result['message']}")
            
            logger.info(f"\n📬 Next Steps:")
            logger.info(f"   1. Ask users to check their email (including spam folders)")
            logger.info(f"   2. Users need to click the verification link from AWS")
            logger.info(f"   3. After verification, individual provider reports should work")
            logger.info(f"   4. You can re-run this script to check verification status")
            
        else:
            logger.info("❌ Verification cancelled by user.")
    else:
        logger.info("🎉 All plus-tagged emails are already verified!")

if __name__ == "__main__":
    main()
