# Created: 2025-08-05 22:48:22
# Last Modified: 2025-08-05 22:53:23
# Author: Scott Cadreau

"""
HIPAA-compliant encryption utility using AWS KMS + AES hybrid approach.

This module provides functionality to:
1. Generate data encryption keys (DEKs) using AWS KMS
2. Encrypt files using AES-256-GCM with generated DEKs
3. Store encrypted DEKs alongside encrypted files
4. Decrypt files by retrieving and decrypting DEKs from KMS
5. Maintain audit trails for HIPAA compliance
"""

import os
import json
import base64
import logging
from typing import Dict, Any, Tuple, Optional
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.backends import default_backend
import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)

class HIPAAEncryption:
    """
    HIPAA-compliant encryption class using AWS KMS + AES hybrid approach.
    """
    
    def __init__(self, kms_key_id: str = None):
        """
        Initialize encryption with KMS key.
        
        Args:
            kms_key_id: AWS KMS key ID/ARN. If None, uses environment default
        """
        self.kms_client = boto3.client('kms')
        self.kms_key_id = kms_key_id or self._get_default_kms_key()
        
    def _get_default_kms_key(self) -> str:
        """
        Get the default KMS key for SurgiCase database encryption.
        Creates one if it doesn't exist.
        """
        try:
            # Try to find existing key by alias
            alias_name = 'alias/surgicase-db-backup-encryption'
            
            try:
                response = self.kms_client.describe_key(KeyId=alias_name)
                return response['KeyMetadata']['KeyId']
            except ClientError as e:
                if e.response['Error']['Code'] != 'NotFoundException':
                    raise
                
            # Key doesn't exist, create it
            logger.info("Creating new KMS key for SurgiCase database backup encryption...")
            
            key_policy = {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Sid": "Enable IAM User Permissions",
                        "Effect": "Allow",
                        "Principal": {"AWS": f"arn:aws:iam::{boto3.client('sts').get_caller_identity()['Account']}:root"},
                        "Action": "kms:*",
                        "Resource": "*"
                    },
                    {
                        "Sid": "Allow SurgiCase backup encryption",
                        "Effect": "Allow",
                        "Principal": {"AWS": boto3.client('sts').get_caller_identity()['Arn']},
                        "Action": [
                            "kms:Encrypt",
                            "kms:Decrypt",
                            "kms:ReEncrypt*",
                            "kms:GenerateDataKey*",
                            "kms:CreateGrant",
                            "kms:DescribeKey"
                        ],
                        "Resource": "*"
                    }
                ]
            }
            
            # Create the key
            create_response = self.kms_client.create_key(
                Description='SurgiCase database backup encryption key for HIPAA compliance',
                Usage='ENCRYPT_DECRYPT',
                KeySpec='SYMMETRIC_DEFAULT',
                Policy=json.dumps(key_policy),
                Tags=[
                    {'TagKey': 'Application', 'TagValue': 'SurgiCase'},
                    {'TagKey': 'Purpose', 'TagValue': 'DatabaseBackupEncryption'},
                    {'TagKey': 'Compliance', 'TagValue': 'HIPAA'}
                ]
            )
            
            key_id = create_response['KeyMetadata']['KeyId']
            
            # Create alias
            self.kms_client.create_alias(
                AliasName=alias_name,
                TargetKeyId=key_id
            )
            
            logger.info(f"Created new KMS key: {key_id} with alias: {alias_name}")
            return key_id
            
        except Exception as e:
            logger.error(f"Error getting/creating KMS key: {str(e)}")
            raise
    
    def generate_data_key(self) -> Tuple[bytes, bytes]:
        """
        Generate a data encryption key using KMS.
        
        Returns:
            Tuple of (plaintext_key, encrypted_key)
        """
        try:
            response = self.kms_client.generate_data_key(
                KeyId=self.kms_key_id,
                KeySpec='AES_256'
            )
            
            return response['Plaintext'], response['CiphertextBlob']
            
        except Exception as e:
            logger.error(f"Error generating data key: {str(e)}")
            raise
    
    def decrypt_data_key(self, encrypted_key: bytes) -> bytes:
        """
        Decrypt a data encryption key using KMS.
        
        Args:
            encrypted_key: Encrypted data key from KMS
            
        Returns:
            Plaintext data key
        """
        try:
            response = self.kms_client.decrypt(CiphertextBlob=encrypted_key)
            return response['Plaintext']
            
        except Exception as e:
            logger.error(f"Error decrypting data key: {str(e)}")
            raise
    
    def encrypt_file(self, input_file_path: str, output_file_path: str, 
                    metadata: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Encrypt a file using AES-256-GCM with KMS-generated key.
        
        Args:
            input_file_path: Path to file to encrypt
            output_file_path: Path for encrypted output file
            metadata: Additional metadata to store with encryption info
            
        Returns:
            Dict with encryption details
        """
        try:
            # Generate data encryption key
            plaintext_key, encrypted_key = self.generate_data_key()
            
            # Generate random IV
            iv = os.urandom(12)  # 96 bits for GCM
            
            # Create cipher
            cipher = Cipher(
                algorithms.AES(plaintext_key),
                modes.GCM(iv),
                backend=default_backend()
            )
            encryptor = cipher.encryptor()
            
            # Encrypt file
            with open(input_file_path, 'rb') as infile:
                with open(output_file_path, 'wb') as outfile:
                    # Read and encrypt in chunks
                    while True:
                        chunk = infile.read(8192)  # 8KB chunks
                        if not chunk:
                            break
                        encrypted_chunk = encryptor.update(chunk)
                        outfile.write(encrypted_chunk)
                    
                    # Finalize and get auth tag
                    encryptor.finalize()
                    auth_tag = encryptor.tag
            
            # Create encryption metadata
            encryption_info = {
                'kms_key_id': self.kms_key_id,
                'encrypted_data_key': base64.b64encode(encrypted_key).decode('utf-8'),
                'iv': base64.b64encode(iv).decode('utf-8'),
                'auth_tag': base64.b64encode(auth_tag).decode('utf-8'),
                'algorithm': 'AES-256-GCM',
                'encrypted_file_size': os.path.getsize(output_file_path),
                'original_file_size': os.path.getsize(input_file_path),
                'metadata': metadata or {}
            }
            
            # Save encryption info alongside encrypted file
            encryption_info_path = f"{output_file_path}.encryption_info"
            with open(encryption_info_path, 'w') as info_file:
                json.dump(encryption_info, info_file, indent=2)
            
            logger.info(f"File encrypted successfully: {output_file_path}")
            logger.info(f"Original size: {encryption_info['original_file_size']:,} bytes")
            logger.info(f"Encrypted size: {encryption_info['encrypted_file_size']:,} bytes")
            
            return {
                'success': True,
                'encrypted_file_path': output_file_path,
                'encryption_info_path': encryption_info_path,
                'encryption_info': encryption_info
            }
            
        except Exception as e:
            logger.error(f"Error encrypting file: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
        finally:
            # Clear sensitive data from memory
            if 'plaintext_key' in locals():
                plaintext_key = b'\x00' * len(plaintext_key)
    
    def decrypt_file(self, encrypted_file_path: str, output_file_path: str) -> Dict[str, Any]:
        """
        Decrypt a file using stored encryption information.
        
        Args:
            encrypted_file_path: Path to encrypted file
            output_file_path: Path for decrypted output file
            
        Returns:
            Dict with decryption results
        """
        try:
            # Load encryption info
            encryption_info_path = f"{encrypted_file_path}.encryption_info"
            if not os.path.exists(encryption_info_path):
                raise FileNotFoundError(f"Encryption info file not found: {encryption_info_path}")
            
            with open(encryption_info_path, 'r') as info_file:
                encryption_info = json.load(info_file)
            
            # Decrypt data key
            encrypted_key = base64.b64decode(encryption_info['encrypted_data_key'])
            plaintext_key = self.decrypt_data_key(encrypted_key)
            
            # Extract encryption parameters
            iv = base64.b64decode(encryption_info['iv'])
            auth_tag = base64.b64decode(encryption_info['auth_tag'])
            
            # Create cipher
            cipher = Cipher(
                algorithms.AES(plaintext_key),
                modes.GCM(iv, auth_tag),
                backend=default_backend()
            )
            decryptor = cipher.decryptor()
            
            # Decrypt file
            with open(encrypted_file_path, 'rb') as infile:
                with open(output_file_path, 'wb') as outfile:
                    # Read and decrypt in chunks
                    while True:
                        chunk = infile.read(8192)  # 8KB chunks
                        if not chunk:
                            break
                        decrypted_chunk = decryptor.update(chunk)
                        outfile.write(decrypted_chunk)
                    
                    # Finalize decryption (verifies auth tag)
                    decryptor.finalize()
            
            # Verify file size
            decrypted_size = os.path.getsize(output_file_path)
            expected_size = encryption_info['original_file_size']
            
            if decrypted_size != expected_size:
                raise ValueError(f"Decrypted file size mismatch. Expected: {expected_size}, Got: {decrypted_size}")
            
            logger.info(f"File decrypted successfully: {output_file_path}")
            logger.info(f"Decrypted size: {decrypted_size:,} bytes")
            
            return {
                'success': True,
                'decrypted_file_path': output_file_path,
                'original_file_size': expected_size,
                'encryption_info': encryption_info
            }
            
        except Exception as e:
            logger.error(f"Error decrypting file: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
        finally:
            # Clear sensitive data from memory
            if 'plaintext_key' in locals():
                plaintext_key = b'\x00' * len(plaintext_key)

def encrypt_backup_file(file_path: str, metadata: Dict[str, Any] = None) -> Dict[str, Any]:
    """
    Convenience function to encrypt a backup file.
    
    Args:
        file_path: Path to file to encrypt
        metadata: Additional metadata for the encryption
        
    Returns:
        Dict with encryption results
    """
    encryptor = HIPAAEncryption()
    encrypted_file_path = f"{file_path}.encrypted"
    
    return encryptor.encrypt_file(
        input_file_path=file_path,
        output_file_path=encrypted_file_path,
        metadata=metadata
    )

def decrypt_backup_file(encrypted_file_path: str, output_file_path: str = None) -> Dict[str, Any]:
    """
    Convenience function to decrypt a backup file.
    
    Args:
        encrypted_file_path: Path to encrypted file
        output_file_path: Path for decrypted file (optional, defaults to removing .encrypted)
        
    Returns:
        Dict with decryption results
    """
    if output_file_path is None:
        if encrypted_file_path.endswith('.encrypted'):
            output_file_path = encrypted_file_path[:-10]  # Remove .encrypted
        else:
            output_file_path = f"{encrypted_file_path}.decrypted"
    
    encryptor = HIPAAEncryption()
    return encryptor.decrypt_file(encrypted_file_path, output_file_path)