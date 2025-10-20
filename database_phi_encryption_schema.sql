-- Created: 2025-10-19
-- Last Modified: 2025-10-19 23:54:20
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
-- Note: IF NOT EXISTS not supported in ALTER TABLE ADD COLUMN, so we ignore errors if column exists
SET @table_name = 'cases';
SET @column_name = 'phi_encrypted';
SET @column_check = (
    SELECT COUNT(*) FROM information_schema.COLUMNS 
    WHERE TABLE_SCHEMA = DATABASE() 
    AND TABLE_NAME = @table_name 
    AND COLUMN_NAME = @column_name
);

SET @sql = IF(@column_check = 0,
    'ALTER TABLE cases ADD COLUMN phi_encrypted TINYINT DEFAULT 0 COMMENT ''0 = unencrypted (legacy), 1 = encrypted with user DEK''',
    'SELECT ''Column phi_encrypted already exists in cases'' AS message');
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- Add index for querying encrypted status
SET @index_check = (
    SELECT COUNT(*) FROM information_schema.STATISTICS 
    WHERE TABLE_SCHEMA = DATABASE() 
    AND TABLE_NAME = 'cases' 
    AND INDEX_NAME = 'idx_phi_encrypted'
);

SET @sql = IF(@index_check = 0,
    'ALTER TABLE cases ADD INDEX idx_phi_encrypted (phi_encrypted)',
    'SELECT ''Index idx_phi_encrypted already exists on cases'' AS message');
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- Add encryption tracking column to deleted_cases table as well
SET @table_name = 'deleted_cases';
SET @column_check = (
    SELECT COUNT(*) FROM information_schema.COLUMNS 
    WHERE TABLE_SCHEMA = DATABASE() 
    AND TABLE_NAME = @table_name 
    AND COLUMN_NAME = 'phi_encrypted'
);

SET @sql = IF(@column_check = 0,
    'ALTER TABLE deleted_cases ADD COLUMN phi_encrypted TINYINT DEFAULT 0 COMMENT ''0 = unencrypted (legacy), 1 = encrypted with user DEK''',
    'SELECT ''Column phi_encrypted already exists in deleted_cases'' AS message');
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- Add index for deleted_cases as well
SET @index_check = (
    SELECT COUNT(*) FROM information_schema.STATISTICS 
    WHERE TABLE_SCHEMA = DATABASE() 
    AND TABLE_NAME = 'deleted_cases' 
    AND INDEX_NAME = 'idx_phi_encrypted'
);

SET @sql = IF(@index_check = 0,
    'ALTER TABLE deleted_cases ADD INDEX idx_phi_encrypted (phi_encrypted)',
    'SELECT ''Index idx_phi_encrypted already exists on deleted_cases'' AS message');
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

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

