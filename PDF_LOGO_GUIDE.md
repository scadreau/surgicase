# Created: 2025-07-17 11:38:00
# Last Modified: 2025-07-30 06:45:15

# PDF Logo Integration Guide

This guide explains how to add logos to PDF reports in the SurgiCase application using FPDF2.

## Overview

The SurgiCase application now supports adding logos to PDF reports through:
- **Enhanced FPDF2 Class**: `ProviderPaymentReportPDF` with built-in logo support
- **Logo Manager**: `LogoManager` utility for configuration and validation
- **Environment Variables**: Flexible configuration through environment variables
- **Multiple Report Types**: Different logo configurations for different reports

## Quick Start

### 1. Install Dependencies

```bash
pip install Pillow
```

### 2. Add Your Logo

Place your logo file in the `assets/logos/` directory:

```bash
mkdir -p assets/logos
# Copy your logo file to assets/logos/company_logo.png
```

### 3. Basic Usage

```python
from endpoints.reports.provider_payment_report import ProviderPaymentReportPDF

# Create PDF with default logo settings
pdf = ProviderPaymentReportPDF()
pdf.add_page()
# ... add content ...
pdf.output("report.pdf")
```

## Configuration Options

### Environment Variables

Set these environment variables for custom logo configuration:

```bash
export REPORT_LOGO_PATH="assets/logos/your_logo.png"
export REPORT_LOGO_WIDTH="40"
export REPORT_LOGO_HEIGHT="20"
export REPORT_LOGO_X="15"
export REPORT_LOGO_Y="15"
```

### Programmatic Configuration

```python
from utils.logo_manager import LogoManager

# Get configuration for specific report type
config = LogoManager.get_logo_config('provider_payment')

# Create PDF with custom settings
pdf = ProviderPaymentReportPDF(
    logo_path=config['path'],
    logo_width=config['width'],
    logo_height=config['height']
)
pdf.set_logo_position(config['x'], config['y'])
```

## Supported Image Formats

FPDF2 supports the following image formats:
- **PNG** (recommended for logos)
- **JPG/JPEG**
- **GIF**
- **BMP**

## Logo Positioning

### Default Positions

- **Provider Payment Reports**: Top-left (10, 10)
- **Case Reports**: Top-left (15, 15) 
- **Summary Reports**: Top-left (8, 8)

### Custom Positioning

```python
# Set custom position
pdf.set_logo_position(x=20, y=25)

# Add logo at specific position for current page
pdf.add_logo(x=30, y=40, width=35, height=18)
```

## Logo Sizing

### Automatic Sizing

The `LogoManager` can automatically calculate appropriate dimensions:

```python
from utils.logo_manager import LogoManager

# Get optimal dimensions for PDF
width, height = LogoManager.resize_logo_for_pdf(
    "assets/logos/logo.png", 
    max_width=50, 
    max_height=25
)
```

### Manual Sizing

```python
# Set default size
pdf.set_logo_size(width=40, height=20)

# Add logo with specific size
pdf.add_logo(width=35, height=18)
```

## Report Types and Configurations

### Provider Payment Reports

```python
# Default configuration
{
    'path': 'assets/logos/company_logo.png',
    'width': 30,
    'height': 15,
    'x': 10,
    'y': 10
}
```

### Case Reports

```python
# Default configuration
{
    'path': 'assets/logos/company_logo.png',
    'width': 25,
    'height': 12,
    'x': 15,
    'y': 15
}
```

### Summary Reports

```python
# Default configuration
{
    'path': 'assets/logos/company_logo.png',
    'width': 35,
    'height': 18,
    'x': 8,
    'y': 8
}
```

## Logo Management Utilities

### List Available Logos

```python
from utils.logo_manager import LogoManager

# List all available logo files
logos = LogoManager.list_available_logos()
print(logos)  # ['assets/logos/logo1.png', 'assets/logos/logo2.jpg']
```

### Validate Logo Files

```python
# Check if logo file is valid
is_valid = LogoManager.validate_logo_path("assets/logos/logo.png")
print(is_valid)  # True/False
```

### Get Logo Dimensions

```python
# Get original dimensions (requires Pillow)
dimensions = LogoManager.get_logo_dimensions("assets/logos/logo.png")
if dimensions:
    width, height = dimensions
    print(f"Logo size: {width}x{height}")
```

## Integration with Existing Reports

### Provider Payment Report

The provider payment report automatically includes logo support:

```python
# The report endpoint already uses LogoManager
@router.get("/provider_payment_report")
def generate_provider_payment_report():
    # Logo is automatically added based on configuration
    logo_config = LogoManager.get_logo_config('provider_payment')
    pdf = ProviderPaymentReportPDF(
        logo_path=logo_config['path'],
        logo_width=logo_config['width'],
        logo_height=logo_config['height']
    )
    # ... rest of report generation
```

### Adding to New Reports

For new reports, extend the FPDF2 class:

