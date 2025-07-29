# Created: 2025-07-29 04:51:35
# Last Modified: 2025-07-29 04:51:36
# Author: Scott Cadreau

# utils/test_pdf_compression.py
import os
import sys
from compress_pdf import compress_pdf_safe, is_pdf_valid

def test_pdf_compression(input_pdf_path: str) -> bool:
    """
    Test PDF compression with a single file
    
    Args:
        input_pdf_path: Path to the PDF to test
        
    Returns:
        bool: True if compression successful and output is valid
    """
    if not os.path.exists(input_pdf_path):
        print(f"❌ Input file does not exist: {input_pdf_path}")
        return False
    
    if not is_pdf_valid(input_pdf_path):
        print(f"❌ Input file is not a valid PDF: {input_pdf_path}")
        return False
    
    # Create output path
    base_name = os.path.splitext(input_pdf_path)[0]
    output_path = f"{base_name}_compressed_test.pdf"
    
    print(f"🔄 Testing compression of: {input_pdf_path}")
    
    # Test compression
    success = compress_pdf_safe(input_pdf_path, output_path)
    
    if not success:
        print(f"❌ Compression failed")
        return False
    
    # Verify output
    if not is_pdf_valid(output_path):
        print(f"❌ Compressed PDF is corrupted: {output_path}")
        return False
    
    # Get file sizes
    original_size = os.path.getsize(input_pdf_path)
    compressed_size = os.path.getsize(output_path)
    reduction = (1 - compressed_size / original_size) * 100
    
    print(f"✅ Compression successful!")
    print(f"   Original: {original_size:,} bytes")
    print(f"   Compressed: {compressed_size:,} bytes")
    print(f"   Reduction: {reduction:.1f}%")
    print(f"   Output: {output_path}")
    
    return True

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python test_pdf_compression.py <path_to_pdf>")
        sys.exit(1)
    
    pdf_path = sys.argv[1]
    success = test_pdf_compression(pdf_path)
    
    if success:
        print("\n🎉 PDF compression test PASSED")
        sys.exit(0)
    else:
        print("\n💥 PDF compression test FAILED")
        sys.exit(1) 