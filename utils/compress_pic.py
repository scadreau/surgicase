# Created: 2025-07-29 04:32:09
# Last Modified: 2025-08-20 08:38:53
# Author: Scott Cadreau

# utils/compress_pic.py
import os
import logging
from PIL import Image, ImageOps
from typing import Optional, Tuple
import tempfile

logger = logging.getLogger(__name__)

def get_compression_mode() -> str:
    """
    Get compression mode from AWS Secrets Manager main configuration
    
    Returns:
        str: "aggressive" or "normal" (defaults to "normal" if not found)
    """
    try:
        from utils.secrets_manager import get_secret_value
        compression_mode = get_secret_value("surgicase/main", "COMPRESSION_MODE")
        return compression_mode.lower() if compression_mode else "normal"
    except Exception as e:
        logger.warning(f"Could not fetch compression mode from secrets, using 'normal': {str(e)}")
        return "normal"

def compress_image(
    input_path: str, 
    output_path: str, 
    quality: int = 75, 
    max_width: int = 1600, 
    max_height: Optional[int] = None,
    preserve_aspect_ratio: bool = True,
    use_compression_mode: bool = True
) -> bool:
    """
    Compress an image using Pillow with configurable compression modes
    
    Args:
        input_path: Path to the input image file
        output_path: Path where compressed image will be saved
        quality: JPEG quality (1-100, default 75)
        max_width: Maximum width in pixels (default 1600)
        max_height: Maximum height in pixels (None = auto based on aspect ratio)
        preserve_aspect_ratio: Whether to maintain original aspect ratio
        use_compression_mode: Whether to override settings based on COMPRESSION_MODE secret
        
    Returns:
        bool: True if compression successful, False otherwise
    """
    try:
        # Validate input file exists
        if not os.path.exists(input_path):
            logger.error(f"Input file does not exist: {input_path}")
            return False
        
        # Override settings based on compression mode if enabled
        compression_mode = "normal"  # Default
        if use_compression_mode:
            compression_mode = get_compression_mode()
            if compression_mode == "aggressive":
                # Get file size for size-based aggressive settings
                file_size = os.path.getsize(input_path)
                
                # Aggressive settings: lower quality and smaller dimensions
                if file_size > 10 * 1024 * 1024:  # > 10MB
                    quality = 40
                    max_width = 800
                elif file_size > 5 * 1024 * 1024:  # > 5MB
                    quality = 50
                    max_width = 1000
                else:
                    quality = 60
                    max_width = 1200
                
                logger.info(f"Using aggressive compression mode for image: {input_path} "
                           f"(quality={quality}, max_width={max_width})")
            else:
                logger.info(f"Using normal compression mode for image: {input_path}")
        
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
                # Use more aggressive resampling in aggressive mode
                if use_compression_mode and compression_mode == "aggressive":
                    resampling_method = Image.Resampling.BICUBIC  # Faster, smaller files
                else:
                    resampling_method = Image.Resampling.LANCZOS  # Higher quality
                
                img = img.resize((new_width, new_height), resampling_method)
                logger.info(f"Resized image from {original_width}x{original_height} to {new_width}x{new_height}")
            
            # Save with compression - more aggressive settings in aggressive mode
            save_kwargs = {
                'format': 'JPEG',
                'quality': quality,
                'optimize': True
            }
            
            # Add progressive JPEG and strip metadata in aggressive mode
            if use_compression_mode and compression_mode == "aggressive":
                save_kwargs.update({
                    'progressive': True,      # Progressive JPEG for better compression
                    'exif': b'',             # Strip EXIF metadata
                    'icc_profile': None      # Remove color profile
                })
            
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