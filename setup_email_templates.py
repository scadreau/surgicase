#!/usr/bin/env python3
# Created: 2025-08-08 02:41:28
# Last Modified: 2025-08-19 00:02:25
# Author: Scott Cadreau

"""
One-time setup script to check and add missing email templates to AWS Secrets Manager.
This script can be run once and then discarded.

Usage:
    python setup_email_templates.py [--region us-east-1] [--dry-run]
"""

import boto3
import json
import logging
import argparse
import sys
from typing import Dict, Any, List

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Email template definitions
EMAIL_TEMPLATES = {
    "provider_payment_report": {
        "weekly": {
            "subject": "Weekly Provider Payment Report for week of {report_date}",
            "body": """Hello {first_name},

Please find the attached Provider Payment Report for the week of {report_date}.

Report Summary:
• Total Providers: {total_providers}
• Total Cases: {total_cases}
• Total Amount: ${total_amount}

IMPORTANT SECURITY INFORMATION:
The attached PDF report is password-protected for security. To open the report, use the following password:
Password: {password}

Please keep this password secure and do not share it with others. The report contains confidential patient and financial information.

The report was created on {creation_date}.

If you have any questions about this report or need assistance accessing the document, please contact our office.

Thank you,
SurgiCase Automation System

----
This is an automated weekly report from the SurgiCase system.
Report filename: {filename}"""
        },
        "on_demand": {
            "subject": "Provider Payment Report - Generated {creation_date}",
            "body": """Hello {first_name},

Please find the attached Provider Payment Report that you requested on {creation_date}.

Report Summary:
• Total Providers: {total_providers}
• Total Cases: {total_cases}
• Total Amount: ${total_amount}

IMPORTANT SECURITY INFORMATION:
The attached PDF report is password-protected for security. To open the report, use the following password:
Password: {password}

Please keep this password secure and do not share it with others. The report contains confidential patient and financial information.

The report was created on {creation_date}.

If you have any questions about this report or need assistance accessing the document, please contact our office.

Thank you,
SurgiCase Automation System

----
This is an on-demand report from the SurgiCase system.
Report filename: {filename}"""
        }
    },
    "provider_payment_summary_report": {
        "weekly": {
            "subject": "Weekly Provider Payment Summary Report - {creation_date}",
            "body": """Dear Team,

Please find attached the weekly Provider Payment Summary Report for your review. This summary report shows provider payment totals grouped by state, providing a high-level overview of pending payments.

Report Details:
• Report Date: {creation_date}
• Report Period: {report_date}
• Total States: {total_states}
• Total Providers: {total_providers}  
• Total Amount: ${total_amount}

This summary report groups providers by state with each state on a separate page. Within each state, providers are listed alphabetically showing:
- Provider Name
- NPI Number
- Total Payment Amount

The detailed individual case information is available in the standard Provider Payment Report.

If you have any questions about this summary report, please contact the operations team.

Best regards,
SurgiCase Reporting System

----
This is an automated weekly report from the SurgiCase system.
Report filename: {filename}"""
        },
        "on_demand": {
            "subject": "Provider Payment Summary Report - {creation_date}",
            "body": """Dear Team,

Please find attached the Provider Payment Summary Report for your review. This summary report shows provider payment totals grouped by state, providing a high-level overview of pending payments.

Report Details:
• Report Date: {creation_date}
• Report Period: {report_date}
• Total States: {total_states}
• Total Providers: {total_providers}
• Total Amount: ${total_amount}

This summary report groups providers by state with each state on a separate page. Within each state, providers are listed alphabetically showing:
- Provider Name
- NPI Number  
- Total Payment Amount

The detailed individual case information is available in the standard Provider Payment Report.

If you have any questions about this summary report, please contact the operations team.

Best regards,
SurgiCase Reporting System

----
This is an on-demand report from the SurgiCase system.
Report filename: {filename}"""
        }
    },
    "individual_provider_payment_report": {
        "weekly": {
            "subject": "Your Personal Payment Report - {creation_date}",
            "body": """Dear {provider_name},

Please find your personal payment report attached for review. This report contains your cases with case status "Pending Payment" and is password-protected for your security.

Report Details:
• Report Date: {creation_date}
• Provider: {provider_name}
• NPI: {npi}
• Total Cases: {case_count}
• Total Amount: {total_amount}

IMPORTANT SECURITY INFORMATION:
Your report is password-protected. To open the PDF, use the following password:
Password: {password}

Please keep this password secure and do not share it with others. The report contains confidential patient and financial information.

If you have any questions about your payment report or need assistance accessing the document, please contact our office.

Best regards,
SurgiCase Team

----
This is an automated message from the SurgiCase system.
Report filename: {filename}
Generated on: {creation_date}"""
        },
        "on_demand": {
            "subject": "Your Personal Payment Report - {creation_date}",
            "body": """Dear {provider_name},

Please find your personal payment report attached for review. This report contains your cases with case status "Pending Payment" and is password-protected for your security.

Report Details:
• Report Date: {creation_date}
• Provider: {provider_name}
• NPI: {npi}
• Total Cases: {case_count}
• Total Amount: {total_amount}

IMPORTANT SECURITY INFORMATION:
Your report is password-protected. To open the PDF, use the following password:
Password: {password}

Please keep this password secure and do not share it with others. The report contains confidential patient and financial information.

If you have any questions about your payment report or need assistance accessing the document, please contact our office.

Best regards,
SurgiCase Team

----
This is an on-demand report from the SurgiCase system.
Report filename: {filename}
Generated on: {creation_date}"""
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
    except client.exceptions.ResourceNotFoundException:
        logger.warning("Email templates secret not found. Will create new secret.")
        return {"email_templates": {}}
    except Exception as e:
        logger.error(f"Error fetching email templates from Secrets Manager: {str(e)}")
        raise

def update_templates_in_secrets(templates: Dict[str, Any], region: str, dry_run: bool = False) -> bool:
    """
    Update email templates in AWS Secrets Manager
    
    Args:
        templates: Dictionary containing email templates to save
        region: AWS region where the secret is stored
        dry_run: If True, only show what would be done without making changes
        
    Returns:
        True if successful
    """
    try:
        if dry_run:
            logger.info("DRY RUN: Would update email templates in AWS Secrets Manager")
            logger.info(f"DRY RUN: Template structure: {json.dumps(templates, indent=2)}")
            return True
            
        client = boto3.client('secretsmanager', region_name=region)
        
        try:
            # Try to update existing secret
            client.update_secret(
                SecretId='surgicase/email_templates',
                SecretString=json.dumps(templates, indent=2)
            )
            logger.info("Successfully updated email templates in AWS Secrets Manager")
        except client.exceptions.ResourceNotFoundException:
            # Create new secret if it doesn't exist
            client.create_secret(
                Name='surgicase/email_templates',
                SecretString=json.dumps(templates, indent=2),
                Description='Email templates for SurgiCase application reports'
            )
            logger.info("Successfully created new email templates secret in AWS Secrets Manager")
            
        return True
        
    except Exception as e:
        logger.error(f"Error updating email templates in Secrets Manager: {str(e)}")
        raise

def check_missing_templates(current_templates: Dict[str, Any]) -> List[str]:
    """
    Check which templates are missing from the current configuration
    
    Args:
        current_templates: Current templates from AWS Secrets Manager
        
    Returns:
        List of missing template keys
    """
    missing = []
    email_templates = current_templates.get('email_templates', {})
    
    for template_key in EMAIL_TEMPLATES.keys():
        if template_key not in email_templates:
            missing.append(template_key)
        elif template_key in ["provider_payment_summary_report", "individual_provider_payment_report"]:
            # Check sub-keys for reports with weekly/on_demand structure
            report_templates = email_templates.get(template_key, {})
            if 'weekly' not in report_templates:
                missing.append(f"{template_key}.weekly")
            if 'on_demand' not in report_templates:
                missing.append(f"{template_key}.on_demand")
    
    return missing

def add_missing_templates(current_templates: Dict[str, Any], missing: List[str]) -> Dict[str, Any]:
    """
    Add missing templates to the current template structure
    
    Args:
        current_templates: Current templates from AWS Secrets Manager
        missing: List of missing template keys
        
    Returns:
        Updated templates dictionary
    """
    if 'email_templates' not in current_templates:
        current_templates['email_templates'] = {}
    
    for template_key in missing:
        if template_key in EMAIL_TEMPLATES:
            current_templates['email_templates'][template_key] = EMAIL_TEMPLATES[template_key]
            logger.info(f"Added template: {template_key}")
        elif "." in template_key:
            # Handle sub-keys for nested structures
            main_key, sub_key = template_key.split(".", 1)
            if main_key not in current_templates['email_templates']:
                current_templates['email_templates'][main_key] = {}
            if main_key in EMAIL_TEMPLATES and sub_key in EMAIL_TEMPLATES[main_key]:
                current_templates['email_templates'][main_key][sub_key] = \
                    EMAIL_TEMPLATES[main_key][sub_key]
                logger.info(f"Added sub-template: {template_key}")
    
    return current_templates

def main():
    """Main function to check and update email templates"""
    parser = argparse.ArgumentParser(
        description="Check and add missing email templates to AWS Secrets Manager"
    )
    parser.add_argument(
        '--region', 
        default='us-east-1', 
        help='AWS region (default: us-east-1)'
    )
    parser.add_argument(
        '--dry-run', 
        action='store_true', 
        help='Show what would be done without making changes'
    )
    parser.add_argument(
        '--force-update', 
        action='store_true', 
        help='Update all templates even if they exist'
    )
    
    args = parser.parse_args()
    
    logger.info(f"Starting email template setup for region: {args.region}")
    if args.dry_run:
        logger.info("DRY RUN MODE: No changes will be made")
    
    try:
        # Get current templates
        current_templates = get_current_templates(args.region)
        
        # Check what's missing
        missing = check_missing_templates(current_templates)
        
        if not missing and not args.force_update:
            logger.info("✅ All email templates are already present in AWS Secrets Manager")
            logger.info("Available templates:")
            email_templates = current_templates.get('email_templates', {})
            for key, value in email_templates.items():
                if isinstance(value, dict) and 'subject' in value:
                    logger.info(f"  - {key}")
                elif isinstance(value, dict):
                    for sub_key in value.keys():
                        logger.info(f"  - {key}.{sub_key}")
            return 0
        
        if missing:
            logger.info(f"Missing templates: {missing}")
        
        if args.force_update:
            logger.info("Force update mode: Adding/updating all templates")
            # Add all templates
            for template_key, template_data in EMAIL_TEMPLATES.items():
                current_templates['email_templates'][template_key] = template_data
                logger.info(f"Added/updated template: {template_key}")
        else:
            # Add only missing templates
            current_templates = add_missing_templates(current_templates, missing)
        
        # Update in AWS Secrets Manager
        success = update_templates_in_secrets(current_templates, args.region, args.dry_run)
        
        if success:
            if args.dry_run:
                logger.info("✅ DRY RUN completed successfully")
            else:
                logger.info("✅ Email templates successfully updated in AWS Secrets Manager")
            return 0
        else:
            logger.error("❌ Failed to update email templates")
            return 1
            
    except Exception as e:
        logger.error(f"❌ Script failed: {str(e)}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
