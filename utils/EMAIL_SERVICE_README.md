# Email Service Utility

A generic email service utility using AWS Simple Email Service (SES) for sending emails with attachments, HTML content, and comprehensive recipient management.

## Features

- **Multiple Recipients**: Support for TO, CC, and BCC recipients
- **Attachments**: Support for file attachments with automatic MIME type detection
- **HTML Email**: Support for both plain text and HTML email bodies
- **Flexible Input**: Accept single email addresses or lists of addresses
- **Error Handling**: Comprehensive error handling with detailed response information
- **AWS SES Integration**: Full integration with AWS Simple Email Service
- **Configuration Verification**: Built-in SES configuration verification

## Setup Requirements

### 1. AWS Configuration

Ensure your AWS credentials are configured (the system already has AWS CLI access):

```bash
# Verify AWS configuration
aws ses describe-configuration-set --configuration-set-name default
```

### 2. AWS Secrets Manager Setup

The email service uses AWS Secrets Manager to securely store the default sender email address. Create a secret with the following configuration:

**Secret Name**: `surgicase/ses_keys`  
**Secret Key**: `ses_default_from_email`  
**Secret Value**: Your verified SES email address

```bash
# Create the secret using AWS CLI
aws secretsmanager create-secret \
  --name "surgicase/ses_keys" \
  --description "SES configuration for SurgiCase email service" \
  --secret-string '{"ses_default_from_email":"your-verified-email@yourdomain.com"}'

# Or update an existing secret
aws secretsmanager update-secret \
  --secret-id "surgicase/ses_keys" \
  --secret-string '{"ses_default_from_email":"your-verified-email@yourdomain.com"}'
```

This approach provides better security and scalability compared to environment variables.

### 3. IAM Permissions

Ensure your application has the necessary IAM permissions for both SES and Secrets Manager:

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "ses:SendEmail",
                "ses:SendRawEmail",
                "ses:GetSendQuota",
                "ses:ListVerifiedEmailAddresses"
            ],
            "Resource": "*"
        },
        {
            "Effect": "Allow",
            "Action": [
                "secretsmanager:GetSecretValue"
            ],
            "Resource": "arn:aws:secretsmanager:*:*:secret:surgicase/ses_keys*"
        }
    ]
}
```

### 4. SES Email Verification

Before using SES, you need to verify your sender email address:

```bash
# Add and verify an email address
aws ses verify-email-identity --email-address your-email@yourdomain.com
```

## Basic Usage

### Simple Text Email

```python
from utils.email_service import send_email

# Send a simple text email
result = send_email(
    to_addresses="recipient@example.com",
    subject="Test Email",
    body="This is a test email message.",
    from_address="sender@yourdomain.com"
)

if result["success"]:
    print(f"Email sent! Message ID: {result['message_id']}")
else:
    print(f"Error: {result['error']}")
```

### Email with Multiple Recipients

```python
result = send_email(
    to_addresses=["user1@example.com", "user2@example.com"],
    subject="Provider Payment Report",
    body="Please find the attached payment report.",
    cc_addresses="manager@example.com",
    bcc_addresses=["audit@example.com", "backup@example.com"]
)
```

### Email with Attachments

```python
from utils.email_service import send_email, create_attachment_from_file

# Create attachment from file
attachment = create_attachment_from_file("/path/to/payment_report.pdf")

result = send_email(
    to_addresses="provider@hospital.com",
    subject="Monthly Payment Report",
    body="Please find your monthly payment report attached.",
    attachments=[attachment]
)
```

### HTML Email

```python
html_body = """
<html>
<body>
<h2>Payment Report</h2>
<p>Dear Provider,</p>
<p>Please find your <strong>monthly payment report</strong> attached.</p>
<p>Best regards,<br>The Billing Team</p>
</body>
</html>
"""

result = send_email(
    to_addresses="provider@hospital.com",
    subject="Monthly Payment Report",
    body="Please find your monthly payment report attached.",  # Plain text fallback
    body_html=html_body,
    attachments=[attachment]
)
```

## Advanced Usage

### Creating Attachments from Data

```python
from utils.email_service import create_attachment_from_data
import json

# Create attachment from in-memory data
report_data = {"total": 1500.00, "cases": 10}
json_data = json.dumps(report_data, indent=2).encode('utf-8')
attachment = create_attachment_from_data(
    filename="report_summary.json",
    data=json_data,
    content_type="application/json"
)

result = send_email(
    to_addresses="manager@hospital.com",
    subject="Report Summary",
    body="Attached is the report summary.",
    attachments=[attachment]
)
```

### Batch Email Processing

```python
def send_provider_reports(provider_emails, report_files):
    """Send payment reports to multiple providers"""
    results = []
    
    for email, report_file in zip(provider_emails, report_files):
        attachment = create_attachment_from_file(report_file)
        
        result = send_email(
            to_addresses=email,
            subject="Your Monthly Payment Report",
            body="Please find your monthly payment report attached.",
            attachments=[attachment]
        )
        
        results.append({
            "email": email,
            "success": result["success"],
            "message_id": result.get("message_id"),
            "error": result.get("error")
        })
    
    return results
```

## Configuration Verification

### SES and Secrets Manager Verification

```python
from utils.email_service import verify_ses_configuration, test_secrets_configuration

