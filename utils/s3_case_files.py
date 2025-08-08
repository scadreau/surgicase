# Created: 2025-07-22 18:43:07
# Last Modified: 2025-08-08 15:36:42
# Author: Scott Cadreau

# utils/s3_case_files.py
import boto3
import json
import os
import logging
from typing import Dict, Any, Optional, List
from botocore.exceptions import ClientError, NoCredentialsError

logger = logging.getLogger(__name__)

def get_s3_case_config(secret_name: str = "surgicase/s3-case-documents") -> Dict[str, Any]:
    """
    Fetch S3 case document configuration from AWS Secrets Manager using centralized secrets manager
    """
    try:
        from utils.secrets_manager import get_secret
        return get_secret(secret_name, cache_ttl=300)
    except Exception as e:
        logger.error(f"Error fetching S3 case configuration from Secrets Manager: {str(e)}")
        raise

def get_s3_case_client(config: Dict[str, Any]):
    """
    Create S3 client with configuration for case documents
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
        logger.error(f"Error creating S3 client for case documents: {str(e)}")
        raise

def move_single_file(s3_client, bucket_name: str, source_key: str, dest_key: str) -> Dict[str, Any]:
    """
    Move a single file from source to destination in S3
    
    Args:
        s3_client: Boto3 S3 client
        bucket_name: S3 bucket name
        source_key: Source S3 key
        dest_key: Destination S3 key
        
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
        
        logger.info(f"Successfully moved file from {source_key} to {dest_key}")
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

def move_case_files_to_deleted(
    case_id: str, 
    user_id: str, 
    demo_file: Optional[str] = None,
    note_file: Optional[str] = None,
    misc_file: Optional[str] = None
) -> Dict[str, Any]:
    """
    Move case files from case-documents folder to deleted-case-documents folder
    
    Args:
        case_id: Case ID for logging/tracking
        user_id: User ID to determine file paths
        demo_file: Demo file name (optional)
        note_file: Note file name (optional)
        misc_file: Misc file name (optional)
        
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
        config = get_s3_case_config()
        s3_client = get_s3_case_client(config)
        
        bucket_name = config['bucket_name']
        source_prefix = config['source_prefix']
        dest_prefix = config['destination_prefix']
        
        # Collect files to move
        files_to_move = []
        if demo_file:
            files_to_move.append(("demo_file", demo_file))
        if note_file:
            files_to_move.append(("note_file", note_file))
        if misc_file:
            files_to_move.append(("misc_file", misc_file))
        
        if not files_to_move:
            return {
                "success": True,
                "message": "No files to move",
                "files_moved": 0,
                "details": [],
                "errors": []
            }
        
        # Process each file
        results = []
        errors = []
        successful_moves = 0
        
        for file_type, filename in files_to_move:
            source_key = f"{source_prefix}{user_id}/{filename}"
            dest_key = f"{dest_prefix}{user_id}/{filename}"
            
            result = move_single_file(s3_client, bucket_name, source_key, dest_key)
            results.append({
                "file_type": file_type,
                "filename": filename,
                "result": result
            })
            
            if result["success"]:
                successful_moves += 1
                logger.info(f"Successfully moved {file_type} ({filename}) for case {case_id}")
            else:
                errors.append(f"{file_type} ({filename}): {result['error']}")
                logger.error(f"Failed to move {file_type} ({filename}) for case {case_id}: {result['error']}")
        
        # Check if all files moved successfully
        if successful_moves == len(files_to_move):
            return {
                "success": True,
                "message": f"All {successful_moves} files moved successfully",
                "files_moved": successful_moves,
                "case_id": case_id,
                "user_id": user_id,
                "details": results,
                "errors": []
            }
        else:
            return {
                "success": False,
                "message": f"Failed to move {len(errors)} out of {len(files_to_move)} files",
                "files_moved": successful_moves,
                "case_id": case_id,
                "user_id": user_id,
                "details": results,
                "errors": errors
            }
        
    except Exception as e:
        error_msg = f"Critical error in move_case_files_to_deleted for case {case_id}: {str(e)}"
        logger.error(error_msg)
        return {
            "success": False,
            "message": error_msg,
            "files_moved": 0,
            "case_id": case_id,
            "user_id": user_id,
            "details": [],
            "errors": [error_msg]
        }

def download_file_from_s3(user_id: str, filename: str, local_path: str) -> bool:
    """
    Download a single file from S3 case documents to a local path
    
    Args:
        user_id: User ID to determine S3 path
        filename: Name of the file to download
        local_path: Local file path where the file should be saved
        
    Returns:
        bool: True if download successful, False otherwise
    """
    try:
        # Get S3 configuration
        config = get_s3_case_config()
        s3_client = get_s3_case_client(config)
        
        bucket_name = config['bucket_name']
        # Use source_prefix which should be 'private/case-documents/'
        s3_key = f"{config['source_prefix']}{user_id}/{filename}"
        
        # Ensure local directory exists
        os.makedirs(os.path.dirname(local_path), exist_ok=True)
        
        # Download the file
        s3_client.download_file(bucket_name, s3_key, local_path)
        
        # Verify the file was downloaded and has content
        if os.path.exists(local_path) and os.path.getsize(local_path) > 0:
            logger.info(f"Successfully downloaded {s3_key} to {local_path}")
            return True
        else:
            logger.error(f"Downloaded file {local_path} is empty or doesn't exist")
            return False
            
    except ClientError as e:
        if e.response['Error']['Code'] == '404':
            logger.warning(f"File not found in S3: {s3_key}")
        else:
            logger.error(f"S3 client error downloading {s3_key}: {str(e)}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error downloading {s3_key}: {str(e)}")
        return False 