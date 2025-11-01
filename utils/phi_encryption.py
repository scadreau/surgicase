# Created: 2025-10-19
# Last Modified: 2025-11-01 02:47:35
# Author: Scott Cadreau

"""
HIPAA-compliant field-level encryption for PHI data using per-user AWS KMS + AES.

This module provides functionality to:
1. Generate per-user data encryption keys (DEKs) using AWS KMS
2. Encrypt/decrypt individual PHI fields using user-specific DEKs
3. Cache DEKs in memory for performance
4. Maintain audit trails for HIPAA compliance
5. Support key rotation per user

Architecture:
- One KMS master key for the entire application
- One DEK per user_id (stored encrypted in database)
- DEKs cached in memory with TTL
- AES-256-GCM for field encryption
"""

import os
import json
import base64
import logging
import threading
import time
from typing import Dict, Any, Optional, Tuple
from datetime import datetime, timedelta
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend
import boto3
from botocore.exceptions import ClientError
import pymysql.cursors

logger = logging.getLogger(__name__)

# KMS Master Key Configuration
KMS_MASTER_KEY_ALIAS = 'alias/surgicase-phi-master'
KMS_REGION = 'us-east-1'

# Cache configuration
DEK_CACHE_TTL_HOURS = 24  # Cache DEKs for 24 hours
_dek_cache: Dict[str, Tuple[bytes, float]] = {}  # {user_id: (decrypted_dek, expiry_timestamp)}
_cache_lock = threading.Lock()

# PHI fields to encrypt in cases table
# Note: patient_dob is NOT encrypted as it's stored in a DATE column (cannot store encrypted text)
# Names are the primary HIPAA identifiers; dob + insurance alone don't identify individuals
PHI_FIELDS = ['patient_first', 'patient_last', 'ins_provider']


class PHIEncryption:
    """
    HIPAA-compliant field-level encryption using per-user DEKs with AWS KMS.
    """
    
    def __init__(self, kms_key_alias: str = KMS_MASTER_KEY_ALIAS, region: str = KMS_REGION):
        """
        Initialize encryption with KMS configuration.
        
        Args:
            kms_key_alias: AWS KMS key alias (default: alias/surgicase-phi-master)
            region: AWS region for KMS (default: us-east-1)
        """
        self.kms_client = boto3.client('kms', region_name=region)
        self.kms_key_alias = kms_key_alias
        self.region = region
    
    def generate_user_dek(self, user_id: str) -> Tuple[bytes, str]:
        """
        Generate a new data encryption key for a specific user.
        
        Args:
            user_id: User ID to generate key for
            
        Returns:
            Tuple of (plaintext_dek, encrypted_dek_base64)
            
        Raises:
            Exception: If KMS key generation fails
        """
        try:
            logger.info(f"Generating new DEK for user: {user_id}")
            
            response = self.kms_client.generate_data_key(
                KeyId=self.kms_key_alias,
                KeySpec='AES_256'
            )
            
            plaintext_dek = response['Plaintext']
            encrypted_dek = response['CiphertextBlob']
            
            # Encode encrypted DEK as base64 for database storage
            encrypted_dek_base64 = base64.b64encode(encrypted_dek).decode('utf-8')
            
            logger.info(f"Successfully generated DEK for user: {user_id}")
            return plaintext_dek, encrypted_dek_base64
            
        except Exception as e:
            logger.error(f"Error generating DEK for user {user_id}: {str(e)}")
            raise
    
    def decrypt_user_dek(self, encrypted_dek_base64: str) -> bytes:
        """
        Decrypt a user's data encryption key using KMS.
        
        Args:
            encrypted_dek_base64: Base64-encoded encrypted DEK from database
            
        Returns:
            Plaintext DEK bytes
            
        Raises:
            Exception: If KMS decryption fails
        """
        try:
            # Decode from base64
            encrypted_dek = base64.b64decode(encrypted_dek_base64)
            
            response = self.kms_client.decrypt(CiphertextBlob=encrypted_dek)
            return response['Plaintext']
            
        except Exception as e:
            logger.error(f"Error decrypting DEK: {str(e)}")
            raise
    
    def encrypt_field(self, plaintext: str, dek: bytes) -> str:
        """
        Encrypt a single field value using AES-256-GCM.
        
        Args:
            plaintext: The field value to encrypt
            dek: Data encryption key (plaintext)
            
        Returns:
            Base64-encoded string containing: iv + auth_tag + ciphertext
            
        Note:
            Returns None if plaintext is None or empty
        """
        if plaintext is None or plaintext == '':
            return None
            
        try:
            # Generate random IV (12 bytes for GCM)
            iv = os.urandom(12)
            
            # Create cipher
            cipher = Cipher(
                algorithms.AES(dek),
                modes.GCM(iv),
                backend=default_backend()
            )
            encryptor = cipher.encryptor()
            
            # Encrypt
            ciphertext = encryptor.update(plaintext.encode('utf-8')) + encryptor.finalize()
            auth_tag = encryptor.tag
            
            # Combine: iv (12 bytes) + auth_tag (16 bytes) + ciphertext
            combined = iv + auth_tag + ciphertext
            
            # Return as base64
            return base64.b64encode(combined).decode('utf-8')
            
        except Exception as e:
            logger.error(f"Error encrypting field: {str(e)}")
            raise
    
    def decrypt_field(self, encrypted_base64: str, dek: bytes) -> Optional[str]:
        """
        Decrypt a single field value using AES-256-GCM.
        
        Args:
            encrypted_base64: Base64-encoded encrypted field (iv + auth_tag + ciphertext)
            dek: Data encryption key (plaintext)
            
        Returns:
            Decrypted string or None if input is None/empty
            
        Raises:
            Exception: If decryption or authentication fails
        """
        if encrypted_base64 is None or encrypted_base64 == '':
            return None
            
        try:
            # Decode from base64
            combined = base64.b64decode(encrypted_base64)
            
            # Extract components
            iv = combined[:12]
            auth_tag = combined[12:28]
            ciphertext = combined[28:]
            
            # Create cipher
            cipher = Cipher(
                algorithms.AES(dek),
                modes.GCM(iv, auth_tag),
                backend=default_backend()
            )
            decryptor = cipher.decryptor()
            
            # Decrypt and verify
            plaintext = decryptor.update(ciphertext) + decryptor.finalize()
            
            return plaintext.decode('utf-8')
            
        except Exception as e:
            logger.error(f"Error decrypting field: {str(e)}")
            raise


