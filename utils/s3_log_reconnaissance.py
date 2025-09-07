# Created: 2025-09-07 21:20:13
# Last Modified: 2025-09-07 21:23:27
# Author: Scott Cadreau

"""
S3 Log File Reconnaissance Script

This script analyzes the S3 bucket to identify log files that need to be moved.
It categorizes files by likely source (API Gateway, Amplify, CloudFront, etc.)
and provides detailed statistics without making any changes.

Usage:
    python utils/s3_log_reconnaissance.py

The script will:
- List all files in the S3 bucket root
- Categorize files by type and likely source
- Show file patterns, sizes, and dates
- Provide recommendations for cleanup
"""

import boto3
import json
import re
from datetime import datetime, timezone
from typing import Dict, List, Any, Tuple
from collections import defaultdict, Counter
import logging

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def get_s3_client_for_reconnaissance():
    """
    Get S3 client using the existing secrets manager configuration
    """
    try:
        from utils.secrets_manager import get_secret
        
        # Try different S3 configurations to find the right one
        config_names = [
            "surgicase/s3-user-reports",
            "surgicase/s3-case-documents", 
            "surgicase/s3-user-documents"
        ]
        
        for config_name in config_names:
            try:
                config = get_secret(config_name)
                if config and 'bucket_name' in config:
                    # Use access keys if provided, otherwise use IAM role
                    if 'aws_access_key_id' in config and 'aws_secret_access_key' in config:
                        s3_client = boto3.client(
                            's3',
                            region_name=config.get('region', 'us-east-1'),
                            aws_access_key_id=config['aws_access_key_id'],
                            aws_secret_access_key=config['aws_secret_access_key']
                        )
                    else:
                        # Use IAM role (recommended for production)
                        s3_client = boto3.client('s3', region_name=config.get('region', 'us-east-1'))
                    
                    return s3_client, config['bucket_name']
            except Exception as e:
                logger.debug(f"Config {config_name} not available: {str(e)}")
                continue
        
        # If no config found, try default IAM role
        logger.info("No S3 config found in secrets, trying default IAM role...")
        s3_client = boto3.client('s3', region_name='us-east-1')
        bucket_name = "amplify-surgicalcasemanag-surgicaldocsbucket5a7ebd-8usdadqv6nnp"
        return s3_client, bucket_name
        
    except Exception as e:
        logger.error(f"Error creating S3 client: {str(e)}")
        raise

def categorize_file(key: str, size: int, last_modified: datetime) -> Dict[str, Any]:
    """
    Categorize a file based on its key pattern and characteristics
    
    Args:
        key: S3 object key (filename/path)
        size: File size in bytes
        last_modified: Last modified timestamp
        
    Returns:
        dict: Category information and metadata
    """
    key_lower = key.lower()
    
    # File extension
    extension = key.split('.')[-1].lower() if '.' in key else 'no_extension'
    
    # Initialize category info
    category_info = {
        'key': key,
        'size': size,
        'last_modified': last_modified,
        'extension': extension,
        'category': 'unknown',
        'subcategory': 'unknown',
        'confidence': 'low',
        'patterns_matched': []
    }
    
    # API Gateway log patterns
    api_gateway_patterns = [
        r'api[_-]?gateway',
        r'access[_-]?log',
        r'request[_-]?log',
        r'\d{4}-\d{2}-\d{2}.*\.log',
        r'gateway.*\.txt',
        r'api.*\.log'
    ]
    
    # Amplify log patterns  
    amplify_patterns = [
        r'amplify',
        r'build[_-]?log',
        r'deploy.*log',
        r'_build_',
        r'amplify.*\.txt',
        r'build.*\.log'
    ]
    
    # CloudFront log patterns
    cloudfront_patterns = [
        r'cloudfront',
        r'cdn[_-]?log',
        r'E[A-Z0-9]{13}\..*\.gz',  # CloudFront log format
        r'distribution.*log'
    ]
    
    # S3 access log patterns
    s3_access_patterns = [
        r's3[_-]?access',
        r'server[_-]?access',
        r'\d{4}-\d{2}-\d{2}-\d{2}-\d{2}-\d{2}-[A-F0-9]{16}',  # S3 access log format
        r'access_log.*'
    ]
    
    # General log patterns
    general_log_patterns = [
        r'\.log$',
        r'\.txt$',
        r'error.*log',
        r'debug.*log',
        r'info.*log'
    ]
    
    # Check patterns and assign categories
    matched_patterns = []
    
    # Check API Gateway patterns
    for pattern in api_gateway_patterns:
        if re.search(pattern, key_lower):
            matched_patterns.append(f"api_gateway: {pattern}")
            category_info['category'] = 'api_gateway'
            category_info['confidence'] = 'high'
    
    # Check Amplify patterns
    for pattern in amplify_patterns:
        if re.search(pattern, key_lower):
            matched_patterns.append(f"amplify: {pattern}")
            if category_info['category'] == 'unknown':
                category_info['category'] = 'amplify'
                category_info['confidence'] = 'high'
    
    # Check CloudFront patterns
    for pattern in cloudfront_patterns:
        if re.search(pattern, key_lower):
            matched_patterns.append(f"cloudfront: {pattern}")
            if category_info['category'] == 'unknown':
                category_info['category'] = 'cloudfront'
                category_info['confidence'] = 'high'
    
    # Check S3 access patterns
    for pattern in s3_access_patterns:
        if re.search(pattern, key_lower):
            matched_patterns.append(f"s3_access: {pattern}")
            if category_info['category'] == 'unknown':
                category_info['category'] = 's3_access'
                category_info['confidence'] = 'high'
    
    # Check general log patterns
    for pattern in general_log_patterns:
        if re.search(pattern, key_lower):
            matched_patterns.append(f"general_log: {pattern}")
            if category_info['category'] == 'unknown':
                category_info['category'] = 'log_file'
                category_info['confidence'] = 'medium'
    
    # Additional heuristics based on file characteristics
    if size < 1024:  # Very small files (< 1KB)
        category_info['subcategory'] = 'very_small'
    elif size < 10240:  # Small files (< 10KB)
        category_info['subcategory'] = 'small'
    elif size < 102400:  # Medium files (< 100KB)
        category_info['subcategory'] = 'medium'
    else:
        category_info['subcategory'] = 'large'
    
    # Check if file is in root directory (no forward slashes)
    if '/' not in key:
        category_info['in_root'] = True
    else:
        category_info['in_root'] = False
    
    category_info['patterns_matched'] = matched_patterns
    
    return category_info

