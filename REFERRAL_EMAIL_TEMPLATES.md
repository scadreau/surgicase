# Referral Report Email Templates Setup

## Overview
The referral report functionality requires email templates to be configured in AWS Secrets Manager. These templates need to be added to the existing `surgicase/email_templates` secret.

## Quick Setup
Run the automated setup script:
```bash
python add_referral_email_templates.py
```

Or for a dry run to see what would be added:
```bash
python add_referral_email_templates.py --dry-run
```

## Manual Setup
If you prefer to add the templates manually, add the following JSON structure to the `surgicase/email_templates` secret in AWS Secrets Manager:

```json
{
  "email_templates": {
    "referral_report": {
      "weekly": {
        "subject": "Weekly Referral Report - {creation_date}",
        "body": "Dear {recipient_name},\n\nPlease find attached the weekly Referral Report for your review. This report provides a comprehensive analysis of our referral network, showing which users were referred by whom along with their payment categories and totals.\n\nReport Summary:\n• Report Date: {creation_date}\n• Total Referral Users: {total_referral_users}\n• Total Referred Users: {total_referred_users}\n• Total Cases: {total_cases}\n• Total Amount: ${total_amount}\n\nIMPORTANT SECURITY INFORMATION:\nThe attached PDF report is password-protected for security. To open the report, use the following password:\nPassword: {password}\n\nPlease keep this password secure and do not share it with others. The report contains confidential business and financial information.\n\nReport Structure:\nThis report is organized by referral user, with each referral user getting their own page showing:\n- All users they referred\n- Payment categories for each referred user\n- Case counts and payment amounts\n- Subtotals per referral user\n\nThis analysis helps track the effectiveness of our referral network and understand user acquisition patterns.\n\nIf you have any questions about this report or need assistance accessing the document, please contact our office.\n\nBest regards,\nSurgiCase Reporting System\n\n----\nThis is an automated weekly report from the SurgiCase system.\nReport Type: {report_type}"
      },
      "on_demand": {
        "subject": "Referral Report - Generated {creation_date}",
        "body": "Dear {recipient_name},\n\nPlease find attached the Referral Report that you requested on {creation_date}. This report provides a comprehensive analysis of our referral network, showing which users were referred by whom along with their payment categories and totals.\n\nReport Summary:\n• Report Date: {creation_date}\n• Total Referral Users: {total_referral_users}\n• Total Referred Users: {total_referred_users}\n• Total Cases: {total_cases}\n• Total Amount: ${total_amount}\n\nIMPORTANT SECURITY INFORMATION:\nThe attached PDF report is password-protected for security. To open the report, use the following password:\nPassword: {password}\n\nPlease keep this password secure and do not share it with others. The report contains confidential business and financial information.\n\nReport Structure:\nThis report is organized by referral user, with each referral user getting their own page showing:\n- All users they referred\n- Payment categories for each referred user\n- Case counts and payment amounts\n- Subtotals per referral user\n\nThis analysis helps track the effectiveness of our referral network and understand user acquisition patterns.\n\nIf you have any questions about this report or need assistance accessing the document, please contact our office.\n\nBest regards,\nSurgiCase Reporting System\n\n----\nThis is an on-demand report from the SurgiCase system.\nReport Type: {report_type}"
      }
    }
  }
}
```

## Email Recipients Setup
You also need to add recipients to the `report_email_list` table in the database:

```sql
INSERT INTO report_email_list (report_name, email_type, email_address, first_name, last_name, active) 
VALUES 
('referral_report', 'weekly', 'admin@example.com', 'Admin', 'User', 1),
('referral_report', 'on_demand', 'admin@example.com', 'Admin', 'User', 1);
```

## Template Variables Available
The following variables are available in the email templates:

### Standard Variables
- `{recipient_name}` - Full name of the email recipient
- `{recipient_first_name}` - First name of the email recipient  
- `{recipient_last_name}` - Last name of the email recipient
- `{creation_date}` - Date the report was created
- `{creation_date_utc}` - UTC datetime object for timezone conversion

### Referral Report Specific Variables
- `{total_referral_users}` - Number of users who made referrals
- `{total_referred_users}` - Total number of users who were referred
- `{total_cases}` - Total number of cases in the report
- `{total_amount}` - Total payment amount across all cases
- `{password}` - Password for the PDF (weekly_YYYYMMDD format)
- `{report_type}` - Always "Referral Report"

## Verification
After adding the templates, you can verify they were added correctly by:

1. Checking the AWS Secrets Manager console
2. Running the referral report endpoint: `GET /referral_report`
3. Checking the application logs for any template-related errors

## Notes
- The templates support both `weekly` and `on_demand` email types
- The `weekly` template is used for automated weekly reports
- The `on_demand` template is used for manually requested reports
- Both templates include password information for the protected PDF
- The templates follow the same format and security practices as other report templates
