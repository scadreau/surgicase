# Created: 2025-07-17 11:36:00
# Last Modified: 2025-07-17 11:36:29

# utils/logo_manager.py
import os
from typing import Optional, Dict, Tuple
from pathlib import Path

class LogoManager:
    """Utility class for managing logos in PDF reports"""
    
    # Default logo configurations for different report types
    DEFAULT_LOGOS = {
        'provider_payment': {
            'path': 'assets/logos/company_logo.png',
            'width': 30,
            'height': 15,
            'x': 10,
            'y': 10
        },
        'case_report': {
            'path': 'assets/logos/company_logo.png',
            'width': 25,
            'height': 12,
            'x': 15,
            'y': 15
        },
        'summary_report': {
            'path': 'assets/logos/company_logo.png',
            'width': 35,
            'height': 18,
            'x': 8,
            'y': 8
        }
    }
    
    @staticmethod
    def get_logo_config(report_type: str = 'default') -> Dict:
        """
        Get logo configuration for a specific report type.
        
        Args:
            report_type: Type of report ('provider_payment', 'case_report', etc.)
            
        Returns:
            Dictionary with logo configuration
        """
        # Check environment variable first
        env_logo_path = os.getenv('REPORT_LOGO_PATH')
        if env_logo_path:
            return {
                'path': env_logo_path,
                'width': int(os.getenv('REPORT_LOGO_WIDTH', 30)),
                'height': int(os.getenv('REPORT_LOGO_HEIGHT', 15)),
                'x': float(os.getenv('REPORT_LOGO_X', 10)),
                'y': float(os.getenv('REPORT_LOGO_Y', 10))
            }
        
        # Fall back to default configurations
        return LogoManager.DEFAULT_LOGOS.get(report_type, LogoManager.DEFAULT_LOGOS['provider_payment'])
    
    @staticmethod
    def validate_logo_path(logo_path: str) -> bool:
        """
        Validate if a logo file exists and is a supported format.
        
        Args:
            logo_path: Path to the logo file
            
        Returns:
            True if logo is valid, False otherwise
        """
        if not logo_path:
            return False
            
        # Check if file exists
        if not os.path.exists(logo_path):
            return False
        
        # Check file extension
        supported_formats = ['.png', '.jpg', '.jpeg', '.gif', '.bmp']
        file_ext = Path(logo_path).suffix.lower()
        
        return file_ext in supported_formats
    
    @staticmethod
    def get_logo_path(report_type: str = 'default') -> Optional[str]:
        """
        Get the logo path for a report type, with validation.
        
        Args:
            report_type: Type of report
            
        Returns:
            Valid logo path or None if not found/valid
        """
        config = LogoManager.get_logo_config(report_type)
        logo_path = config.get('path')
        
        if logo_path and LogoManager.validate_logo_path(logo_path):
            return logo_path
        
        return None
    
    @staticmethod
    def create_logo_directory() -> str:
        """
        Create the default logo directory if it doesn't exist.
        
        Returns:
            Path to the logo directory
        """
        logo_dir = Path('assets/logos')
        logo_dir.mkdir(parents=True, exist_ok=True)
        return str(logo_dir)
    
    @staticmethod
    def list_available_logos() -> list:
        """
        List all available logo files in the assets/logos directory.
        
        Returns:
            List of logo file paths
        """
        logo_dir = Path('assets/logos')
        if not logo_dir.exists():
            return []
        
        supported_formats = ['.png', '.jpg', '.jpeg', '.gif', '.bmp']
        logos = []
        
        for file_path in logo_dir.iterdir():
            if file_path.is_file() and file_path.suffix.lower() in supported_formats:
                logos.append(str(file_path))
        
        return logos
    
    @staticmethod
    def get_logo_dimensions(logo_path: str) -> Optional[Tuple[int, int]]:
        """
        Get the dimensions of a logo file (requires Pillow).
        
        Args:
            logo_path: Path to the logo file
            
        Returns:
            Tuple of (width, height) or None if error
        """
        try:
            from PIL import Image
            with Image.open(logo_path) as img:
                return img.size
        except ImportError:
            print("Pillow not installed. Install with: pip install Pillow")
            return None
        except Exception as e:
            print(f"Error getting logo dimensions: {e}")
            return None
    
    @staticmethod
    def resize_logo_for_pdf(logo_path: str, max_width: int = 50, max_height: int = 25) -> Tuple[float, float]:
        """
        Calculate appropriate dimensions for a logo in a PDF.
        
        Args:
            logo_path: Path to the logo file
            max_width: Maximum width in PDF units
            max_height: Maximum height in PDF units
            
        Returns:
            Tuple of (width, height) for PDF
        """
        dimensions = LogoManager.get_logo_dimensions(logo_path)
        if not dimensions:
            return (max_width, max_height)
        
        orig_width, orig_height = dimensions
        
        # Calculate aspect ratio
        aspect_ratio = orig_width / orig_height
        
        # Calculate new dimensions maintaining aspect ratio
        if aspect_ratio > (max_width / max_height):
            # Width is the limiting factor
            new_width = max_width
            new_height = max_width / aspect_ratio
        else:
            # Height is the limiting factor
            new_height = max_height
            new_width = max_height * aspect_ratio
        
        return (new_width, new_height) 