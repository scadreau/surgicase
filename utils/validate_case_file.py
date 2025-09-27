# Created: 2025-09-26 14:33:42
# Last Modified: 2025-09-26 17:04:51
# Author: Scott Cadreau

# utils/validate_case_file.py
import io
import logging
from typing import Dict, Any, Optional
from PIL import Image
import pypdf
from utils.s3_case_files import get_s3_case_config, get_s3_case_client
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)

def validate_pdf(file_content: bytes) -> Dict[str, Any]:
    """
    Validate PDF file by attempting to open and read it
    
    Args:
        file_content: PDF file content as bytes
        
    Returns:
        dict: {
            "valid": bool,
            "error": str (if invalid),
            "file_type": "pdf"
        }
    """
    try:
        # Create a BytesIO object from the file content
        pdf_stream = io.BytesIO(file_content)
        
        # Try to open the PDF with pypdf
        pdf_reader = pypdf.PdfReader(pdf_stream)
        
        # Basic validation - check if we can read the number of pages
        num_pages = len(pdf_reader.pages)
        
        # Try to read the first page to ensure it's not corrupted
        if num_pages > 0:
            first_page = pdf_reader.pages[0]
            # Attempt to extract text (this will fail if page is corrupted)
            _ = first_page.extract_text()
        
        logger.info(f"PDF validation successful: {num_pages} pages")
        return {
            "valid": True,
            "file_type": "pdf",
            "pages": num_pages
        }
        
    except Exception as e:
        error_msg = f"PDF validation failed: {str(e)}"
        logger.warning(error_msg)
        return {
            "valid": False,
            "error": error_msg,
            "file_type": "pdf"
        }

def validate_jpeg(file_content: bytes) -> Dict[str, Any]:
    """
    Validate JPEG/JPG file by attempting to open it with PIL
    
    Args:
        file_content: JPEG file content as bytes
        
    Returns:
        dict: {
            "valid": bool,
            "error": str (if invalid),
            "file_type": "jpeg"
        }
    """
    try:
        # Create a BytesIO object from the file content
        image_stream = io.BytesIO(file_content)
        
        # Try to open the image with PIL
        with Image.open(image_stream) as img:
            # Verify the image by loading it
            img.verify()
            
            # Get basic image info
            width, height = img.size
            format_name = img.format
            
        logger.info(f"JPEG validation successful: {width}x{height}, format: {format_name}")
        return {
            "valid": True,
            "file_type": "jpeg",
            "width": width,
            "height": height,
            "format": format_name
        }
        
    except Exception as e:
        error_msg = f"JPEG validation failed: {str(e)}"
        logger.warning(error_msg)
        return {
            "valid": False,
            "error": error_msg,
            "file_type": "jpeg"
        }

def _download_file_for_validation(user_id: str, filename: str) -> Optional[bytes]:
    """
    Download file from S3 for validation purposes
    
    Args:
        user_id: User ID for S3 path construction
        filename: Name of the file to download
        
    Returns:
        bytes: File content if successful, None if failed
    """
    s3_key = None
    try:
        logger.info(f"📡 Getting S3 configuration for file download")
        # Get S3 configuration
        config = get_s3_case_config()
        s3_client = get_s3_case_client(config)
        
        bucket_name = config['bucket_name']
        s3_key = f"{config['source_prefix']}{user_id}/{filename}"
        
        logger.info(f"📡 S3 download details: bucket={bucket_name}, key={s3_key}")
        
        # Download file to memory
        file_obj = io.BytesIO()
        s3_client.download_fileobj(bucket_name, s3_key, file_obj)
        
        # Get the file content
        file_content = file_obj.getvalue()
        
        if len(file_content) == 0:
            logger.error(f"❌ Downloaded file is empty: {s3_key}")
            return None
            
        logger.info(f"✅ S3 download successful: {s3_key} ({len(file_content)} bytes)")
        return file_content
        
    except ClientError as e:
        if e.response['Error']['Code'] == '404':
            logger.warning(f"⚠️ File not found in S3: {s3_key}")
        else:
            logger.error(f"❌ S3 client error downloading {s3_key}: {str(e)}")
        return None
    except Exception as e:
        logger.error(f"❌ Unexpected error downloading {s3_key}: {str(e)}")
        return None