def get_user_dek(user_id: str, conn, cache: bool = True) -> bytes:
    """
    Get a user's decrypted DEK, using cache if available.
    
    Args:
        user_id: User ID to get DEK for
        conn: Database connection
        cache: Whether to use cache (default: True)
        
    Returns:
        Decrypted DEK bytes
        
    Raises:
        ValueError: If user has no encryption key
        Exception: If database or KMS operation fails
    """
    global _dek_cache
    
    # Check cache first
    if cache:
        with _cache_lock:
            if user_id in _dek_cache:
                dek, expiry = _dek_cache[user_id]
                if time.time() < expiry:
                    logger.debug(f"DEK cache hit for user: {user_id}")
                    return dek
                else:
                    # Expired, remove from cache
                    logger.debug(f"DEK cache expired for user: {user_id}")
                    del _dek_cache[user_id]
    
    # Cache miss or cache disabled, fetch from database
    logger.debug(f"DEK cache miss for user: {user_id}, fetching from database")
    
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute("""
                SELECT encrypted_dek, is_active 
                FROM user_encryption_keys 
                WHERE user_id = %s
            """, (user_id,))
            
            result = cursor.fetchone()
            
            if not result:
                raise ValueError(f"No encryption key found for user: {user_id}")
            
            if result['is_active'] != 1:
                raise ValueError(f"Encryption key for user {user_id} is not active")
            
            encrypted_dek_base64 = result['encrypted_dek']
        
        # Decrypt using KMS
        phi_crypto = PHIEncryption()
        decrypted_dek = phi_crypto.decrypt_user_dek(encrypted_dek_base64)
        
        # Cache it
        if cache:
            expiry = time.time() + (DEK_CACHE_TTL_HOURS * 3600)
            with _cache_lock:
                _dek_cache[user_id] = (decrypted_dek, expiry)
            logger.debug(f"Cached DEK for user: {user_id} (expires in {DEK_CACHE_TTL_HOURS} hours)")
        
        return decrypted_dek
        
    except Exception as e:
        logger.error(f"Error getting DEK for user {user_id}: {str(e)}")
        raise


def clear_dek_cache(user_id: Optional[str] = None):
    """
    Clear DEK cache for a specific user or all users.
    
    Args:
        user_id: User ID to clear cache for (None = clear all)
    """
    global _dek_cache
    
    with _cache_lock:
        if user_id:
            if user_id in _dek_cache:
                del _dek_cache[user_id]
                logger.info(f"Cleared DEK cache for user: {user_id}")
        else:
            _dek_cache.clear()
            logger.info("Cleared all DEK cache")


