# Created: 2025-07-29 03:41:16
# Last Modified: 2025-07-29 04:50:43
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
from datetime import datetime
from core.database import get_db_connection, close_db_connection
from utils.monitoring import track_business_operation, business_metrics
from utils.s3_case_files import download_file_from_s3
from utils.compress_pic import compress_image
from utils.compress_pdf import compress_pdf_safe, is_pdf_valid

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
    Retrieve case images for specified case IDs and return as ZIP file.
    Downloads demo_file and note_file from S3 for each case and packages them into a ZIP.
    Only accessible to users with user_type >= 10.
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
    Compress a file based on its type (image or PDF)
    
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
        
        # Handle PDF files
        elif file_ext == '.pdf':
            # Validate it's a proper PDF first
            if is_pdf_valid(original_path):
                success = compress_pdf_safe(
                    input_path=original_path,
                    output_path=compressed_path
                )
                if success:
                    stats["pdfs_compressed"] += 1
                    return True
                else:
                    stats["compression_errors"] += 1
                    return False
            else:
                # Invalid PDF, skip compression
                stats["compression_errors"] += 1
                return False
        
        # For other file types, no compression - just copy
        else:
            import shutil
            shutil.copy2(original_path, compressed_path)
            return True
            
    except Exception as e:
        logger.error(f"Error compressing file {original_path}: {str(e)}")
        stats["compression_errors"] += 1
        return False 