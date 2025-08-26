#!/usr/bin/env python3
# Created: 2025-08-26 20:15:00
# Last Modified: 2025-08-26 20:16:22
# Author: Scott Cadreau

"""
Script to add referral report email templates to AWS Secrets Manager.
This adds the missing referral_report templates to the existing surgicase/email_templates secret.

Usage:
    python add_referral_email_templates.py [--region us-east-1] [--dry-run]
"""

import boto3
import json
import logging
import argparse
import sys
from typing import Dict, Any

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Referral report email templates
REFERRAL_REPORT_TEMPLATES = {
    "referral_report": {
        "weekly": {
            "subject": "Weekly Referral Report - {creation_date}",
            "body": """Dear {recipient_name},

Please find attached the weekly Referral Report for your review. This report provides a comprehensive analysis of our referral network, showing which users were referred by whom along with their payment categories and totals.

Report Summary:
• Report Date: {creation_date}
• Total Referral Users: {total_referral_users}
• Total Referred Users: {total_referred_users}
• Total Cases: {total_cases}
• Total Amount: ${total_amount}

IMPORTANT SECURITY INFORMATION:
The attached PDF report is password-protected for security. To open the report, use the following password:
Password: {password}

Please keep this password secure and do not share it with others. The report contains confidential business and financial information.

Report Structure:
This report is organized by referral user, with each referral user getting their own page showing:
- All users they referred
- Payment categories for each referred user
- Case counts and payment amounts
- Subtotals per referral user

This analysis helps track the effectiveness of our referral network and understand user acquisition patterns.

If you have any questions about this report or need assistance accessing the document, please contact our office.

Best regards,
SurgiCase Reporting System

----
This is an automated weekly report from the SurgiCase system.
Report Type: {report_type}"""
        },
        "on_demand": {
            "subject": "Referral Report - Generated {creation_date}",
            "body": """Dear {recipient_name},

Please find attached the Referral Report that you requested on {creation_date}. This report provides a comprehensive analysis of our referral network, showing which users were referred by whom along with their payment categories and totals.

Report Summary:
• Report Date: {creation_date}
• Total Referral Users: {total_referral_users}
• Total Referred Users: {total_referred_users}
• Total Cases: {total_cases}
• Total Amount: ${total_amount}

IMPORTANT SECURITY INFORMATION:
The attached PDF report is password-protected for security. To open the report, use the following password:
Password: {password}

Please keep this password secure and do not share it with others. The report contains confidential business and financial information.

Report Structure:
This report is organized by referral user, with each referral user getting their own page showing:
- All users they referred
- Payment categories for each referred user
- Case counts and payment amounts
- Subtotals per referral user

This analysis helps track the effectiveness of our referral network and understand user acquisition patterns.

If you have any questions about this report or need assistance accessing the document, please contact our office.

Best regards,
SurgiCase Reporting System

----
This is an on-demand report from the SurgiCase system.
Report Type: {report_type}"""
        }
    }
}

def get_current_templates(region: str) -> Dict[str, Any]:
    """
    Fetch current email templates from AWS Secrets Manager
    
    Args:
        region: AWS region where the secret is stored
        
    Returns:
        Dictionary containing current email templates
    """
    try:
        client = boto3.client('secretsmanager', region_name=region)
        response = client.get_secret_value(SecretId='surgicase/email_templates')
        templates = json.loads(response['SecretString'])
        logger.info("Successfully retrieved current email templates from AWS Secrets Manager")
        return templates
    except Exception as e:
        logger.error(f"Error retrieving current email templates: {str(e)}")
        return {"email_templates": {}}

def update_templates(region: str, dry_run: bool = False) -> bool:
    """
    Update email templates in AWS Secrets Manager with referral report templates
    
    Args:
        region: AWS region where the secret is stored
        dry_run: If True, only show what would be done without making changes
        
    Returns:
        True if successful, False otherwise
    """
    try:
        # Get current templates
        current_templates = get_current_templates(region)
        
        # Check if referral_report templates already exist
        if "referral_report" in current_templates.get("email_templates", {}):
            logger.info("Referral report templates already exist in AWS Secrets Manager")
            return True
        
        # Add referral report templates to current templates
        if "email_templates" not in current_templates:
            current_templates["email_templates"] = {}
        
        current_templates["email_templates"].update(REFERRAL_REPORT_TEMPLATES)
        
        if dry_run:
            logger.info("DRY RUN: Would add the following referral report templates:")
            logger.info(json.dumps(REFERRAL_REPORT_TEMPLATES, indent=2))
            return True
        
        # Update the secret in AWS Secrets Manager
        client = boto3.client('secretsmanager', region_name=region)
        client.update_secret(
            SecretId='surgicase/email_templates',
            SecretString=json.dumps(current_templates, indent=2)
        )
        
        logger.info("Successfully added referral report email templates to AWS Secrets Manager")
        return True
        
    except Exception as e:
        logger.error(f"Error updating email templates: {str(e)}")
        return False

def main():
    """Main function to handle command line arguments and execute the update"""
    parser = argparse.ArgumentParser(
        description="Add referral report email templates to AWS Secrets Manager"
    )
    parser.add_argument(
        '--region', 
        default='us-east-1',
        help='AWS region where the secret is stored (default: us-east-1)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be done without making changes'
    )
    
    args = parser.parse_args()
    
    logger.info(f"Starting referral report email template setup for region: {args.region}")
    if args.dry_run:
        logger.info("DRY RUN MODE: No changes will be made")
    
    try:
        success = update_templates(args.region, args.dry_run)
        
        if success:
            if args.dry_run:
                logger.info("DRY RUN completed successfully")
            else:
                logger.info("Referral report email templates setup completed successfully!")
                logger.info("The referral report endpoint is now ready to send emails.")
            sys.exit(0)
        else:
            logger.error("Failed to setup referral report email templates")
            sys.exit(1)
            
    except Exception as e:
        logger.error(f"Unexpected error during setup: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()
