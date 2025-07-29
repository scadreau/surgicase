# Created: 2025-07-17 10:30:00
# Last Modified: 2025-07-29 02:13:17
# Author: Scott Cadreau

# utils/s3_storage.py
import boto3
import json
import os
import logging
from datetime import datetime
from typing import Optional, Dict, Any
from botocore.exceptions import ClientError, NoCredentialsError

logger = logging.getLogger(__name__)

def get_s3_config(secret_name: str = "surgicase/s3-user-reports") -> Dict[str, Any]:
    """
    Fetch S3 configuration from AWS Secrets Manager
    """
    try:
        region = os.environ.get("AWS_REGION", "us-east-1")
        client = boto3.client("secretsmanager", region_name=region)
        response = client.get_secret_value(SecretId=secret_name)
        secret = json.loads(response["SecretString"])
        return secret
    except Exception as e:
        logger.error(f"Error fetching S3 configuration from Secrets Manager: {str(e)}")
        raise

def get_s3_client(config: Dict[str, Any]):
    """
    Create S3 client with configuration
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
        logger.error(f"Error creating S3 client: {str(e)}")
        raise

def upload_file_to_s3(
    file_path: str, 
    s3_key: str, 
    content_type: str = 'application/pdf',
    metadata: Optional[Dict[str, str]] = None
) -> Dict[str, Any]:
    """
    Upload a file to S3
    
    Args:
        file_path: Local path to the file
        s3_key: S3 object key (path in bucket)
        content_type: MIME type of the file
        metadata: Optional metadata to attach to the object
        
    Returns:
        dict: {
            "success": bool,
            "s3_url": str,
            "s3_key": str,
            "message": str
        }
    """
    try:
        # Get S3 configuration
        config = get_s3_config()
        s3_client = get_s3_client(config)
        
        # Prepare metadata
        extra_args = {
            'ContentType': content_type,
            'ServerSideEncryption': config.get('encryption', 'AES256')
        }
        
        if metadata:
            extra_args['Metadata'] = metadata
        
        # Upload file
        s3_client.upload_file(
            file_path,
            config['bucket_name'],
            s3_key,
            ExtraArgs=extra_args
        )
        
        # Generate S3 URL
        s3_url = f"https://{config['bucket_name']}.s3.{config['region']}.amazonaws.com/{s3_key}"
        
        logger.info(f"Successfully uploaded {file_path} to S3: {s3_url}")
        
        return {
            "success": True,
            "s3_url": s3_url,
            "s3_key": s3_key,
            "message": f"File uploaded successfully to S3: {s3_url}"
        }
        
    except FileNotFoundError:
        error_msg = f"File not found: {file_path}"
        logger.error(error_msg)
        return {
            "success": False,
            "s3_url": None,
            "s3_key": s3_key,
            "message": error_msg
        }
    except NoCredentialsError:
        error_msg = "AWS credentials not found"
        logger.error(error_msg)
        return {
            "success": False,
            "s3_url": None,
            "s3_key": s3_key,
            "message": error_msg
        }
    except ClientError as e:
        error_msg = f"S3 upload error: {str(e)}"
        logger.error(error_msg)
        return {
            "success": False,
            "s3_url": None,
            "s3_key": s3_key,
            "message": error_msg
        }
    except Exception as e:
        error_msg = f"Unexpected error uploading to S3: {str(e)}"
        logger.error(error_msg)
        return {
            "success": False,
            "s3_url": None,
            "s3_key": s3_key,
            "message": error_msg
        }

def generate_s3_key(
    file_type: str, 
    filename: str, 
    folder_prefix: Optional[str] = None
) -> str:
    """
    Generate S3 key for file storage
    
    Args:
        file_type: Type of report (e.g., 'provider-payment', 'pay-calculation')
        filename: Original filename
        folder_prefix: Optional folder prefix override
        
    Returns:
        str: S3 object key
    """
    try:
        config = get_s3_config()
        base_prefix = folder_prefix or config.get('folder_prefix', 'reports/')
        
        # Ensure folder prefix ends with slash
        if not base_prefix.endswith('/'):
            base_prefix += '/'
        
        # Add timestamp for uniqueness
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Create S3 key
        if file_type:
            s3_key = f"{base_prefix}{file_type}/{timestamp}_{filename}"
        else:
            s3_key = f"{base_prefix}{timestamp}_{filename}"
        
        return s3_key
        
    except Exception as e:
        logger.error(f"Error generating S3 key: {str(e)}")
        # Fallback to simple key
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        if file_type:
            return f"reports/{file_type}/{timestamp}_{filename}"
        else:
            return f"reports/{timestamp}_{filename}"

def delete_file_from_s3(s3_key: str) -> Dict[str, Any]:
    """
    Delete a file from S3
    
    Args:
        s3_key: S3 object key to delete
        
    Returns:
        dict: {
            "success": bool,
            "message": str
        }
    """
    try:
        config = get_s3_config()
        s3_client = get_s3_client(config)
        
        s3_client.delete_object(
            Bucket=config['bucket_name'],
            Key=s3_key
        )
        
        logger.info(f"Successfully deleted file from S3: {s3_key}")
        
        return {
            "success": True,
            "message": f"File deleted successfully from S3: {s3_key}"
        }
        
    except ClientError as e:
        error_msg = f"S3 delete error: {str(e)}"
        logger.error(error_msg)
        return {
            "success": False,
            "message": error_msg
        }
    except Exception as e:
        error_msg = f"Unexpected error deleting from S3: {str(e)}"
        logger.error(error_msg)
        return {
            "success": False,
            "message": error_msg
        }

def get_file_metadata(s3_key: str) -> Dict[str, Any]:
    """
    Get metadata for a file in S3
    
    Args:
        s3_key: S3 object key
        
    Returns:
        dict: File metadata or error information
    """
    try:
        config = get_s3_config()
        s3_client = get_s3_client(config)
        
        response = s3_client.head_object(
            Bucket=config['bucket_name'],
            Key=s3_key
        )
        
        return {
            "success": True,
            "metadata": {
                "content_type": response.get('ContentType'),
                "content_length": response.get('ContentLength'),
                "last_modified": response.get('LastModified'),
                "etag": response.get('ETag'),
                "server_side_encryption": response.get('ServerSideEncryption'),
                "custom_metadata": response.get('Metadata', {})
            }
        }
        
    except ClientError as e:
        error_code = e.response['Error']['Code']
        if error_code == '404':
            return {
                "success": False,
                "message": f"File not found in S3: {s3_key}"
            }
        else:
            return {
                "success": False,
                "message": f"S3 error: {str(e)}"
            }
    except Exception as e:
        return {
            "success": False,
            "message": f"Unexpected error: {str(e)}"
        } 