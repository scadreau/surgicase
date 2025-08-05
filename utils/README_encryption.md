# HIPAA Database Backup Encryption

This document describes the HIPAA-compliant encryption system for SurgiCase database backups.

## Overview

The encryption system uses a **hybrid AWS KMS + AES-256-GCM approach** to ensure HIPAA compliance for database backups containing protected health information (PHI).

## Architecture

### Encryption Process
1. **Data Encryption Key (DEK) Generation**: AWS KMS generates a 256-bit AES key
2. **File Encryption**: AES-256-GCM encrypts the backup file using the DEK
3. **Key Encryption**: KMS encrypts the DEK and stores it alongside the backup
4. **S3 Upload**: Encrypted backup + encryption metadata uploaded with KMS server-side encryption

### Components

- **`utils/encryption.py`** - Core encryption/decryption functionality
- **`utils/db_backup.py`** - Modified backup process with encryption integration
- **`utils/db_decrypt.py`** - Decryption and recovery utilities
- **`utils/s3_storage.py`** - Updated S3 functions with KMS support

## Usage

### Creating Encrypted Backups
```bash
python utils/db_backup.py
```

The backup process now automatically:
- Creates compressed database dump
- Encrypts using AES-256-GCM + KMS
- Removes unencrypted files
- Uploads to S3 with additional KMS encryption

### Listing Available Backups
```bash
python utils/db_decrypt.py --list
```

### Decrypting a Backup
```bash
# Decrypt local file
python utils/db_decrypt.py --decrypt /path/to/backup.sql.gz.encrypted

# Full recovery from S3 (dry run)
python utils/db_decrypt.py --recover db_backup_20250101_120000.sql.gz.encrypted

# Full recovery with database restore
python utils/db_decrypt.py --recover db_backup_20250101_120000.sql.gz.encrypted --restore
```

## Security Features

### HIPAA Compliance
- **Encryption at Rest**: AES-256-GCM for file encryption
- **Key Management**: AWS KMS with audit trails
- **Access Controls**: IAM policies for KMS key usage
- **Data Integrity**: GCM authentication tags prevent tampering

### Multi-Layer Protection
1. **Application Layer**: AES-256-GCM encryption
2. **S3 Layer**: KMS server-side encryption
3. **Transport Layer**: HTTPS for all transfers

### Key Security
- **Automatic Key Rotation**: AWS KMS handles key rotation
- **Access Logging**: CloudTrail logs all key operations
- **Memory Protection**: Sensitive keys cleared after use

## File Structure

### Encrypted Backup Files
```
~/vol2/db_backups/
├── db_backup_20250101_120000.sql.gz.encrypted
└── db_backup_20250101_120000.sql.gz.encrypted.encryption_info
```

### S3 Storage Structure
```
s3://bucket/private/db_backups/
├── db_backup_20250101_120000.sql.gz.encrypted
└── db_backup_20250101_120000.sql.gz.encrypted.encryption_info
```

## Encryption Metadata

Each encrypted backup includes metadata:
```json
{
  "kms_key_id": "arn:aws:kms:us-east-1:...",
  "encrypted_data_key": "base64-encoded-key",
  "iv": "base64-encoded-iv",
  "auth_tag": "base64-encoded-tag",
  "algorithm": "AES-256-GCM",
  "metadata": {
    "backup_date": "2025-01-01T12:00:00Z",
    "tables_count": 45,
    "backup_type": "database_dump"
  }
}
```

## Recovery Process

### Emergency Recovery Steps
1. **List backups**: `python utils/db_decrypt.py --list`
2. **Download & decrypt**: `python utils/db_decrypt.py --recover [backup_name]`
3. **Validate backup**: Review dry-run output
4. **Restore database**: Add `--restore` flag (⚠️ OVERWRITES DATABASE)

### Validation
- File integrity verification using GCM auth tags
- SQL dump format validation
- Size verification against original file

## Monitoring

The system includes:
- Encryption success/failure logging
- KMS key usage tracking
- File size and timing metrics
- S3 upload status monitoring

## Dependencies

- `cryptography` - AES encryption
- `boto3` - AWS SDK
- `pymysql` - Database connectivity

## Security Considerations

⚠️ **Important Notes**:
- Encrypted backups are automatically generated - unencrypted backups are removed
- KMS key access is required for decryption
- Database restore operations overwrite existing data
- Always test recovery procedures in non-production environments

## Compliance

This system meets HIPAA requirements for:
- **§164.312(a)(2)(iv)** - Encryption of PHI
- **§164.312(e)(2)(ii)** - End-to-end encryption
- **§164.312(c)(1)** - Access controls
- **§164.312(b)** - Audit trails