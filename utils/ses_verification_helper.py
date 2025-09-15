#!/usr/bin/env python3
"""
SES Verification Helper for User Signup
Handles automatic SES verification for new users with plus-tagged emails
"""

import boto3
import logging
from typing import Dict, Any
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)

def check_and_verify_email_for_ses(email_address: str, aws_region: str = "us-east-1") -> Dict[str, Any]:
    """
    Check if an email address is verified in SES, and if not, send verification email.
    This is specifically designed for user signup to handle plus-tagged emails.
    
    Args:
        email_address: Email address to check and potentially verify
        aws_region: AWS region for SES
        
    Returns:
        Dictionary with verification status and actions taken
    """
    try:
        ses_client = boto3.client('ses', region_name=aws_region)
        
        # Get all verified identities (includes both emails and domains)
        response = ses_client.list_identities()
        verified_identities = set(response['Identities'])
        
        # Check if email is directly verified
        if email_address in verified_identities:
            return {
                "success": True,
                "already_verified": True,
                "verification_sent": False,
                "message": f"Email {email_address} is already verified in SES"
            }
        
        # Check if the domain is verified (covers all emails at that domain)
        domain = email_address.split('@')[1] if '@' in email_address else ''
        if domain in verified_identities:
            return {
                "success": True,
                "already_verified": True,
                "verification_sent": False,
                "message": f"Domain {domain} is verified in SES, covers {email_address}"
            }
        
        # Email/domain not verified - send verification email
        logger.info(f"Email {email_address} not verified in SES, sending verification email")
        
        try:
            verify_response = ses_client.verify_email_identity(EmailAddress=email_address)
            
            return {
                "success": True,
                "already_verified": False,
                "verification_sent": True,
                "message": f"Verification email sent to {email_address}. User must click verification link to receive emails.",
                "request_id": verify_response['ResponseMetadata']['RequestId']
            }
            
        except ClientError as verify_error:
            error_code = verify_error.response['Error']['Code']
            error_message = verify_error.response['Error']['Message']
            
            return {
                "success": False,
                "already_verified": False,
                "verification_sent": False,
                "message": f"Failed to send verification email to {email_address}: {error_message}",
                "error_code": error_code
            }
        
    except Exception as e:
        logger.error(f"Error in check_and_verify_email_for_ses for {email_address}: {str(e)}")
        return {
            "success": False,
            "already_verified": False,
            "verification_sent": False,
            "message": f"Error checking SES verification status: {str(e)}"
        }

def should_verify_email_for_ses(email_address: str) -> bool:
    """
    Determine if an email address needs SES verification.
    Currently focuses on plus-tagged emails, but could be expanded.
    
    Args:
        email_address: Email address to check
        
    Returns:
        True if email should be verified, False otherwise
    """
    if not email_address or '@' not in email_address:
        return False
    
    # Check if email contains plus sign (these need individual verification)
    if '+' in email_address:
        return True
    
    # Could add other criteria here in the future
    # For example: specific domains that aren't verified
    
    return False

def get_verification_instructions_for_user(email_address: str) -> str:
    """
    Generate user-friendly instructions for email verification
    
    Args:
        email_address: Email address that needs verification
        
    Returns:
        String with instructions for the user
    """
    return f"""
IMPORTANT: Email Verification Required

We've sent a verification email to: {email_address}

To receive emails from SurgiCase (including reports and notifications):
1. Check your email inbox AND spam folder
2. Look for an email from "Amazon Web Services" 
3. Click the verification link in that email
4. That's it! You'll then receive all SurgiCase emails normally.

This is a one-time verification required for email addresses with "+" signs.

If you don't see the verification email, please check your spam folder or contact support.
"""
