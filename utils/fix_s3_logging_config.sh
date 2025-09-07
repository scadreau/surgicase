#!/bin/bash
# Created: 2025-09-07 21:23:00
# Last Modified: 2025-09-07 21:25:55
# Author: Scott Cadreau

# S3 Logging Configuration Fix Script
# 
# This script fixes the S3 access logging misconfiguration that's causing
# thousands of log files to be written to the main application bucket.
#
# What it does:
# 1. Creates a dedicated log bucket
# 2. Disables access logging on the main bucket
# 3. Optionally re-enables logging to the dedicated bucket
# 4. Sets up lifecycle policies for log cleanup

set -e  # Exit on any error

# Configuration
MAIN_BUCKET="amplify-surgicalcasemanag-surgicaldocsbucket5a7ebd-8usdadqv6nnp"
LOG_BUCKET="${MAIN_BUCKET}-access-logs"
REGION="us-east-1"

echo "🚀 S3 Logging Configuration Fix"
echo "================================"
echo "Main Bucket: $MAIN_BUCKET"
echo "Log Bucket: $LOG_BUCKET"
echo "Region: $REGION"
echo ""

# Function to check if bucket exists
check_bucket_exists() {
    local bucket_name=$1
    if aws s3api head-bucket --bucket "$bucket_name" 2>/dev/null; then
        return 0
    else
        return 1
    fi
}

# Step 1: Check current logging configuration
echo "📋 Step 1: Checking current S3 access logging configuration..."
echo "Current logging status for $MAIN_BUCKET:"
aws s3api get-bucket-logging --bucket "$MAIN_BUCKET" || echo "No logging configuration found"
echo ""

# Step 2: Create dedicated log bucket if it doesn't exist
echo "📦 Step 2: Creating dedicated log bucket..."
if check_bucket_exists "$LOG_BUCKET"; then
    echo "✅ Log bucket $LOG_BUCKET already exists"
else
    echo "Creating log bucket: $LOG_BUCKET"
    aws s3api create-bucket --bucket "$LOG_BUCKET" --region "$REGION"
    echo "✅ Created log bucket: $LOG_BUCKET"
fi
echo ""

# Step 3: Disable access logging on main bucket (this stops the flood of log files)
echo "🛑 Step 3: Disabling access logging on main bucket..."
echo "This will STOP the creation of new log files in your main bucket."
read -p "Continue? (y/N): " -n 1 -r
echo ""
if [[ $REPLY =~ ^[Yy]$ ]]; then
    # Create empty logging configuration to disable logging
    cat > /tmp/disable_logging.json << EOF
{}
EOF
    
    aws s3api put-bucket-logging --bucket "$MAIN_BUCKET" --bucket-logging-status file:///tmp/disable_logging.json
    echo "✅ Disabled access logging on $MAIN_BUCKET"
    rm /tmp/disable_logging.json
else
    echo "❌ Skipped disabling access logging"
fi
echo ""

# Step 4: Set up lifecycle policy for log bucket (optional)
echo "🔄 Step 4: Setting up lifecycle policy for log bucket..."
echo "This will automatically delete old log files to save costs."
read -p "Set up 30-day log retention? (y/N): " -n 1 -r
echo ""
if [[ $REPLY =~ ^[Yy]$ ]]; then
    cat > /tmp/log_lifecycle.json << EOF
{
    "Rules": [
        {
            "ID": "DeleteOldAccessLogs",
            "Status": "Enabled",
            "Filter": {
                "Prefix": ""
            },
            "Expiration": {
                "Days": 30
            }
        }
    ]
}
EOF
    
    aws s3api put-bucket-lifecycle-configuration --bucket "$LOG_BUCKET" --lifecycle-configuration file:///tmp/log_lifecycle.json
    echo "✅ Set up 30-day lifecycle policy for $LOG_BUCKET"
    rm /tmp/log_lifecycle.json
else
    echo "❌ Skipped lifecycle policy setup"
fi
echo ""

# Step 5: Optionally re-enable logging to dedicated bucket
echo "📊 Step 5: Re-enable access logging (optional)..."
echo "This will enable proper S3 access logging to the dedicated bucket."
echo "WARNING: Only enable this if you actually need S3 access logs for compliance/auditing."
read -p "Enable access logging to dedicated bucket? (y/N): " -n 1 -r
echo ""
if [[ $REPLY =~ ^[Yy]$ ]]; then
    cat > /tmp/enable_logging.json << EOF
{
    "LoggingEnabled": {
        "TargetBucket": "$LOG_BUCKET",
        "TargetPrefix": "access-logs/"
    }
}
EOF
    
    aws s3api put-bucket-logging --bucket "$MAIN_BUCKET" --bucket-logging-status file:///tmp/enable_logging.json
    echo "✅ Enabled access logging to $LOG_BUCKET with prefix 'access-logs/'"
    rm /tmp/enable_logging.json
else
    echo "❌ Access logging remains disabled (recommended for most applications)"
fi
echo ""

# Step 6: Verify configuration
echo "✅ Step 6: Verifying new configuration..."
echo "New logging status for $MAIN_BUCKET:"
aws s3api get-bucket-logging --bucket "$MAIN_BUCKET" || echo "Logging is disabled (good!)"
echo ""

# Step 7: Show bucket policies (for reference)
echo "📋 Step 7: Current bucket policy for reference..."
echo "Main bucket policy:"
aws s3api get-bucket-policy --bucket "$MAIN_BUCKET" --query Policy --output text 2>/dev/null || echo "No bucket policy set"
echo ""

echo "🎉 S3 Logging Configuration Fix Complete!"
echo "========================================"
echo ""
echo "✅ What was fixed:"
echo "   - Stopped S3 access logs from flooding your main bucket"
echo "   - Created dedicated log bucket: $LOG_BUCKET"
echo "   - Set up proper log retention (if selected)"
echo ""
echo "🎯 Next Steps:"
echo "   1. Run the migration script to clean up existing log files"
echo "   2. Monitor your bucket to confirm no new log files are created"
echo "   3. Set up daily cleanup automation"
echo ""
echo "💡 Cost Savings:"
echo "   - No more ~10,000 files per day being created"
echo "   - Reduced S3 request costs"
echo "   - Reduced storage costs"
echo ""
