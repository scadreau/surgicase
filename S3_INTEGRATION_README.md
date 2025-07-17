# S3 Integration for SurgiCase Reports

This document describes the S3 integration feature that allows automatic storage of generated reports in AWS S3.

## Overview

The SurgiCase API now includes S3 storage capabilities for all generated reports. Reports are automatically uploaded to S3 with metadata for easy tracking and retrieval.

## Features

- **Automatic S3 Upload**: All reports are automatically uploaded to S3 after generation
- **Metadata Storage**: Rich metadata is attached to each S3 object for tracking
- **Secure Configuration**: S3 configuration is stored in AWS Secrets Manager
- **Dual Storage**: Reports are stored both locally and in S3
- **Error Handling**: Graceful handling of S3 upload failures

## Setup

### 1. AWS Secrets Manager Configuration

Create a secret in AWS Secrets Manager with the name `surgicase/s3-user-reports`:

**Secret Name**: `surgicase/s3-user-reports`

**Secret Value (JSON)**:
```json
{
  "bucket_name": "amplify-surgicalcasemanag-surgicaldocsbucket5a7ebd-8usdadqv6nnp",
  "region": "us-east-1",
  "folder_prefix": "reports/provider-payments/",
  "encryption": "AES256",
  "retention_days": 90
}
```

**Optional (if using access keys instead of IAM roles)**:
```json
{
  "bucket_name": "amplify-surgicalcasemanag-surgicaldocsbucket5a7ebd-8usdadqv6nnp",
  "region": "us-east-1",
  "folder_prefix": "private/reports/provider-payments/",
  "encryption": "AES256",
  "retention_days": 36500,
  "aws_access_key_id": "YOUR_ACCESS_KEY_ID",
  "aws_secret_access_key": "YOUR_SECRET_ACCESS_KEY"
}
```

### 2. AWS Credentials

Ensure your application has access to AWS services:

**Option A: IAM Role (Recommended for production)**
- Attach an IAM role to your EC2 instance or ECS task
- Role should have permissions for S3 and Secrets Manager

**Option B: Access Keys**
- Configure AWS credentials in your environment
- Include access keys in the Secrets Manager configuration

### 3. S3 Bucket Permissions

Ensure your S3 bucket allows the necessary operations:

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "SurgiCaseReportUploads",
            "Effect": "Allow",
            "Principal": {
                "AWS": "arn:aws:iam::YOUR_ACCOUNT_ID:role/YOUR_ROLE_NAME"
            },
            "Action": [
                "s3:PutObject",
                "s3:GetObject",
                "s3:DeleteObject"
            ],
            "Resource": "arn:aws:s3:::amplify-surgicalcasemanag-surgicaldocsbucket5a7ebd-8usdadqv6nnp/reports/*"
        }
    ]
}
```

## API Endpoints

### Provider Payment Report
- **Endpoint**: `GET /provider_payment_report`
- **S3 Storage**: Automatically uploads to `reports/provider-payments/`
- **Metadata**: Includes provider count, case count, total amount, date filters

### Provider Payment Report (Enhanced)
- **Endpoint**: `GET /provider_payment_report`
- **S3 Storage**: Automatically uploads to `reports/provider-payments/`
- **Metadata**: Includes provider count, case count, total amount, date filters
- **Features**: Enhanced with S3 storage while maintaining all existing functionality

## S3 File Structure

```
reports/
└── provider-payments/
    ├── 20250717_104530_provider_payment_report_20250717_104530.pdf
    └── 20250717_104545_provider_payment_report_20250717_104545.pdf
```

## File Naming Convention

Files are named with timestamps for uniqueness:
- Format: `YYYYMMDD_HHMMSS_filename_YYYYMMDD_HHMMSS.pdf`
- Example: `20250717_104530_provider_payment_report_20250717_104530.pdf`

## Metadata

Each S3 object includes rich metadata:

### Provider Payment Report Metadata
```json
{
  "report_type": "provider_payment",
  "generated_by": "surgicase_api",
  "total_providers": "5",
  "total_cases": "25",
  "total_amount": "12500.00",
  "start_date": "2025-01-01",
  "end_date": "2025-07-17",
  "user_filter": "all"
}
```



## Response Headers

API responses include S3 information in headers:

```
X-S3-URL: https://bucket-name.s3.us-east-1.amazonaws.com/reports/provider-payments/20250717_104530_provider_payment_report_20250717_104530.pdf
X-S3-Key: reports/provider-payments/20250717_104530_provider_payment_report_20250717_104530.pdf
X-S3-Upload-Success: true
```

## Testing

Run the S3 integration test:

```bash
python test_s3_integration.py
```

This will:
1. Test S3 configuration retrieval from Secrets Manager
2. Test file upload functionality
3. Provide detailed feedback on any issues

## Error Handling

The system handles various error scenarios:

- **Configuration Errors**: Logs errors and continues with local storage only
- **Upload Failures**: Logs errors but doesn't prevent report generation
- **Network Issues**: Graceful timeout handling
- **Permission Errors**: Detailed error messages for troubleshooting

## Monitoring

Monitor S3 uploads through:

1. **Application Logs**: Check for S3-related log messages
2. **AWS CloudWatch**: Monitor S3 metrics and logs
3. **S3 Console**: View uploaded files and metadata
4. **API Response Headers**: Check upload success status

## Security Considerations

- **Encryption**: All files are encrypted with AES256
- **Access Control**: Use IAM roles for production deployments
- **Secrets Management**: Configuration stored securely in AWS Secrets Manager
- **Audit Trail**: All uploads are logged with timestamps and metadata

## Troubleshooting

### Common Issues

1. **"AWS credentials not found"**
   - Ensure AWS credentials are configured
   - Check IAM role permissions
   - Verify access keys in Secrets Manager

2. **"S3 upload error: Access Denied"**
   - Check S3 bucket permissions
   - Verify IAM role has S3 access
   - Ensure bucket exists and is accessible

3. **"Secret not found"**
   - Verify secret name is correct
   - Check AWS region configuration
   - Ensure application has Secrets Manager access

### Debug Mode

Enable debug logging by setting the log level:

```python
import logging
logging.getLogger('utils.s3_storage').setLevel(logging.DEBUG)
```

## Future Enhancements

- **Lifecycle Policies**: Automatic cleanup of old reports
- **Versioning**: S3 object versioning for report history
- **CDN Integration**: CloudFront distribution for faster access
- **Backup Strategy**: Cross-region replication for disaster recovery 