# Check complete SES configuration including secrets
config = verify_ses_configuration()

if config["success"]:
    print(f"SES configured in region: {config['region']}")
    print(f"Daily quota: {config['daily_sending_quota']}")
    print(f"Emails sent today: {config['emails_sent_today']}")
    print(f"Verified addresses: {config['verified_email_addresses']}")
    
    # Check secrets manager status
    secrets = config["secrets_manager"]
    if secrets["success"]:
        print(f"Default from email: {secrets['default_from_email']}")
    else:
        print(f"Secrets error: {secrets['error']}")
else:
    print(f"Configuration error: {config['error']}")

# Test only the secrets manager configuration
secrets_test = test_secrets_configuration()
if secrets_test["success"]:
    print(f"✅ {secrets_test['message']}")
    print(f"From address: {secrets_test['from_address']}")
else:
    print(f"❌ {secrets_test['message']}")
    print(f"Error: {secrets_test['error']}")
```

## Function Reference

### `send_email()`

Main function for sending emails.

**Parameters:**
- `to_addresses` (str | List[str]): Email address(es) to send to
- `subject` (str): Email subject line
- `body` (str): Plain text email body
- `from_address` (str, optional): Sender email address. If None, retrieves from AWS Secrets Manager
- `attachments` (List[EmailAttachment], optional): List of attachments
- `cc_addresses` (str | List[str], optional): CC recipients
- `bcc_addresses` (str | List[str], optional): BCC recipients
- `body_html` (str, optional): HTML version of email body
- `aws_region` (str, optional): AWS region (default: "us-east-1")

**Returns:**
Dict with success status, message ID, or error details.

### `create_attachment_from_file()`

Create an attachment from a file path.

**Parameters:**
- `file_path` (str): Path to the file
- `filename` (str, optional): Custom filename for attachment

**Returns:**
`EmailAttachment` object

### `create_attachment_from_data()`

Create an attachment from raw data.

**Parameters:**
- `filename` (str): Filename for the attachment
- `data` (bytes): Raw file data
- `content_type` (str, optional): MIME content type

**Returns:**
`EmailAttachment` object

### `verify_ses_configuration()`

Verify SES configuration and get status information, including Secrets Manager test.

**Parameters:**
- `aws_region` (str, optional): AWS region to check

**Returns:**
Dict with configuration details, SES status, and Secrets Manager test results

### `test_secrets_configuration()`

Test only the AWS Secrets Manager configuration for the email service.

**Parameters:**
- `aws_region` (str, optional): AWS region where the secret is stored

**Returns:**
Dict with secrets configuration test results

## Supported File Types

The email service automatically detects MIME types for common file extensions:

- **Documents**: `.pdf`, `.docx`, `.doc`, `.txt`
- **Spreadsheets**: `.xlsx`, `.xls`, `.csv`
- **Data**: `.json`, `.xml`, `.iif`
- **Archives**: `.zip`
- **Images**: `.png`, `.jpg`, `.jpeg`, `.gif`

## Error Handling

The email service provides comprehensive error handling:

```python
result = send_email(
    to_addresses="invalid-email",
    subject="Test",
    body="Test message"
)

if not result["success"]:
    error_code = result.get("error_code")
    if error_code == "MessageRejected":
        print("Email was rejected - check recipient address")
    elif error_code == "SendingPausedException":
        print("SES sending is paused for your account")
    else:
        print(f"General error: {result['error']}")
```

## Best Practices

1. **Email Verification**: Always verify sender email addresses with SES before use
2. **Rate Limiting**: Be aware of SES sending limits and implement appropriate throttling
3. **Error Handling**: Always check the success status of email operations
4. **Attachment Size**: Keep attachments under 10MB (SES limit)
5. **Secrets Management**: Use AWS Secrets Manager for secure configuration storage
6. **Logging**: The service automatically logs email operations for debugging
7. **IAM Permissions**: Ensure your application has proper permissions for both SES and Secrets Manager

## Integration Example

Here's how to integrate the email service with your existing report generation:

```python
from utils.email_service import send_email, create_attachment_from_file

def send_provider_payment_report(provider_email: str, report_path: str):
    """
    Send payment report to provider
    
    Args:
        provider_email: Provider's email address
        report_path: Path to the generated PDF report
    
    Returns:
        Dict with send status
    """
    try:
        # Create attachment from generated report
        attachment = create_attachment_from_file(report_path)
        
        # Send email with report
        result = send_email(
            to_addresses=provider_email,
            subject="Monthly Payment Report - SurgiCase",
            body="""Dear Provider,

Please find your monthly payment report attached. This report contains:
- Case summaries for the reporting period
- Payment calculations and adjustments
- Total amounts payable

If you have any questions about this report, please contact our billing department.

Best regards,
SurgiCase Billing Team""",
            attachments=[attachment]
        )
        
        return result
        
    except Exception as e:
        return {
            "success": False,
            "error": f"Failed to send report: {str(e)}"
        }
```

## Monitoring and Logging

The email service integrates with the existing logging infrastructure. All email operations are logged with appropriate log levels:

- **INFO**: Successful email sends
- **ERROR**: Failed email operations
- **DEBUG**: Detailed operation information

Monitor your email sending through CloudWatch metrics in AWS Console for SES usage statistics.