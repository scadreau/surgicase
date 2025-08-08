# Created: 2025-07-22 18:53:59
# Last Modified: 2025-08-08 15:36:43
# Author: Scott Cadreau

# utils/s3_user_files.py
import boto3
import json
import os
import logging
from typing import Dict, Any, Optional, List, Tuple
from botocore.exceptions import ClientError, NoCredentialsError

logger = logging.getLogger(__name__)

def get_s3_user_config(secret_name: str = "surgicase/s3-user-documents") -> Dict[str, Any]:
    """
    Fetch S3 user document configuration from AWS Secrets Manager using centralized secrets manager
    """
    try:
        from utils.secrets_manager import get_secret
        return get_secret(secret_name, cache_ttl=300)
    except Exception as e:
        logger.error(f"Error fetching S3 user configuration from Secrets Manager: {str(e)}")
        raise

def get_s3_user_client(config: Dict[str, Any]):
    """
    Create S3 client with configuration for user documents
    """
    try:
        # Use access keys if provided, otherwise use IAM role
        if 'aws_access_key_id' in config and 'aws_secret_access_key' in config:
            s3_client = boto3.client(
                's3',
                region_name=config['region'],
                aws_access_key_id=config['aws_access_key_id'],
                aws_secret_access_key=config['aws_secret_access_key']
            )
        else:
            # Use IAM role (recommended for production)
            s3_client = boto3.client('s3', region_name=config['region'])
        
        return s3_client
    except Exception as e:
        logger.error(f"Error creating S3 client for user documents: {str(e)}")
        raise

def move_single_user_file(s3_client, bucket_name: str, source_key: str, dest_key: str) -> Dict[str, Any]:
    """
    Move a single user document file from source to destination in S3
    
    Args:
        s3_client: Boto3 S3 client
        bucket_name: S3 bucket name
        source_key: Source S3 key (full path)
        dest_key: Destination S3 key (full path)
        
    Returns:
        dict: Operation result with success status and details
    """
    try:
        # First check if source file exists
        try:
            s3_client.head_object(Bucket=bucket_name, Key=source_key)
        except ClientError as e:
            if e.response['Error']['Code'] == '404':
                return {
                    "success": False,
                    "error": f"Source file not found: {source_key}",
                    "source_key": source_key,
                    "dest_key": dest_key
                }
            else:
                raise
        
        # Copy the file to destination
        copy_source = {'Bucket': bucket_name, 'Key': source_key}
        s3_client.copy_object(
            CopySource=copy_source,
            Bucket=bucket_name,
            Key=dest_key,
            ServerSideEncryption='AES256'
        )
        
        # Verify the copy was successful by checking if destination exists
        try:
            s3_client.head_object(Bucket=bucket_name, Key=dest_key)
        except ClientError:
            return {
                "success": False,
                "error": f"Failed to verify copied file at destination: {dest_key}",
                "source_key": source_key,
                "dest_key": dest_key
            }
        
        # Delete the source file
        s3_client.delete_object(Bucket=bucket_name, Key=source_key)
        
        # Verify source file was deleted
        try:
            s3_client.head_object(Bucket=bucket_name, Key=source_key)
            # If we get here, the file still exists - deletion failed
            return {
                "success": False,
                "error": f"Failed to delete source file after copy: {source_key}",
                "source_key": source_key,
                "dest_key": dest_key
            }
        except ClientError as e:
            if e.response['Error']['Code'] == '404':
                # File successfully deleted
                pass
            else:
                return {
                    "success": False,
                    "error": f"Error verifying source file deletion: {str(e)}",
                    "source_key": source_key,
                    "dest_key": dest_key
                }
        
        logger.info(f"Successfully moved user file from {source_key} to {dest_key}")
        return {
            "success": True,
            "message": f"File moved successfully from {source_key} to {dest_key}",
            "source_key": source_key,
            "dest_key": dest_key
        }
        
    except ClientError as e:
        error_msg = f"S3 operation error moving {source_key} to {dest_key}: {str(e)}"
        logger.error(error_msg)
        return {
            "success": False,
            "error": error_msg,
            "source_key": source_key,
            "dest_key": dest_key
        }
    except Exception as e:
        error_msg = f"Unexpected error moving {source_key} to {dest_key}: {str(e)}"
        logger.error(error_msg)
        return {
            "success": False,
            "error": error_msg,
            "source_key": source_key,
            "dest_key": dest_key
        }

def move_user_documents_to_deleted(
    user_id: str, 
    user_documents: List[Tuple[str, str]] = None
) -> Dict[str, Any]:
    """
    Move user documents from user-documents folder to deleted-user-documents folder
    
    Args:
        user_id: User ID for logging/tracking
        user_documents: List of tuples containing (document_type, document_name/full_path)
        
    Returns:
        dict: {
            "success": bool,
            "message": str,
            "files_moved": int,
            "details": list of individual file results,
            "errors": list of any errors
        }
    """
    try:
        # Get S3 configuration
        config = get_s3_user_config()
        s3_client = get_s3_user_client(config)
        
        bucket_name = config['bucket_name']
        source_prefix = config.get('source_prefix', 'private/user-documents/')
        dest_prefix = config.get('destination_prefix', 'private/deleted-user-documents/')
        
        if not user_documents:
            return {
                "success": True,
                "message": "No user documents to move",
                "files_moved": 0,
                "details": [],
                "errors": []
            }
        
        # Process each document
        results = []
        errors = []
        successful_moves = 0
        
        for document_type, document_name in user_documents:
            # Since document_name contains the full path, we need to handle it properly
            # If it starts with a prefix, use it as is, otherwise construct the path
            if document_name.startswith('private/') or document_name.startswith('/'):
                # Document name is already a full path
                source_key = document_name.lstrip('/')  # Remove leading slash if present
                # Extract just the filename for destination
                filename = document_name.split('/')[-1]
                dest_key = f"{dest_prefix}{user_id}/{filename}"
            else:
                # Document name is just a filename, construct full paths
                source_key = f"{source_prefix}{user_id}/{document_name}"
                dest_key = f"{dest_prefix}{user_id}/{document_name}"
            
            result = move_single_user_file(s3_client, bucket_name, source_key, dest_key)
            results.append({
                "document_type": document_type,
                "document_name": document_name,
                "source_key": source_key,
                "dest_key": dest_key,
                "result": result
            })
            
            if result["success"]:
                successful_moves += 1
                logger.info(f"Successfully moved {document_type} ({document_name}) for user {user_id}")
            else:
                errors.append(f"{document_type} ({document_name}): {result['error']}")
                logger.error(f"Failed to move {document_type} ({document_name}) for user {user_id}: {result['error']}")
        
        # Check if all documents moved successfully
        if successful_moves == len(user_documents):
            return {
                "success": True,
                "message": f"All {successful_moves} user documents moved successfully",
                "files_moved": successful_moves,
                "user_id": user_id,
                "details": results,
                "errors": []
            }
        else:
            return {
                "success": False,
                "message": f"Failed to move {len(errors)} out of {len(user_documents)} user documents",
                "files_moved": successful_moves,
                "user_id": user_id,
                "details": results,
                "errors": errors
            }
        
    except Exception as e:
        error_msg = f"Critical error in move_user_documents_to_deleted for user {user_id}: {str(e)}"
        logger.error(error_msg)
        return {
            "success": False,
            "message": error_msg,
            "files_moved": 0,
            "user_id": user_id,
            "details": [],
            "errors": [error_msg]
        } 