def encrypt_patient_data(data: Dict[str, Any], user_id: str, conn) -> Dict[str, Any]:
    """
    Encrypt all PHI fields in a patient data dictionary.
    
    Args:
        data: Dictionary containing patient data with PHI fields
        user_id: User ID who owns this data
        conn: Database connection
        
    Returns:
        Dictionary with PHI fields encrypted
        
    Note:
        Modifies the input dictionary in place and returns it
    """
    try:
        # Get user's DEK
        dek = get_user_dek(user_id, conn)
        
        # Encrypt each PHI field if present
        phi_crypto = PHIEncryption()
        
        for field in PHI_FIELDS:
            if field in data and data[field] is not None:
                data[field] = phi_crypto.encrypt_field(data[field], dek)
        
        logger.debug(f"Encrypted patient data for user: {user_id}")
        return data
        
    except Exception as e:
        logger.error(f"Error encrypting patient data for user {user_id}: {str(e)}")
        raise


def decrypt_patient_data(data: Dict[str, Any], user_id: str, conn) -> Dict[str, Any]:
    """
    Decrypt all PHI fields in a patient data dictionary.
    
    Args:
        data: Dictionary containing encrypted patient data
        user_id: User ID who owns this data
        conn: Database connection
        
    Returns:
        Dictionary with PHI fields decrypted
        
    Note:
        Modifies the input dictionary in place and returns it
    """
    try:
        # Get user's DEK
        dek = get_user_dek(user_id, conn)
        
        # Decrypt each PHI field if present
        phi_crypto = PHIEncryption()
        
        for field in PHI_FIELDS:
            if field in data and data[field] is not None:
                # Check if field looks like encrypted data (should be at least 28 bytes after base64 decode)
                # Minimum: 12 bytes IV + 16 bytes auth_tag + at least some ciphertext
                field_value = str(data[field])
                
                # Skip fields that are clearly not encrypted (too short or look like plain dates)
                if len(field_value) < 28:  # Minimum base64 length for encrypted data
                    logger.info(f"[DECRYPT] Skipping field '{field}' - too short to be encrypted data (length: {len(field_value)})")
                    continue
                
                try:
                    data[field] = phi_crypto.decrypt_field(data[field], dek)
                except Exception as field_error:
                    logger.warning(f"[DECRYPT] Could not decrypt field '{field}', leaving as-is. Error: {str(field_error)}")
                    # Leave the field as-is if decryption fails
                    pass
        
        logger.debug(f"Decrypted patient data for user: {user_id}")
        return data
        
    except Exception as e:
        logger.error(f"Error decrypting patient data for user {user_id}: {str(e)}")
        raise


