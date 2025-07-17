# Created: 2025-07-17 11:37:00
# Last Modified: 2025-07-17 11:37:20

# examples/add_logo_to_pdf.py
"""
Example script demonstrating how to add logos to PDF reports.

This script shows different ways to configure and use logos in your PDF reports.
"""

import os
import sys
from pathlib import Path

# Add the parent directory to the path for imports
sys.path.append(str(Path(__file__).parent.parent))

from endpoints.reports.provider_payment_report import ProviderPaymentReportPDF
from utils.logo_manager import LogoManager

def example_basic_logo():
    """Example 1: Basic logo usage with default settings"""
    print("Example 1: Basic logo usage")
    
    # Create the logo directory
    logo_dir = LogoManager.create_logo_directory()
    print(f"Logo directory: {logo_dir}")
    
    # Create a simple PDF with logo
    pdf = ProviderPaymentReportPDF()
    
    # Add a page
    pdf.add_page()
    
    # Add some content
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(0, 10, "Sample Report with Logo", ln=True, align="C")
    pdf.ln(10)
    
    pdf.set_font("Arial", '', 12)
    pdf.cell(0, 8, "This is a sample report demonstrating logo functionality.", ln=True)
    pdf.cell(0, 8, "The logo will appear in the header if a valid logo file is found.", ln=True)
    
    # Save the PDF
    output_path = "examples/sample_report_with_logo.pdf"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    pdf.output(output_path)
    print(f"PDF saved to: {output_path}")

def example_custom_logo_config():
    """Example 2: Custom logo configuration"""
    print("\nExample 2: Custom logo configuration")
    
    # Set environment variables for custom logo
    os.environ['REPORT_LOGO_PATH'] = 'assets/logos/custom_logo.png'
    os.environ['REPORT_LOGO_WIDTH'] = '40'
    os.environ['REPORT_LOGO_HEIGHT'] = '20'
    os.environ['REPORT_LOGO_X'] = '15'
    os.environ['REPORT_LOGO_Y'] = '15'
    
    # Get the custom configuration
    config = LogoManager.get_logo_config('provider_payment')
    print(f"Custom logo config: {config}")
    
    # Create PDF with custom logo settings
    pdf = ProviderPaymentReportPDF(
        logo_path=config['path'],
        logo_width=config['width'],
        logo_height=config['height']
    )
    pdf.set_logo_position(config['x'], config['y'])
    
    pdf.add_page()
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(0, 10, "Custom Logo Configuration", ln=True, align="C")
    
    output_path = "examples/custom_logo_report.pdf"
    pdf.output(output_path)
    print(f"PDF saved to: {output_path}")

def example_logo_validation():
    """Example 3: Logo validation and management"""
    print("\nExample 3: Logo validation and management")
    
    # List available logos
    available_logos = LogoManager.list_available_logos()
    print(f"Available logos: {available_logos}")
    
    # Validate a logo path
    test_logo_path = "assets/logos/company_logo.png"
    is_valid = LogoManager.validate_logo_path(test_logo_path)
    print(f"Logo {test_logo_path} is valid: {is_valid}")
    
    # Get logo dimensions (if Pillow is installed)
    dimensions = LogoManager.get_logo_dimensions(test_logo_path)
    if dimensions:
        print(f"Logo dimensions: {dimensions}")
        
        # Calculate PDF dimensions
        pdf_dimensions = LogoManager.resize_logo_for_pdf(test_logo_path, 50, 25)
        print(f"PDF dimensions: {pdf_dimensions}")

def example_multiple_logos():
    """Example 4: Using different logos for different report types"""
    print("\nExample 4: Different logos for different report types")
    
    report_types = ['provider_payment', 'case_report', 'summary_report']
    
    for report_type in report_types:
        config = LogoManager.get_logo_config(report_type)
        print(f"{report_type} report logo config: {config}")
        
        # Create a sample PDF for each report type
        pdf = ProviderPaymentReportPDF(
            logo_path=config['path'],
            logo_width=config['width'],
            logo_height=config['height']
        )
        pdf.set_logo_position(config['x'], config['y'])
        
        pdf.add_page()
        pdf.set_font("Arial", 'B', 16)
        pdf.cell(0, 10, f"{report_type.replace('_', ' ').title()} Report", ln=True, align="C")
        
        output_path = f"examples/{report_type}_sample.pdf"
        pdf.output(output_path)
        print(f"PDF saved to: {output_path}")

def main():
    """Run all examples"""
    print("=" * 60)
    print("PDF LOGO FUNCTIONALITY EXAMPLES")
    print("=" * 60)
    
    try:
        example_basic_logo()
        example_custom_logo_config()
        example_logo_validation()
        example_multiple_logos()
        
        print("\n" + "=" * 60)
        print("All examples completed successfully!")
        print("=" * 60)
        print("\nNext steps:")
        print("1. Add your logo file to assets/logos/")
        print("2. Set environment variables for custom configuration")
        print("3. Use the LogoManager in your report generation code")
        
    except Exception as e:
        print(f"Error running examples: {e}")
        print("\nMake sure you have:")
        print("- Pillow installed: pip install Pillow")
        print("- A logo file in assets/logos/ directory")

if __name__ == "__main__":
    main() 