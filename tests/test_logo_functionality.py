# Created: 2025-07-17 11:39:00
# Last Modified: 2025-07-17 11:48:49

# tests/test_logo_functionality.py
"""
Test script for logo functionality in PDF reports.
Tests logo validation, configuration, and PDF generation with logos.
"""

import os
import sys
import tempfile
from pathlib import Path

# Add the parent directory to the path for imports
sys.path.append(str(Path(__file__).parent.parent))

from utils.logo_manager import LogoManager
from endpoints.reports.provider_payment_report import ProviderPaymentReportPDF

def test_logo_manager_creation():
    """Test LogoManager directory creation"""
    print("Testing LogoManager directory creation...")
    
    logo_dir = LogoManager.create_logo_directory()
    assert os.path.exists(logo_dir), f"Logo directory {logo_dir} should exist"
    print(f"✓ Logo directory created: {logo_dir}")
    return True

def test_logo_configuration():
    """Test logo configuration retrieval"""
    print("Testing logo configuration...")
    
    # Test default configuration
    config = LogoManager.get_logo_config('provider_payment')
    assert 'path' in config, "Configuration should have 'path' key"
    assert 'width' in config, "Configuration should have 'width' key"
    assert 'height' in config, "Configuration should have 'height' key"
    assert 'x' in config, "Configuration should have 'x' key"
    assert 'y' in config, "Configuration should have 'y' key"
    
    print(f"✓ Default config: {config}")
    
    # Test environment variable override
    os.environ['REPORT_LOGO_PATH'] = '/test/path/logo.png'
    os.environ['REPORT_LOGO_WIDTH'] = '50'
    os.environ['REPORT_LOGO_HEIGHT'] = '25'
    
    env_config = LogoManager.get_logo_config('provider_payment')
    assert env_config['path'] == '/test/path/logo.png', "Environment path should override default"
    assert env_config['width'] == 50, "Environment width should override default"
    assert env_config['height'] == 25, "Environment height should override default"
    
    print(f"✓ Environment config: {env_config}")
    
    # Clean up environment variables
    del os.environ['REPORT_LOGO_PATH']
    del os.environ['REPORT_LOGO_WIDTH']
    del os.environ['REPORT_LOGO_HEIGHT']
    
    return True

def test_logo_validation():
    """Test logo file validation"""
    print("Testing logo validation...")
    
    # Test with non-existent file
    is_valid = LogoManager.validate_logo_path("nonexistent.png")
    assert not is_valid, "Non-existent file should be invalid"
    print("✓ Non-existent file correctly marked as invalid")
    
    # Test with invalid extension
    is_valid = LogoManager.validate_logo_path("test.txt")
    assert not is_valid, "Invalid extension should be invalid"
    print("✓ Invalid extension correctly marked as invalid")
    
    # Test with valid extension but non-existent file
    is_valid = LogoManager.validate_logo_path("valid.png")
    assert not is_valid, "Valid extension but non-existent file should be invalid"
    print("✓ Valid extension but non-existent file correctly marked as invalid")
    
    return True

