# Email Template Setup Script

This document explains how to use the one-time email template setup script.

## Overview

The `setup_email_templates.py` script checks which email templates are already stored in AWS Secrets Manager and adds any missing ones. This is a one-time utility script that can be run and then discarded.

## Usage

### Basic Usage
```bash
python setup_email_templates.py
```

### Options
```bash
# Specify AWS region
python setup_email_templates.py --region us-west-2

# Dry run (see what would be done without making changes)
python setup_email_templates.py --dry-run

# Force update all templates (even if they exist)
python setup_email_templates.py --force-update

# Combine options
python setup_email_templates.py --region us-east-1 --dry-run
```

## What It Does

1. **Checks Current Templates**: Retrieves existing email templates from `surgicase/email_templates` secret in AWS Secrets Manager
2. **Identifies Missing Templates**: Compares with required templates and identifies what's missing
3. **Adds Missing Templates**: Updates the secret with any missing template definitions
4. **Creates Secret If Needed**: If the secret doesn't exist, it will be created

## Templates Managed

The script manages these email templates:

### Provider Payment Summary Report
- `provider_payment_summary_report.weekly` - Weekly summary report email
- `provider_payment_summary_report.on_demand` - On-demand summary report email

### Individual Provider Reports  
- `individual_provider_payment_report.weekly` - Weekly individual provider report
- `individual_provider_payment_report.on_demand` - On-demand individual provider report

## Template Variables

The templates support these variables:
- `{creation_date}` - Report generation date
- `{report_date}` - Report period/date range
- `{total_states}` - Number of states (summary report only)
- `{total_providers}` - Number of providers  
- `{total_amount}` - Total payment amount
- `{filename}` - PDF filename
- `{provider_name}` - Provider name (individual reports only)
- `{npi}` - Provider NPI (individual reports only)
- `{password}` - PDF password (individual reports only)
- `{case_count}` - Number of cases (individual reports only)

## Prerequisites

1. AWS credentials configured (via AWS CLI, environment variables, or IAM role)
2. Permissions to read/write to AWS Secrets Manager
3. Python 3.6+ with boto3 installed

## Installation

```bash
pip install boto3 --break-system-packages
```

## Example Output

```
2025-08-08 10:30:00 - INFO - Starting email template setup for region: us-east-1
2025-08-08 10:30:01 - INFO - Successfully retrieved current email templates from AWS Secrets Manager
2025-08-08 10:30:01 - INFO - Missing templates: ['provider_payment_summary_report', 'individual_provider_payment_report']
2025-08-08 10:30:01 - INFO - Added template: provider_payment_summary_report
2025-08-08 10:30:01 - INFO - Added template: individual_provider_payment_report
2025-08-08 10:30:02 - INFO - Successfully updated email templates in AWS Secrets Manager
2025-08-08 10:30:02 - INFO - ✅ Email templates successfully updated in AWS Secrets Manager
```

## Cleanup

After running this script successfully, you can:
1. Delete the script file: `rm setup_email_templates.py`
2. Delete this README: `rm EMAIL_TEMPLATE_SETUP.md`

The email templates will be permanently stored in AWS Secrets Manager and the application will retrieve them from there.

## Troubleshooting

### Permission Errors
Ensure your AWS credentials have the following permissions:
- `secretsmanager:GetSecretValue`
- `secretsmanager:UpdateSecret` 
- `secretsmanager:CreateSecret`

### Region Issues
Make sure to specify the correct AWS region where your secrets are stored:
```bash
python setup_email_templates.py --region your-region
```

### Dry Run First
Always test with dry run first to see what changes would be made:
```bash
python setup_email_templates.py --dry-run
```