def generate_and_store_user_key(user_id: str, conn, performed_by: Optional[str] = None, 
                                 ip_address: Optional[str] = None) -> Dict[str, Any]:
    """
    Generate a new encryption key for a user and store it in the database.
    
    Args:
        user_id: User ID to generate key for
        conn: Database connection
        performed_by: Admin user ID who initiated this (for audit)
        ip_address: IP address of the request (for audit)
        
    Returns:
        Dict with success status and details
        
    Raises:
        Exception: If key generation or storage fails
    """
    try:
        logger.info(f"Generating encryption key for user: {user_id}")
        
        # Generate DEK
        phi_crypto = PHIEncryption()
        plaintext_dek, encrypted_dek_base64 = phi_crypto.generate_user_dek(user_id)
        
        # Store in database
        with conn.cursor() as cursor:
            cursor.execute("""
                INSERT INTO user_encryption_keys 
                (user_id, encrypted_dek, key_version, created_at, is_active)
                VALUES (%s, %s, 1, NOW(), 1)
                ON DUPLICATE KEY UPDATE 
                    encrypted_dek = VALUES(encrypted_dek),
                    key_version = key_version + 1,
                    rotated_at = NOW()
            """, (user_id, encrypted_dek_base64))
            
            # Log audit entry
            audit_details = {
                'operation': 'generate_key',
                'key_version': 1,
                'timestamp': datetime.now().isoformat()
            }
            
            cursor.execute("""
                INSERT INTO encryption_key_audit 
                (user_id, operation, performed_by, operation_timestamp, details, ip_address)
                VALUES (%s, 'generate', %s, NOW(), %s, %s)
            """, (user_id, performed_by, json.dumps(audit_details), ip_address))
        
        conn.commit()
        
        # Clear cache for this user to ensure fresh key is loaded
        clear_dek_cache(user_id)
        
        logger.info(f"Successfully generated and stored encryption key for user: {user_id}")
        
        return {
            'success': True,
            'user_id': user_id,
            'key_version': 1,
            'message': 'Encryption key generated successfully'
        }
        
    except Exception as e:
        conn.rollback()
        logger.error(f"Error generating encryption key for user {user_id}: {str(e)}")
        
        # Log error to audit
        try:
            with conn.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO encryption_key_audit 
                    (user_id, operation, performed_by, operation_timestamp, details, ip_address)
                    VALUES (%s, 'error', %s, NOW(), %s, %s)
                """, (user_id, performed_by, json.dumps({'error': str(e)}), ip_address))
            conn.commit()
        except:
            pass  # Don't fail on audit logging failure
        
        raise


def get_cache_stats() -> Dict[str, Any]:
    """
    Get statistics about the DEK cache.
    
    Returns:
        Dict with cache statistics
    """
    with _cache_lock:
        total_cached = len(_dek_cache)
        expired_count = 0
        current_time = time.time()
        
        for user_id, (dek, expiry) in list(_dek_cache.items()):
            if expiry < current_time:
                expired_count += 1
        
        return {
            'total_cached': total_cached,
            'expired_count': expired_count,
            'active_count': total_cached - expired_count,
            'cache_ttl_hours': DEK_CACHE_TTL_HOURS
        }


def warm_all_user_deks(conn=None) -> Dict[str, Any]:
    """
    Warm DEK cache by pre-loading all user encryption keys on server startup.
    
    This eliminates cold start latency for all users and reduces KMS API calls.
    With 128GB RAM available, pre-loading all DEKs is memory-efficient (<5MB)
    and provides consistent fast decryption performance for all users.
    
    Args:
        conn: Optional database connection (creates new one if not provided)
        
    Returns:
        Dict with warming results including:
            - total_users: Total users with encryption keys
            - successful: Number successfully loaded
            - failed: Number that failed to load
            - duration_seconds: Time taken to warm cache
            - details: List of per-user results
    """
    start_time = time.time()
    logger.info("Starting DEK cache warming for optimal decryption performance")
    
    results = {
        "total_users": 0,
        "successful": 0,
        "failed": 0,
        "details": [],
        "duration_seconds": 0
    }
    
    # Track whether we need to close connection
    should_close_conn = False
    
    try:
        # Import here to avoid circular dependency
        from core.database import get_db_connection, close_db_connection
        
        # Use provided connection or create new one
        if conn is None:
            conn = get_db_connection()
            should_close_conn = True
        
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            # Get all active users with encryption keys
            cursor.execute("""
                SELECT user_id, encrypted_dek, is_active 
                FROM user_encryption_keys 
                WHERE is_active = 1
                ORDER BY user_id
            """)
            
            user_keys = cursor.fetchall()
            results["total_users"] = len(user_keys)
            
            logger.info(f"Found {results['total_users']} users with encryption keys to warm")
            
            # Pre-load each user's DEK
            for i, user_key in enumerate(user_keys, 1):
                user_id = user_key['user_id']
                
                try:
                    user_start = time.time()
                    
                    # This will decrypt and cache the DEK
                    get_user_dek(user_id, conn, cache=True)
                    
                    user_duration = time.time() - user_start
                    results["successful"] += 1
                    results["details"].append({
                        "user_id": user_id,
                        "status": "success",
                        "duration_ms": round(user_duration * 1000, 2)
                    })
                    
                    # Log progress every 100 users
                    if i % 100 == 0:
                        logger.info(f"DEK cache warming progress: {i}/{results['total_users']} users")
                    
                except Exception as e:
                    results["failed"] += 1
                    results["details"].append({
                        "user_id": user_id,
                        "status": "failed",
                        "error": str(e)
                    })
                    logger.error(f"Failed to warm DEK for user {user_id}: {str(e)}")
        
    except Exception as e:
        logger.error(f"Failed to establish database connection for DEK cache warming: {str(e)}")
        results["failed"] = results.get("total_users", 0)
        
    finally:
        if should_close_conn and conn:
            close_db_connection(conn)
    
    results["duration_seconds"] = round(time.time() - start_time, 2)
    
    # Log warming summary
    if results["failed"] == 0 and results["successful"] > 0:
        logger.info(f"✅ DEK cache warming successful: {results['successful']} user keys loaded in {results['duration_seconds']}s")
    elif results["successful"] > 0:
        logger.warning(f"⚠️ DEK cache warming partial: {results['successful']}/{results['total_users']} keys loaded in {results['duration_seconds']}s")
    else:
        logger.error(f"❌ DEK cache warming failed: No keys loaded")
    
    return results