def test_pdf_with_logo():
    """Test PDF generation with logo"""
    print("Testing PDF generation with logo...")
    
    # Create a temporary logo file for testing
    logo_dir = LogoManager.create_logo_directory()
    test_logo_path = os.path.join(logo_dir, "test_logo.png")
    
    # Create a simple test image (1x1 pixel PNG)
    try:
        from PIL import Image
        # Create a simple test image
        img = Image.new('RGB', (100, 50), color='red')
        img.save(test_logo_path)
        print(f"✓ Created test logo: {test_logo_path}")
    except ImportError:
        print("⚠ Pillow not available, skipping image creation test")
        return True
    
    # Test PDF creation with logo
    try:
        pdf = ProviderPaymentReportPDF(
            logo_path=test_logo_path,
            logo_width=30,
            logo_height=15
        )
        pdf.set_logo_position(10, 10)
        
        # Add a page
        pdf.add_page()
        
        # Add some content
        pdf.set_font("Arial", 'B', 16)
        pdf.cell(0, 10, "Test Report with Logo", ln=True, align="C")
        
        # Save to temporary file
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp_file:
            pdf.output(tmp_file.name)
            print(f"✓ PDF generated successfully: {tmp_file.name}")
            
            # Verify file was created and has content
            assert os.path.exists(tmp_file.name), "PDF file should exist"
            assert os.path.getsize(tmp_file.name) > 0, "PDF file should have content"
            
            # Clean up (handle Windows file access issues)
            try:
                os.unlink(tmp_file.name)
            except OSError as e:
                print(f"⚠ Could not delete temporary file (this is normal on Windows): {e}")
                # On Windows, files might be locked by the system, which is okay
    
    except Exception as e:
        print(f"✗ Error generating PDF: {e}")
        return False
    
    # Clean up test logo (handle Windows file access issues)
    if os.path.exists(test_logo_path):
        try:
            os.unlink(test_logo_path)
        except OSError as e:
            print(f"⚠ Could not delete test logo (this is normal on Windows): {e}")
            # On Windows, files might be locked by the system, which is okay
    
    return True

def test_pdf_without_logo():
    """Test PDF generation without logo"""
    print("Testing PDF generation without logo...")
    
    try:
        # Create PDF without logo
        pdf = ProviderPaymentReportPDF()
        pdf.add_page()
        
        # Add content
        pdf.set_font("Arial", 'B', 16)
        pdf.cell(0, 10, "Test Report without Logo", ln=True, align="C")
        
        # Save to temporary file
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp_file:
            pdf.output(tmp_file.name)
            print(f"✓ PDF generated successfully without logo: {tmp_file.name}")
            
            # Verify file was created and has content
            assert os.path.exists(tmp_file.name), "PDF file should exist"
            assert os.path.getsize(tmp_file.name) > 0, "PDF file should have content"
            
            # Clean up (handle Windows file access issues)
            try:
                os.unlink(tmp_file.name)
            except OSError as e:
                print(f"⚠ Could not delete temporary file (this is normal on Windows): {e}")
                # On Windows, files might be locked by the system, which is okay
    
    except Exception as e:
        print(f"✗ Error generating PDF without logo: {e}")
        return False
    
    return True

def test_logo_utilities():
    """Test logo utility functions"""
    print("Testing logo utilities...")
    
    # Test listing available logos
    logos = LogoManager.list_available_logos()
    assert isinstance(logos, list), "list_available_logos should return a list"
    print(f"✓ Available logos: {logos}")
    
    # Test logo path retrieval
    logo_path = LogoManager.get_logo_path('provider_payment')
    # This might be None if no logo exists, which is fine
    print(f"✓ Logo path: {logo_path}")
    
    return True

def main():
    """Run all logo functionality tests"""
    print("=" * 60)
    print("LOGO FUNCTIONALITY TEST SUITE")
    print("=" * 60)
    
    tests = [
        ("Logo Manager Creation", test_logo_manager_creation),
        ("Logo Configuration", test_logo_configuration),
        ("Logo Validation", test_logo_validation),
        ("PDF with Logo", test_pdf_with_logo),
        ("PDF without Logo", test_pdf_without_logo),
        ("Logo Utilities", test_logo_utilities)
    ]
    
    results = []
    
    for test_name, test_func in tests:
        print(f"\n{'='*20} {test_name} {'='*20}")
        try:
            result = test_func()
            results.append((test_name, result))
            status = "PASS" if result else "FAIL"
            print(f"{test_name}: {status}")
        except Exception as e:
            print(f"{test_name}: ERROR - {e}")
            results.append((test_name, False))
    
    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "PASS" if result else "FAIL"
        print(f"{test_name}: {status}")
    
    print(f"\nOverall: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All logo functionality tests passed!")
        print("\nNext steps:")
        print("1. Add your actual logo file to assets/logos/")
        print("2. Configure logo settings via environment variables")
        print("3. Test with your real reports")
    else:
        print("❌ Some tests failed. Check the output above for details.")
    
    return passed == total

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1) 