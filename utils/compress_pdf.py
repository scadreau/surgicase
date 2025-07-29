# Created: 2025-07-29 04:32:53
# Last Modified: 2025-07-29 06:35:53
# Author: Scott Cadreau

# utils/compress_pdf.py
import os
import logging
import fitz  # PyMuPDF
from typing import Dict, Any, Optional
import tempfile
import subprocess
import shutil

logger = logging.getLogger(__name__)

def compress_pdf(
    input_path: str,
    output_path: str,
    compression_level: str = "medium",
    image_quality: int = 75,
    image_max_width: int = 1600,
    remove_annotations: bool = False,
    remove_links: bool = False,
    safe_mode: bool = True
) -> bool:
    """
    Compress a PDF using PyMuPDF
    
    Args:
        input_path: Path to the input PDF file
        output_path: Path where compressed PDF will be saved
        compression_level: "low", "medium", "high", or "maximum" compression
        image_quality: JPEG quality for images (1-100, default 75)
        image_max_width: Maximum width for images in pixels (default 1600)
        remove_annotations: Whether to remove annotations (default False)
        remove_links: Whether to remove hyperlinks (default False)
        safe_mode: If True, skip aggressive image compression to prevent corruption (default True)
        
    Returns:
        bool: True if compression successful, False otherwise
    """
    try:
        # Validate input file exists
        if not os.path.exists(input_path):
            logger.error(f"Input PDF file does not exist: {input_path}")
            return False
        
        # Ensure output directory exists
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        # Open PDF document
        doc = fitz.open(input_path)
        
        # Set compression parameters based on level
        compression_params = _get_compression_params(compression_level)
        
        # Process each page
        for page_num in range(len(doc)):
            page = doc.load_page(page_num)
            
            # Remove annotations if requested
            if remove_annotations:
                annots = page.annots()
                for annot in annots:
                    page.delete_annot(annot)
            
            # Remove links if requested
            if remove_links:
                links = page.get_links()
                for link in links:
                    page.delete_link(link)
            
            # Compress images on the page (only if not in safe mode)
            if not safe_mode:
                _compress_page_images(page, image_quality, image_max_width)
        
        # Save with compression
        doc.save(
            output_path,
            garbage=compression_params["garbage"],
            clean=compression_params["clean"], 
            deflate=compression_params["deflate"],
            deflate_images=compression_params["deflate_images"],
            deflate_fonts=compression_params["deflate_fonts"]
        )
        
        doc.close()
        
        # Log compression results
        original_size = os.path.getsize(input_path)
        compressed_size = os.path.getsize(output_path)
        compression_ratio = (1 - compressed_size / original_size) * 100
        
        logger.info(f"Compressed PDF {input_path}: {original_size} -> {compressed_size} bytes "
                   f"({compression_ratio:.1f}% reduction)")
        
        return True
        
    except Exception as e:
        logger.error(f"Error compressing PDF {input_path}: {str(e)}")
        return False

def _get_compression_params(compression_level: str) -> Dict[str, Any]:
    """
    Get compression parameters based on compression level
    
    Args:
        compression_level: "low", "medium", "high", or "maximum"
        
    Returns:
        dict: Compression parameters for PyMuPDF
    """
    params = {
        "low": {
            "garbage": 1,
            "clean": True,
            "deflate": True,
            "deflate_images": False,
            "deflate_fonts": False
        },
        "medium": {
            "garbage": 2,
            "clean": True,
            "deflate": True,
            "deflate_images": True,
            "deflate_fonts": True
        },
        "high": {
            "garbage": 3,
            "clean": True,
            "deflate": True,
            "deflate_images": True,
            "deflate_fonts": True
        },
        "maximum": {
            "garbage": 4,
            "clean": True,
            "deflate": True,
            "deflate_images": True,
            "deflate_fonts": True
        }
    }
    
    return params.get(compression_level, params["medium"])