```python
from fpdf2 import FPDF
from utils.logo_manager import LogoManager

class CustomReportPDF(FPDF):
    def __init__(self, logo_path=None, logo_width=30, logo_height=15):
        super().__init__()
        self.logo_path = logo_path
        self.logo_width = logo_width
        self.logo_height = logo_height
        self.logo_x = 10
        self.logo_y = 10
    
    def add_logo(self, x=None, y=None, width=None, height=None):
        if not self.logo_path or not os.path.exists(self.logo_path):
            return False
        
        x = x if x is not None else self.logo_x
        y = y if y is not None else self.logo_y
        width = width if width is not None else self.logo_width
        height = height if height is not None else self.logo_height
        
        self.image(self.logo_path, x, y, width, height)
        return True
    
    def header(self):
        # Add logo to header
        if self.logo_path and os.path.exists(self.logo_path):
            self.add_logo()
        
        # Add header text
        self.set_font("Arial", 'B', 16)
        self.cell(0, 10, "Your Report Title", ln=True, align="C")
```

## Best Practices

### Logo File Preparation

1. **Use PNG format** for best quality and transparency support
2. **Optimize file size** - keep logos under 100KB
3. **Use appropriate resolution** - 300-600 DPI for print quality
4. **Maintain aspect ratio** - avoid distortion

### Positioning Guidelines

1. **Top-left corner** is most common for company logos
2. **Leave adequate margins** - at least 10mm from edges
3. **Consider text flow** - ensure logo doesn't interfere with content
4. **Consistent placement** across all reports

### Sizing Guidelines

1. **Not too large** - logos should be prominent but not dominant
2. **Not too small** - ensure readability and brand visibility
3. **Proportional scaling** - maintain aspect ratio
4. **Test different sizes** - what works on screen may differ in print

## Troubleshooting

### Common Issues

1. **Logo not appearing**
   - Check file path is correct
   - Verify file exists and is readable
   - Ensure supported image format

2. **Logo too large/small**
   - Adjust width and height parameters
   - Use `LogoManager.resize_logo_for_pdf()` for optimal sizing

3. **Logo in wrong position**
   - Check x, y coordinates
   - Verify page margins and layout

4. **Poor image quality**
   - Use higher resolution source image
   - Convert to PNG format
   - Avoid excessive compression

### Debug Commands

```python
# Check logo configuration
config = LogoManager.get_logo_config('provider_payment')
print(f"Logo config: {config}")

# Validate logo file
is_valid = LogoManager.validate_logo_path(config['path'])
print(f"Logo valid: {is_valid}")

# List all available logos
logos = LogoManager.list_available_logos()
print(f"Available logos: {logos}")
```

## Examples

### Basic Example

```python
from endpoints.reports.provider_payment_report import ProviderPaymentReportPDF

# Simple usage with default logo
pdf = ProviderPaymentReportPDF()
pdf.add_page()
pdf.set_font("Arial", 'B', 16)
pdf.cell(0, 10, "Report with Logo", ln=True, align="C")
pdf.output("basic_report.pdf")
```

### Advanced Example

```python
from utils.logo_manager import LogoManager

# Custom configuration
config = LogoManager.get_logo_config('provider_payment')
config['width'] = 40
config['height'] = 20

# Create PDF with custom logo
pdf = ProviderPaymentReportPDF(
    logo_path=config['path'],
    logo_width=config['width'],
    logo_height=config['height']
)
pdf.set_logo_position(15, 15)

# Add content
pdf.add_page()
pdf.set_font("Arial", 'B', 16)
pdf.cell(0, 10, "Custom Logo Report", ln=True, align="C")

pdf.output("custom_report.pdf")
```

## Testing

Run the example script to test logo functionality:

```bash
python examples/add_logo_to_pdf.py
```

This will create sample PDFs demonstrating different logo configurations and help verify your setup is working correctly.

## Environment Setup

### Development Environment

```bash
# Install dependencies
pip install -r requirements.txt

# Create logo directory
mkdir -p assets/logos

# Add your logo file
cp your_logo.png assets/logos/company_logo.png

# Set environment variables (optional)
export REPORT_LOGO_PATH="assets/logos/company_logo.png"
export REPORT_LOGO_WIDTH="30"
export REPORT_LOGO_HEIGHT="15"
```

### Production Environment

```bash
# Set production logo configuration
export REPORT_LOGO_PATH="/path/to/production/logo.png"
export REPORT_LOGO_WIDTH="35"
export REPORT_LOGO_HEIGHT="18"
export REPORT_LOGO_X="10"
export REPORT_LOGO_Y="10"
```

## Security Considerations

1. **File validation** - LogoManager validates file paths and formats
2. **Path restrictions** - Only allow logos from designated directories
3. **File size limits** - Consider implementing size restrictions
4. **Access controls** - Ensure logo files are not publicly accessible

## Performance Notes

1. **Logo caching** - Consider caching logo dimensions for repeated use
2. **File I/O** - Logo files are read for each PDF generation
3. **Memory usage** - Large logos may increase memory consumption
4. **Processing time** - Logo addition adds minimal overhead to PDF generation 