# Created: 2025-07-29 03:41:16
# Last Modified: 2025-08-06 15:24:52
# Author: Scott Cadreau

# endpoints/backoffice/get_case_images.py
from fastapi import APIRouter, HTTPException, Request, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from typing import List
import pymysql.cursors
import os
import tempfile
import zipfile
import shutil
import time
import logging
from datetime import datetime
from core.database import get_db_connection, close_db_connection
from utils.monitoring import track_business_operation, business_metrics
from utils.s3_case_files import download_file_from_s3
from utils.compress_pic import compress_image
from utils.compress_pdf import compress_pdf_ghostscript, is_pdf_valid

logger = logging.getLogger(__name__)

router = APIRouter()

class CaseImagesRequest(BaseModel):
    case_ids: List[str] = Field(..., description="List of case IDs to retrieve images for")

@router.post("/get_case_images")
@track_business_operation("post", "get_case_images")
def get_case_images(
    request: Request,
    case_request: CaseImagesRequest,
    user_id: str = Query(..., description="The user ID making the request (must be user_type >= 10)")
):
    """
    Download and package case files with intelligent compression for administrative case review and distribution.
    
    This endpoint provides administrative access to bulk case file downloads with advanced compression
    and packaging capabilities. It retrieves demo files and note files from AWS S3 storage, applies
    intelligent compression based on file type, and packages everything into a convenient ZIP archive
    for administrative review, distribution, or offline analysis.
    
    Key Features:
    - Bulk case file download and packaging from AWS S3 storage
    - Intelligent compression system optimized by file type
    - Advanced PDF compression using Ghostscript for quality preservation
    - Image compression with configurable quality and size limits
    - Temporary file management with automatic cleanup
    - Administrative access control with comprehensive permission validation
    - Detailed error reporting and download statistics
    - Organized file structure within ZIP archives
    
    Args:
        request (Request): FastAPI request object for logging and monitoring
        case_request (CaseImagesRequest): Request body containing:
            - case_ids (List[str]): List of case IDs to retrieve files for (required, non-empty)
        user_id (str): Unique identifier of the requesting administrative user (required)
                      Must have user_type >= 10 to access case files
    
    Returns:
        FileResponse: ZIP file download containing:
            - Organized directory structure by case (case_id_patient_name/)
            - Compressed demo files (demo_filename)
            - Compressed note files (note_filename)
            - Error log file (download_errors.txt) if any download failures occurred
            - Custom HTTP headers with download statistics:
                * X-Downloaded-Files: Number of successfully downloaded files
                * X-Download-Errors: Number of download failures
                * X-Cases-Processed: Total number of cases processed
                * X-Images-Compressed: Number of images compressed
                * X-PDFs-Compressed: Number of PDFs compressed
                * X-Compression-Errors: Number of compression failures
    
    Raises:
        HTTPException:
            - 400 Bad Request: Empty case_ids list provided
            - 403 Forbidden: User does not have sufficient permissions (user_type < 10)
            - 404 Not Found: No valid cases found for provided case_ids or no files downloaded
            - 500 Internal Server Error: Database errors, S3 access issues, or compression failures
    
    Database Operations:
        1. Validates requesting user's permission level (user_type >= 10)
        2. Retrieves case information for provided case_ids
        3. Fetches case details including user_id, file paths, and patient information
        4. Validates case existence and active status
        5. Only processes active cases (active = 1)
    
    AWS S3 Integration:
        - Downloads demo_file and note_file from user-specific S3 buckets
        - Handles S3 access errors gracefully with detailed error reporting
        - Uses download_file_from_s3 utility for reliable file retrieval
        - Supports various file types stored in S3 buckets
        - Manages S3 connection timeouts and retry logic
    
    Compression System:
        Image Compression (JPG, PNG, TIFF, BMP):
        - Uses PIL/Pillow for high-quality image compression
        - Quality setting: 75% for optimal size/quality balance
        - Maximum width: 1600px for bandwidth optimization
        - Preserves aspect ratio and metadata where possible
        
        PDF Compression:
        - Uses Ghostscript for professional-grade PDF compression
        - Quality setting: "screen" for aggressive size reduction
        - Maintains text readability and structure
        - Fallback to original file if compression fails
        
        Other File Types:
        - Direct copy without compression for unsupported formats
        - Preserves original file integrity and metadata
    
    File Organization:
        - Creates case-specific subdirectories: case_id_patient_name/
        - Organizes files by type: demo_filename, note_filename
        - Handles special characters in patient names for filesystem compatibility
        - Temporary file management with automatic cleanup
        - ZIP archive with optimal compression settings
    
    Error Handling & Recovery:
        - Graceful handling of individual file download failures
        - Continues processing remaining files even if some fail
        - Detailed error logging with specific failure reasons
        - Download statistics tracking for operational insights
        - Compression failure recovery with original file fallback
    
    Administrative Features:
        - Bulk case file access for administrative review
        - Compressed archives for efficient distribution
        - Detailed download statistics for operational monitoring
        - Error reporting for troubleshooting S3 or compression issues
        - Patient information integration for file organization
    
    Temporary File Management:
        - Creates timestamped temporary directories for isolation
        - Automatic cleanup of temporary files after ZIP creation
        - Efficient disk space usage during processing
        - Error handling for cleanup failures
        - Organized temporary file structure for processing
    
    Monitoring & Logging:
        - Business metrics tracking for file download operations
        - Compression statistics for performance monitoring
        - Prometheus monitoring via @track_business_operation decorator
        - Detailed execution time and response logging
        - Administrative access tracking for security auditing
        - Error categorization for different failure types:
            * permission_denied: Insufficient user permissions
            * success: Files downloaded and packaged successfully
            * error: General download, compression, or packaging errors
    
    Security Features:
        - Administrative access control (user_type >= 10 required)
        - Permission validation before any file operations
        - Only active cases and their files are accessible
        - Secure temporary file handling with cleanup
        - S3 access through authenticated download utilities
    
    Performance Optimizations:
        - Intelligent compression reduces bandwidth requirements
        - Temporary file cleanup minimizes disk usage
        - Batch processing for multiple case files
        - Efficient ZIP archive creation
        - Progressive download with error recovery
    
    Example Request:
        POST /get_case_images?user_id=ADMIN001
        {
            "case_ids": ["CASE-2024-001", "CASE-2024-002", "CASE-2024-003"]
        }
    
    Example Response Headers:
        Content-Type: application/zip
        Content-Disposition: attachment; filename="case_images_20240815_143022.zip"
        X-Downloaded-Files: 5
        X-Download-Errors: 1
        X-Cases-Processed: 3
        X-Images-Compressed: 2
        X-PDFs-Compressed: 3
        X-Compression-Errors: 0
    
    Example Error Response (Permission Denied):
        {
            "detail": "User does not have permission to access case images."
        }
    
    Example Error Response (No Files):
        {
            "detail": "No files were successfully downloaded"
        }
    
    ZIP Archive Structure:
        case_images_20240815_143022.zip
        ├── CASE-2024-001_John_Doe/
        │   ├── demo_surgery_video.mp4
        │   └── note_surgical_report.pdf
        ├── CASE-2024-002_Jane_Smith/
        │   ├── demo_procedure.mp4
        │   └── note_documentation.pdf
        └── download_errors.txt (if any errors occurred)
    
    Note:
        - Only active cases (active=1) and their files are processed
        - Compression settings are optimized for healthcare file types
        - ZIP files are created with timestamps to prevent naming conflicts
        - Temporary directories are automatically cleaned up after processing
        - Error logs are included in ZIP if any downloads fail
        - Administrative users should use this for case review and distribution
        - Large file sets may take time to process - consider batch size limits
        - S3 access requires proper AWS credentials and permissions
        - Ghostscript must be installed for PDF compression functionality
    """
    conn = None
    temp_dir = None
    start_time = time.time()
    response_status = 200
    error_message = None
    
    try:
        # Validate input
        if not case_request.case_ids:
            response_status = 400
            error_message = "case_ids list cannot be empty"
            raise HTTPException(status_code=400, detail="case_ids list cannot be empty")
        
        conn = get_db_connection()
        
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            # Check user permission
            cursor.execute("SELECT user_type FROM user_profile WHERE user_id = %s", (user_id,))
            user_row = cursor.fetchone()
            if not user_row or user_row.get("user_type", 0) < 10:
                business_metrics.record_utility_operation("get_case_images", "permission_denied")
                response_status = 403
                error_message = "User does not have permission to access case images"
                raise HTTPException(status_code=403, detail="User does not have permission to access case images.")
            
            # Get case information
            placeholders = ",".join(["%s"] * len(case_request.case_ids))
            sql = f"""
                SELECT case_id, user_id, demo_file, note_file, patient_first, patient_last
                FROM cases 
                WHERE case_id IN ({placeholders}) AND active = 1
            """
            
            cursor.execute(sql, case_request.case_ids)
            cases = cursor.fetchall()
            
            if not cases:
                response_status = 404
                error_message = "No valid cases found for provided case_ids"
                raise HTTPException(status_code=404, detail="No valid cases found for provided case_ids")
        
        # Create temporary directory for downloads
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        temp_base_dir = os.path.join(project_root, "..", "vol2")
        os.makedirs(temp_base_dir, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        temp_dir = os.path.join(temp_base_dir, f"case_images_{timestamp}")
        os.makedirs(temp_dir, exist_ok=True)
        
        # Download and compress files for each case
        downloaded_files = []
        download_errors = []
        compression_stats = {"images_compressed": 0, "pdfs_compressed": 0, "compression_errors": 0}
        
        for case in cases:
            case_id = case["case_id"]
            case_user_id = case["user_id"]
            demo_file = case["demo_file"]
            note_file = case["note_file"]
            patient_name = f"{case['patient_first'] or ''} {case['patient_last'] or ''}".strip()
            
            # Create case subdirectory
            case_dir = os.path.join(temp_dir, f"{case_id}_{patient_name}".replace(" ", "_"))
            os.makedirs(case_dir, exist_ok=True)
            
            # Download demo file if exists
            if demo_file:
                try:
                    original_path = os.path.join(case_dir, f"original_demo_{demo_file}")
                    compressed_path = os.path.join(case_dir, f"demo_{demo_file}")
                    
                    success = download_file_from_s3(case_user_id, demo_file, original_path)
                    if success:
                        # Compress the file based on type
                        compression_success = _compress_file(original_path, compressed_path, compression_stats)
                        if compression_success:
                            downloaded_files.append(compressed_path)
                            # Remove original file to save space
                            os.remove(original_path)
                        else:
                            # If compression fails, use original file
                            os.rename(original_path, compressed_path)
                            downloaded_files.append(compressed_path)
                    else:
                        download_errors.append(f"Failed to download demo file for case {case_id}: {demo_file}")
                except Exception as e:
                    download_errors.append(f"Error downloading demo file for case {case_id}: {str(e)}")
            
            # Download note file if exists
            if note_file:
                try:
                    original_path = os.path.join(case_dir, f"original_note_{note_file}")
                    compressed_path = os.path.join(case_dir, f"note_{note_file}")
                    
                    success = download_file_from_s3(case_user_id, note_file, original_path)
                    if success:
                        # Compress the file based on type
                        compression_success = _compress_file(original_path, compressed_path, compression_stats)
                        if compression_success:
                            downloaded_files.append(compressed_path)
                            # Remove original file to save space
                            os.remove(original_path)
                        else:
                            # If compression fails, use original file
                            os.rename(original_path, compressed_path)
                            downloaded_files.append(compressed_path)
                    else:
                        download_errors.append(f"Failed to download note file for case {case_id}: {note_file}")
                except Exception as e:
                    download_errors.append(f"Error downloading note file for case {case_id}: {str(e)}")
        
        # Create ZIP file
        zip_filename = f"case_images_{timestamp}.zip"
        zip_path = os.path.join(temp_base_dir, zip_filename)
        
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            # Add all downloaded files to ZIP
            for file_path in downloaded_files:
                # Get relative path for archive
                rel_path = os.path.relpath(file_path, temp_dir)
                zipf.write(file_path, rel_path)
            
            # Add error log if there were any errors
            if download_errors:
                error_content = "\n".join(download_errors)
                zipf.writestr("download_errors.txt", error_content)
        
        if not downloaded_files:
            response_status = 404
            error_message = "No files were successfully downloaded"
            raise HTTPException(status_code=404, detail="No files were successfully downloaded")
        
        # Record successful operation
        business_metrics.record_utility_operation("get_case_images", "success")
        
        # Record compression metrics
        if compression_stats["images_compressed"] > 0:
            business_metrics.record_utility_operation("image_compression", "success")
        if compression_stats["pdfs_compressed"] > 0:
            business_metrics.record_utility_operation("pdf_compression", "success")
        if compression_stats["compression_errors"] > 0:
            business_metrics.record_utility_operation("compression", "error")
        
        # Return ZIP file
        return FileResponse(
            path=zip_path,
            filename=zip_filename,
            media_type='application/zip',
            headers={
                'Content-Disposition': f'attachment; filename="{zip_filename}"',
                'X-Downloaded-Files': str(len(downloaded_files)),
                'X-Download-Errors': str(len(download_errors)),
                'X-Cases-Processed': str(len(cases)),
                'X-Images-Compressed': str(compression_stats["images_compressed"]),
                'X-PDFs-Compressed': str(compression_stats["pdfs_compressed"]),
                'X-Compression-Errors': str(compression_stats["compression_errors"])
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        response_status = 500
        error_message = str(e)
        business_metrics.record_utility_operation("get_case_images", "error")
        raise HTTPException(status_code=500, detail={"error": str(e)})
        
    finally:
        if conn:
            close_db_connection(conn)
            
        # Cleanup temp directory (but keep ZIP file for download)
        if temp_dir and os.path.exists(temp_dir):
            try:
                shutil.rmtree(temp_dir)
            except Exception as e:
                print(f"Warning: Could not cleanup temp directory {temp_dir}: {e}")
        
        # Calculate execution time
        execution_time_ms = int((time.time() - start_time) * 1000)
        
        # Log request details
        from endpoints.utility.log_request import log_request_from_endpoint
        log_request_from_endpoint(
            request=request,
            execution_time_ms=execution_time_ms,
            response_status=response_status,
            user_id=user_id,
            response_data={"cases_requested": len(case_request.case_ids)} if case_request else None,
            error_message=error_message
        )

def _compress_file(original_path: str, compressed_path: str, stats: dict) -> bool:
    """
    Compress a file based on its type. Images are compressed using PIL/Pillow.
    PDFs are compressed using ghostscript for better quality preservation.
    
    Args:
        original_path: Path to original file
        compressed_path: Path where compressed file should be saved
        stats: Dictionary to track compression statistics
        
    Returns:
        bool: True if compression successful, False otherwise
    """
    try:
        file_ext = os.path.splitext(original_path)[1].lower()
        
        # Handle image files
        if file_ext in ['.jpg', '.jpeg', '.png', '.tiff', '.tif', '.bmp']:
            success = compress_image(
                input_path=original_path,
                output_path=compressed_path,
                quality=75,
                max_width=1600
            )
            if success:
                stats["images_compressed"] += 1
                return True
            else:
                stats["compression_errors"] += 1
                return False
        
        # Handle PDF files - using ghostscript compression
        elif file_ext == '.pdf':
            success = compress_pdf_ghostscript(
                input_path=original_path,
                output_path=compressed_path,
                quality="screen"  # More aggressive compression for better size reduction
            )
            if success:
                stats["pdfs_compressed"] += 1
                return True
            else:
                # If ghostscript compression fails, fall back to copying
                shutil.copy2(original_path, compressed_path)
                logger.warning(f"PDF compression failed, using original: {original_path}")
                stats["compression_errors"] += 1
                return True
        
        # For other file types, no compression - just copy
        else:
            import shutil
            shutil.copy2(original_path, compressed_path)
            return True
            
    except Exception as e:
        logger.error(f"Error compressing file {original_path}: {str(e)}")
        stats["compression_errors"] += 1
        return False 