# Created: 2025-07-29 04:32:09
# Last Modified: 2025-07-29 04:37:36
# Author: Scott Cadreau

# utils/compress_pic.py
import os
import logging
from PIL import Image, ImageOps
from typing import Optional, Tuple
import tempfile

logger = logging.getLogger(__name__)

def compress_image(
    input_path: str, 
    output_path: str, 
    quality: int = 75, 
    max_width: int = 1600, 
    max_height: Optional[int] = None,
    preserve_aspect_ratio: bool = True
) -> bool:
    """
    Compress an image using Pillow
    
    Args:
        input_path: Path to the input image file
        output_path: Path where compressed image will be saved
        quality: JPEG quality (1-100, default 75)
        max_width: Maximum width in pixels (default 1600)
        max_height: Maximum height in pixels (None = auto based on aspect ratio)
        preserve_aspect_ratio: Whether to maintain original aspect ratio
        
    Returns:
        bool: True if compression successful, False otherwise
    """
    try:
        # Validate input file exists
        if not os.path.exists(input_path):
            logger.error(f"Input file does not exist: {input_path}")
            return False
        
        # Ensure output directory exists
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        # Open and process image
        with Image.open(input_path) as img:
            # Convert to RGB if necessary (handles RGBA, P, etc.)
            if img.mode not in ('RGB', 'L'):
                if img.mode == 'RGBA':
                    # Create white background for transparent images
                    background = Image.new('RGB', img.size, (255, 255, 255))
                    background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
                    img = background
                else:
                    img = img.convert('RGB')
            
            # Auto-orient image based on EXIF data
            img = ImageOps.exif_transpose(img)
            
            # Calculate new dimensions
            original_width, original_height = img.size
            
            if preserve_aspect_ratio:
                # Calculate scale factor
                width_scale = max_width / original_width if original_width > max_width else 1.0
                height_scale = 1.0
                
                if max_height:
                    height_scale = max_height / original_height if original_height > max_height else 1.0
                
                # Use the smaller scale factor to ensure both dimensions fit
                scale = min(width_scale, height_scale)
                
                new_width = int(original_width * scale)
                new_height = int(original_height * scale)
            else:
                new_width = min(max_width, original_width)
                new_height = max_height if max_height else original_height
            
            # Only resize if image is larger than target dimensions
            if new_width < original_width or new_height < original_height:
                img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
                logger.info(f"Resized image from {original_width}x{original_height} to {new_width}x{new_height}")
            
            # Save with compression
            save_kwargs = {
                'format': 'JPEG',
                'quality': quality,
                'optimize': True
            }
            
            img.save(output_path, **save_kwargs)
            
            # Log compression results
            original_size = os.path.getsize(input_path)
            compressed_size = os.path.getsize(output_path)
            compression_ratio = (1 - compressed_size / original_size) * 100
            
            logger.info(f"Compressed {input_path}: {original_size} -> {compressed_size} bytes "
                       f"({compression_ratio:.1f}% reduction)")
            
            return True
            
    except Exception as e:
        logger.error(f"Error compressing image {input_path}: {str(e)}")
        return False

def compress_image_in_memory(
    input_path: str, 
    quality: int = 75, 
    max_width: int = 1600, 
    max_height: Optional[int] = None
) -> Optional[bytes]:
    """
    Compress an image and return the compressed data as bytes
    
    Args:
        input_path: Path to the input image file
        quality: JPEG quality (1-100, default 75)
        max_width: Maximum width in pixels (default 1600)
        max_height: Maximum height in pixels (None = auto based on aspect ratio)
        
    Returns:
        bytes: Compressed image data, or None if compression failed
    """
    try:
        with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as temp_file:
            temp_path = temp_file.name
        
        # Use the main compression function
        if compress_image(input_path, temp_path, quality, max_width, max_height):
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
        logger.error(f"Error compressing image in memory {input_path}: {str(e)}")
        return None

def get_image_compression_stats(input_path: str, compressed_path: str) -> dict:
    """
    Get compression statistics for an image
    
    Args:
        input_path: Path to original image
        compressed_path: Path to compressed image
        
    Returns:
        dict: Compression statistics
    """
    try:
        if not os.path.exists(input_path) or not os.path.exists(compressed_path):
            return {"error": "One or both files do not exist"}
        
        original_size = os.path.getsize(input_path)
        compressed_size = os.path.getsize(compressed_path)
        compression_ratio = (1 - compressed_size / original_size) * 100
        
        # Get image dimensions
        with Image.open(input_path) as orig_img:
            orig_dimensions = orig_img.size
        
        with Image.open(compressed_path) as comp_img:
            comp_dimensions = comp_img.size
        
        return {
            "original_size_bytes": original_size,
            "compressed_size_bytes": compressed_size,
            "compression_ratio_percent": round(compression_ratio, 2),
            "size_reduction_bytes": original_size - compressed_size,
            "original_dimensions": orig_dimensions,
            "compressed_dimensions": comp_dimensions
        }
        
    except Exception as e:
        logger.error(f"Error getting compression stats: {str(e)}")
        return {"error": str(e)} 