def _compress_page_images(page, image_quality: int, max_width: int) -> None:
    """
    Compress images on a PDF page
    
    WARNING: This function can corrupt PDFs by modifying embedded images.
    Use with caution and always test thoroughly. Consider using safe_mode=True instead.
    
    Args:
        page: PyMuPDF page object
        image_quality: JPEG quality (1-100)
        max_width: Maximum width for images
    """
    try:
        # Get all images on the page
        image_list = page.get_images()
        
        for img_index, img in enumerate(image_list):
            # Get image data
            xref = img[0]
            base_image = page.parent.extract_image(xref)
            image_bytes = base_image["image"]
            image_ext = base_image["ext"]
            
            # Only compress if it's a supported format and large enough
            if image_ext in ["png", "jpeg", "jpg"] and len(image_bytes) > 10000:  # 10KB threshold
                try:
                    # Use Pillow for compression
                    from PIL import Image
                    import io
                    
                    # Load image from bytes
                    img_pil = Image.open(io.BytesIO(image_bytes))
                    
                    # Resize if necessary
                    if img_pil.width > max_width:
                        ratio = max_width / img_pil.width
                        new_height = int(img_pil.height * ratio)
                        img_pil = img_pil.resize((max_width, new_height), Image.Resampling.LANCZOS)
                    
                    # Convert to RGB if necessary
                    if img_pil.mode not in ('RGB', 'L'):
                        if img_pil.mode == 'RGBA':
                            background = Image.new('RGB', img_pil.size, (255, 255, 255))
                            background.paste(img_pil, mask=img_pil.split()[-1])
                            img_pil = background
                        else:
                            img_pil = img_pil.convert('RGB')
                    
                    # Save compressed image to bytes
                    img_buffer = io.BytesIO()
                    img_pil.save(img_buffer, format='JPEG', quality=image_quality, optimize=True)
                    compressed_bytes = img_buffer.getvalue()
                    
                    # Replace image in PDF only if compression was beneficial
                    if len(compressed_bytes) < len(image_bytes):
                        page.parent.update_stream(xref, compressed_bytes)
                        logger.debug(f"Compressed image {img_index}: {len(image_bytes)} -> {len(compressed_bytes)} bytes")
                    
                except Exception as img_error:
                    logger.warning(f"Could not compress image {img_index}: {str(img_error)}")
                    continue
                    
    except Exception as e:
        logger.warning(f"Error processing images on page: {str(e)}")

def compress_pdf_in_memory(
    input_path: str,
    compression_level: str = "medium",
    image_quality: int = 75,
    safe_mode: bool = True
) -> Optional[bytes]:
    """
    Compress a PDF and return the compressed data as bytes
    
    Args:
        input_path: Path to the input PDF file
        compression_level: "low", "medium", "high", or "maximum" compression
        image_quality: JPEG quality for images (1-100, default 75)
        safe_mode: If True, skip aggressive image compression to prevent corruption (default True)
        
    Returns:
        bytes: Compressed PDF data, or None if compression failed
    """
    try:
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as temp_file:
            temp_path = temp_file.name
        
        # Use the main compression function
        if compress_pdf(input_path, temp_path, compression_level, image_quality, safe_mode=safe_mode):
            with open(temp_path, 'rb') as f:
                compressed_data = f.read()
            
            # Clean up temp file
            os.unlink(temp_path)
            return compressed_data
        else:
            # Clean up temp file on failure
            if os.path.exists(temp_path):
                os.unlink(temp_path)
            return None
            
    except Exception as e:
        logger.error(f"Error compressing PDF in memory {input_path}: {str(e)}")
        return None

def get_pdf_compression_stats(input_path: str, compressed_path: str) -> dict:
    """
    Get compression statistics for a PDF
    
    Args:
        input_path: Path to original PDF
        compressed_path: Path to compressed PDF
        
    Returns:
        dict: Compression statistics
    """
    try:
        if not os.path.exists(input_path) or not os.path.exists(compressed_path):
            return {"error": "One or both files do not exist"}
        
        original_size = os.path.getsize(input_path)
        compressed_size = os.path.getsize(compressed_path)
        compression_ratio = (1 - compressed_size / original_size) * 100
        
        # Get PDF page counts
        try:
            orig_doc = fitz.open(input_path)
            comp_doc = fitz.open(compressed_path)
            
            orig_pages = len(orig_doc)
            comp_pages = len(comp_doc)
            
            orig_doc.close()
            comp_doc.close()
            
        except Exception:
            orig_pages = comp_pages = "unknown"
        
        return {
            "original_size_bytes": original_size,
            "compressed_size_bytes": compressed_size,
            "compression_ratio_percent": round(compression_ratio, 2),
            "size_reduction_bytes": original_size - compressed_size,
            "original_pages": orig_pages,
            "compressed_pages": comp_pages
        }
        
    except Exception as e:
        logger.error(f"Error getting PDF compression stats: {str(e)}")
        return {"error": str(e)}