def analyze_s3_bucket(s3_client, bucket_name: str) -> Dict[str, Any]:
    """
    Analyze all files in the S3 bucket and categorize them
    
    Args:
        s3_client: Boto3 S3 client
        bucket_name: Name of the S3 bucket
        
    Returns:
        dict: Analysis results with categorized files
    """
    logger.info(f"Starting analysis of S3 bucket: {bucket_name}")
    
    analysis_results = {
        'bucket_name': bucket_name,
        'scan_timestamp': datetime.now(timezone.utc).isoformat(),
        'total_files': 0,
        'total_size': 0,
        'root_files': 0,
        'categories': defaultdict(list),
        'extensions': Counter(),
        'size_distribution': defaultdict(int),
        'date_distribution': defaultdict(int),
        'recommendations': []
    }
    
    try:
        # List all objects in the bucket
        paginator = s3_client.get_paginator('list_objects_v2')
        page_iterator = paginator.paginate(Bucket=bucket_name)
        
        for page in page_iterator:
            if 'Contents' not in page:
                continue
                
            for obj in page['Contents']:
                key = obj['Key']
                size = obj['Size']
                last_modified = obj['LastModified']
                
                analysis_results['total_files'] += 1
                analysis_results['total_size'] += size
                
                # Check if file is in root directory
                if '/' not in key:
                    analysis_results['root_files'] += 1
                
                # Categorize the file
                file_info = categorize_file(key, size, last_modified)
                category = file_info['category']
                analysis_results['categories'][category].append(file_info)
                
                # Track extensions
                analysis_results['extensions'][file_info['extension']] += 1
                
                # Track size distribution
                if size < 1024:
                    analysis_results['size_distribution']['< 1KB'] += 1
                elif size < 10240:
                    analysis_results['size_distribution']['1KB - 10KB'] += 1
                elif size < 102400:
                    analysis_results['size_distribution']['10KB - 100KB'] += 1
                elif size < 1048576:
                    analysis_results['size_distribution']['100KB - 1MB'] += 1
                else:
                    analysis_results['size_distribution']['> 1MB'] += 1
                
                # Track date distribution (by month)
                month_key = last_modified.strftime('%Y-%m')
                analysis_results['date_distribution'][month_key] += 1
        
        logger.info(f"Analysis complete. Found {analysis_results['total_files']} files")
        
    except Exception as e:
        logger.error(f"Error analyzing bucket: {str(e)}")
        raise
    
    return analysis_results

def generate_recommendations(analysis_results: Dict[str, Any]) -> List[str]:
    """
    Generate recommendations based on the analysis results
    """
    recommendations = []
    
    # Check for high number of root files
    if analysis_results['root_files'] > 100:
        recommendations.append(
            f"🚨 HIGH PRIORITY: {analysis_results['root_files']} files found in bucket root. "
            "These should be organized into directories."
        )
    
    # Check for log files
    log_categories = ['api_gateway', 'amplify', 'cloudfront', 's3_access', 'log_file']
    total_log_files = sum(len(analysis_results['categories'][cat]) for cat in log_categories)
    
    if total_log_files > 50:
        recommendations.append(
            f"📋 CLEANUP NEEDED: {total_log_files} log files detected. "
            "Consider moving to log_files/ directory structure."
        )
    
    # Check for very small files (likely log entries)
    small_files = analysis_results['size_distribution'].get('< 1KB', 0)
    if small_files > 100:
        recommendations.append(
            f"🔍 PATTERN DETECTED: {small_files} very small files (< 1KB) suggest frequent logging. "
            "Review AWS service logging configuration."
        )
    
    # Check for specific AWS service patterns
    if len(analysis_results['categories']['api_gateway']) > 0:
        recommendations.append(
            "⚙️ API GATEWAY: Configure API Gateway access logs to use CloudWatch or dedicated log bucket."
        )
    
    if len(analysis_results['categories']['amplify']) > 0:
        recommendations.append(
            "🚀 AMPLIFY: Review Amplify build logging configuration to prevent log files in main bucket."
        )
    
    if len(analysis_results['categories']['cloudfront']) > 0:
        recommendations.append(
            "🌐 CLOUDFRONT: Configure CloudFront access logs to use separate bucket."
        )
    
    return recommendations

