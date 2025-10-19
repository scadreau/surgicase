-- Created: 2025-10-19
-- Last Modified: 2025-10-19 23:40:46
-- Author: Scott Cadreau
--
-- PHI Field Encryption Database Schema
-- Creates tables to support per-user field-level encryption for PHI data

-- Table to store encrypted data encryption keys (DEKs) per user
CREATE TABLE IF NOT EXISTS user_encryption_keys (
    user_id VARCHAR(100) PRIMARY KEY,
    encrypted_dek TEXT NOT NULL COMMENT 'Base64-encoded DEK encrypted by AWS KMS master key',
    key_version INT DEFAULT 1 COMMENT 'Version number for key rotation tracking',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT 'When this encryption key was first generated',
    rotated_at TIMESTAMP NULL COMMENT 'Last time this key was rotated (if ever)',
    is_active TINYINT DEFAULT 1 COMMENT 'Whether this key is currently active (for rotation scenarios)',
    FOREIGN KEY (user_id) REFERENCES user_profile(user_id) ON DELETE CASCADE,
    INDEX idx_is_active (is_active),
    INDEX idx_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
COMMENT='Stores encrypted data encryption keys for per-user PHI field encryption';

-- Add encryption tracking column to cases table
-- This helps track migration status and identify encrypted vs unencrypted records
ALTER TABLE cases 
ADD COLUMN IF NOT EXISTS phi_encrypted TINYINT DEFAULT 0 
COMMENT '0 = unencrypted (legacy), 1 = encrypted with user DEK';

-- Add index for querying encrypted status
ALTER TABLE cases
ADD INDEX IF NOT EXISTS idx_phi_encrypted (phi_encrypted);

-- Add encryption tracking column to deleted_cases table as well
ALTER TABLE deleted_cases 
ADD COLUMN IF NOT EXISTS phi_encrypted TINYINT DEFAULT 0 
COMMENT '0 = unencrypted (legacy), 1 = encrypted with user DEK';

-- Add index for deleted_cases as well
ALTER TABLE deleted_cases
ADD INDEX IF NOT EXISTS idx_phi_encrypted (phi_encrypted);

-- Optional: Create audit table for key operations (for HIPAA compliance)
CREATE TABLE IF NOT EXISTS encryption_key_audit (
    audit_id BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id VARCHAR(100) NOT NULL,
    operation VARCHAR(50) NOT NULL COMMENT 'Operation: generate, rotate, decrypt, error',
    performed_by VARCHAR(100) NULL COMMENT 'Admin user who performed the operation',
    operation_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    details TEXT NULL COMMENT 'Additional operation details in JSON format',
    ip_address VARCHAR(45) NULL COMMENT 'IP address of the request',
    INDEX idx_user_id (user_id),
    INDEX idx_operation (operation),
    INDEX idx_timestamp (operation_timestamp)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
COMMENT='Audit trail for all encryption key operations for HIPAA compliance';