def _delete_invalid_file(user_id: str, filename: str) -> bool:
    """
    Delete invalid file from S3
    
    Args:
        user_id: User ID for S3 path construction
        filename: Name of the file to delete
        
    Returns:
        bool: True if deletion successful, False otherwise
    """
    try:
        # Get S3 configuration
        config = get_s3_case_config()
        s3_client = get_s3_case_client(config)
        
        bucket_name = config['bucket_name']
        s3_key = f"{config['source_prefix']}{user_id}/{filename}"
        
        # Delete the file
        s3_client.delete_object(Bucket=bucket_name, Key=s3_key)
        
        logger.info(f"Successfully deleted invalid file: {s3_key}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to delete invalid file {s3_key}: {str(e)}")
        return False

def validate_case_file(user_id: str, filename: str) -> Dict[str, Any]:
    """
    Validate a case file by downloading from S3 and checking if it can be opened
    
    Args:
        user_id: User ID for S3 path construction
        filename: Name of the file to validate
        
    Returns:
        dict: {
            "valid": bool,
            "filename": str,
            "file_type": str,
            "error": str (if invalid),
            "deleted": bool (if invalid file was deleted)
        }
    """
    try:
        logger.info(f"🔍 VALIDATION START: user_id={user_id}, filename={filename}")
        
        # Determine file type from extension
        filename_lower = filename.lower()
        if filename_lower.endswith('.pdf'):
            expected_type = 'pdf'
            logger.info(f"📄 File type detected: PDF - {filename}")
        elif filename_lower.endswith(('.jpg', '.jpeg')):
            expected_type = 'jpeg'
            logger.info(f"🖼️ File type detected: JPEG - {filename}")
        else:
            # For unsupported types (like PNG), just return valid
            logger.info(f"⚠️ File type not validated (passthrough): {filename}")
            return {
                "valid": True,
                "filename": filename,
                "file_type": "not_validated",
                "message": "File type not validated"
            }
        
        # Download file content
        logger.info(f"⬇️ Downloading file from S3: {filename}")
        file_content = _download_file_for_validation(user_id, filename)
        if file_content is None:
            logger.error(f"❌ VALIDATION FAILED - Download failed: {filename}")
            return {
                "valid": False,
                "filename": filename,
                "file_type": expected_type,
                "error": f"Could not download file {filename} from S3",
                "deleted": False
            }
        
        logger.info(f"✅ Download successful: {filename} ({len(file_content)} bytes)")
        
        # Validate based on file type
        logger.info(f"🔍 Starting {expected_type.upper()} validation: {filename}")
        if expected_type == 'pdf':
            validation_result = validate_pdf(file_content)
        elif expected_type == 'jpeg':
            validation_result = validate_jpeg(file_content)
        
        # Add filename to result
        validation_result["filename"] = filename
        
        # Log validation result
        if validation_result["valid"]:
            logger.info(f"✅ VALIDATION PASSED: {filename} - {expected_type.upper()} is valid")
        else:
            logger.warning(f"❌ VALIDATION FAILED: {filename} - {validation_result.get('error', 'Unknown error')}")
        
        # If validation failed, delete the invalid file
        if not validation_result["valid"]:
            logger.info(f"🗑️ Attempting to delete invalid file: {filename}")
            deleted = _delete_invalid_file(user_id, filename)
            validation_result["deleted"] = deleted
            
            if deleted:
                logger.info(f"✅ Invalid file deleted successfully: {filename}")
            else:
                logger.error(f"❌ Failed to delete invalid file: {filename}")
            
            # Create user-friendly error message
            validation_result["user_error"] = f"File {filename} is not readable and has been removed. Please upload a new file."
        
        logger.info(f"🏁 VALIDATION COMPLETE: {filename} - Result: {'PASS' if validation_result['valid'] else 'FAIL'}")
        return validation_result
        
    except Exception as e:
        error_msg = f"Critical error validating file {filename}: {str(e)}"
        logger.error(error_msg)
        return {
            "valid": False,
            "filename": filename,
            "file_type": "unknown",
            "error": error_msg,
            "deleted": False,
            "user_error": f"File {filename} could not be validated. Please try uploading again."
        }