def print_analysis_report(analysis_results: Dict[str, Any]):
    """
    Print a formatted analysis report
    """
    print("\n" + "="*80)
    print("🔍 S3 BUCKET LOG FILE RECONNAISSANCE REPORT")
    print("="*80)
    
    print(f"\n📊 BUCKET OVERVIEW:")
    print(f"   Bucket Name: {analysis_results['bucket_name']}")
    print(f"   Scan Time: {analysis_results['scan_timestamp']}")
    print(f"   Total Files: {analysis_results['total_files']:,}")
    print(f"   Total Size: {analysis_results['total_size'] / (1024*1024):.2f} MB")
    print(f"   Files in Root: {analysis_results['root_files']:,}")
    
    print(f"\n📁 FILE CATEGORIES:")
    for category, files in analysis_results['categories'].items():
        if files:
            total_size = sum(f['size'] for f in files)
            print(f"   {category.upper()}: {len(files):,} files ({total_size / 1024:.1f} KB)")
            
            # Show sample files for each category
            sample_files = files[:3]  # Show first 3 files as examples
            for file_info in sample_files:
                print(f"      └─ {file_info['key']} ({file_info['size']} bytes)")
            if len(files) > 3:
                print(f"      └─ ... and {len(files) - 3} more files")
    
    print(f"\n📈 SIZE DISTRIBUTION:")
    for size_range, count in analysis_results['size_distribution'].items():
        print(f"   {size_range}: {count:,} files")
    
    print(f"\n📅 DATE DISTRIBUTION (by month):")
    sorted_dates = sorted(analysis_results['date_distribution'].items())
    for month, count in sorted_dates[-6:]:  # Show last 6 months
        print(f"   {month}: {count:,} files")
    
    print(f"\n🔧 FILE EXTENSIONS:")
    for ext, count in analysis_results['extensions'].most_common(10):
        print(f"   .{ext}: {count:,} files")
    
    # Generate and show recommendations
    recommendations = generate_recommendations(analysis_results)
    if recommendations:
        print(f"\n💡 RECOMMENDATIONS:")
        for i, rec in enumerate(recommendations, 1):
            print(f"   {i}. {rec}")
    
    print("\n" + "="*80)
    print("✅ RECONNAISSANCE COMPLETE")
    print("="*80)

def save_detailed_report(analysis_results: Dict[str, Any], filename: str = None):
    """
    Save detailed analysis results to a JSON file
    """
    if not filename:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"s3_log_reconnaissance_report_{timestamp}.json"
    
    # Convert datetime objects to strings for JSON serialization
    serializable_results = {}
    for key, value in analysis_results.items():
        if key == 'categories':
            serializable_categories = {}
            for cat, files in value.items():
                serializable_files = []
                for file_info in files:
                    serializable_file = file_info.copy()
                    if 'last_modified' in serializable_file:
                        serializable_file['last_modified'] = serializable_file['last_modified'].isoformat()
                    serializable_files.append(serializable_file)
                serializable_categories[cat] = serializable_files
            serializable_results[key] = serializable_categories
        else:
            serializable_results[key] = value
    
    try:
        with open(filename, 'w') as f:
            json.dump(serializable_results, f, indent=2, default=str)
        print(f"\n📄 Detailed report saved to: {filename}")
    except Exception as e:
        logger.error(f"Error saving detailed report: {str(e)}")

def main():
    """
    Main function to run the S3 log reconnaissance
    """
    try:
        print("🚀 Starting S3 Log File Reconnaissance...")
        
        # Get S3 client and bucket name
        s3_client, bucket_name = get_s3_client_for_reconnaissance()
        print(f"✅ Connected to S3 bucket: {bucket_name}")
        
        # Analyze the bucket
        analysis_results = analyze_s3_bucket(s3_client, bucket_name)
        
        # Print the report
        print_analysis_report(analysis_results)
        
        # Save detailed report
        save_detailed_report(analysis_results)
        
        print("\n🎯 Next Steps:")
        print("   1. Review the analysis results above")
        print("   2. Confirm which file categories should be moved to log_files/")
        print("   3. Run the migration script once patterns are confirmed")
        
    except Exception as e:
        logger.error(f"Reconnaissance failed: {str(e)}")
        print(f"\n❌ Error: {str(e)}")
        print("\nTroubleshooting:")
        print("   - Verify AWS credentials are configured")
        print("   - Check S3 bucket permissions")
        print("   - Ensure bucket name is correct")

if __name__ == "__main__":
    main()