def compress_pdf_safe(input_path: str, output_path: str) -> bool:
    """
    Safely compress a PDF using only document-level compression
    without modifying embedded images (prevents corruption)
    
    Args:
        input_path: Path to the input PDF file
        output_path: Path where compressed PDF will be saved
        
    Returns:
        bool: True if compression successful, False otherwise
    """
    try:
        # Validate input file exists
        if not os.path.exists(input_path):
            logger.error(f"Input PDF file does not exist: {input_path}")
            return False
        
        # Ensure output directory exists
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        # Open PDF document
        doc = fitz.open(input_path)
        
        # Save with safe compression settings (no image manipulation)
        doc.save(
            output_path,
            garbage=3,  # Remove unused objects
            clean=True,  # Clean up document structure
            deflate=True,  # Compress streams
            deflate_images=False,  # Don't touch images - this prevents corruption
            deflate_fonts=True  # Compress fonts safely
        )
        
        doc.close()
        
        # Verify the compressed PDF is readable
        if not is_pdf_valid(output_path):
            logger.error(f"Compressed PDF is corrupted: {output_path}")
            return False
        
        # Log compression results
        original_size = os.path.getsize(input_path)
        compressed_size = os.path.getsize(output_path)
        compression_ratio = (1 - compressed_size / original_size) * 100
        
        logger.info(f"Safely compressed PDF {input_path}: {original_size} -> {compressed_size} bytes "
                   f"({compression_ratio:.1f}% reduction)")
        
        return True
        
    except Exception as e:
        logger.error(f"Error safely compressing PDF {input_path}: {str(e)}")
        return False

def is_pdf_valid(file_path: str) -> bool:
    """
    Check if a file is a valid PDF
    
    Args:
        file_path: Path to the PDF file
        
    Returns:
        bool: True if valid PDF, False otherwise
    """
    try:
        doc = fitz.open(file_path)
        doc.close()
        return True
    except Exception:
        return False

def compress_pdf_ghostscript(
    input_path: str,
    output_path: str,
    quality: str = "ebook",
    dpi: int = 150
) -> bool:
    """
    Compress a PDF using ghostscript command line tool.
    This is often more reliable than PyMuPDF for maintaining quality.
    
    Args:
        input_path: Path to the input PDF file
        output_path: Path where compressed PDF will be saved
        quality: Compression quality setting:
                - "screen": Low quality, smallest size (72 dpi images)
                - "ebook": Medium quality, good for web viewing (150 dpi images)
                - "printer": High quality, good for printing (300 dpi images) 
                - "prepress": Highest quality, largest size (300 dpi, color preservation)
        dpi: Custom DPI for image downsampling (overrides quality preset)
        
    Returns:
        bool: True if compression successful, False otherwise
    """
    try:
        # Validate input file exists
        if not os.path.exists(input_path):
            logger.error(f"Input PDF file does not exist: {input_path}")
            return False
            
        # Ensure output directory exists
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        # Check if ghostscript is available
        try:
            subprocess.run(['gs', '--version'], capture_output=True, check=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            logger.error("Ghostscript is not available on this system")
            return False
        
        # Build ghostscript command
        gs_cmd = [
            'gs',
            '-sDEVICE=pdfwrite',
            '-dCompatibilityLevel=1.4',
            '-dPDFSETTINGS=/' + quality,
            '-dNOPAUSE',
            '-dQUIET',
            '-dBATCH',
            f'-dColorImageDownsampleType=/Bicubic',
            f'-dColorImageResolution={dpi}',
            f'-dGrayImageDownsampleType=/Bicubic', 
            f'-dGrayImageResolution={dpi}',
            f'-dMonoImageDownsampleType=/Bicubic',
            f'-dMonoImageResolution={dpi}',
            f'-sOutputFile={output_path}',
            input_path
        ]
        
        # Execute ghostscript command
        result = subprocess.run(
            gs_cmd,
            capture_output=True,
            text=True,
            timeout=300  # 5 minute timeout
        )
        
        if result.returncode != 0:
            logger.error(f"Ghostscript compression failed: {result.stderr}")
            return False
            
        # Verify output file was created and is valid
        if not os.path.exists(output_path):
            logger.error(f"Ghostscript did not create output file: {output_path}")
            return False
            
        if not is_pdf_valid(output_path):
            logger.error(f"Ghostscript produced invalid PDF: {output_path}")
            return False
        
        # Log compression results
        original_size = os.path.getsize(input_path)
        compressed_size = os.path.getsize(output_path)
        compression_ratio = (1 - compressed_size / original_size) * 100
        
        logger.info(f"Ghostscript compressed PDF {input_path}: {original_size} -> {compressed_size} bytes "
                   f"({compression_ratio:.1f}% reduction) using quality='{quality}'")
        
        return True
        
    except subprocess.TimeoutExpired:
        logger.error(f"Ghostscript compression timed out for {input_path}")
        return False
    except Exception as e:
        logger.error(f"Error compressing PDF with ghostscript {input_path}: {str(e)}")
        return False

def get_ghostscript_version() -> Optional[str]:
    """
    Get the installed ghostscript version
    
    Returns:
        str: Version string if ghostscript is available, None otherwise
    """
    try:
        result = subprocess.run(['gs', '--version'], capture_output=True, text=True, check=True)
        return result.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None 