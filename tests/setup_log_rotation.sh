#!/bin/bash
# Created: 2025-08-14 16:15:20
# Last Modified: 2025-08-14 16:17:45
# Author: Scott Cadreau

# Setup script for EC2 monitoring log rotation
# This script configures automatic log rotation every 6 hours

echo "Setting up EC2 monitoring log rotation..."

# Define paths
SCRIPT_DIR="/home/scadreau/surgicase/tests"
ROTATION_SCRIPT="$SCRIPT_DIR/rotate_monitoring_logs.py"
CRON_ENTRY_ROTATION="0 */6 * * * cd /home/scadreau/surgicase && python $ROTATION_SCRIPT >> $SCRIPT_DIR/log_rotation.log 2>&1"

# Check if the rotation script exists
if [ ! -f "$ROTATION_SCRIPT" ]; then
    echo "Error: Log rotation script not found at $ROTATION_SCRIPT"
    exit 1
fi

# Make sure the script is executable
chmod +x "$ROTATION_SCRIPT"

# Check if log rotation cron entry already exists
if crontab -l 2>/dev/null | grep -q "rotate_monitoring_logs.py"; then
    echo "Log rotation cron job already exists"
    echo "Current log rotation cron jobs:"
    crontab -l | grep "rotate_monitoring_logs.py"
else
    # Add the log rotation cron job
    echo "Adding log rotation cron job..."
    (crontab -l 2>/dev/null; echo "$CRON_ENTRY_ROTATION") | crontab -
    
    if [ $? -eq 0 ]; then
        echo "✅ Log rotation cron job added successfully!"
        echo "Log rotation will run every 6 hours"
        echo "Rotation logs will be written to: $SCRIPT_DIR/log_rotation.log"
    else
        echo "❌ Failed to add log rotation cron job"
        exit 1
    fi
fi

echo ""
echo "📊 Log Rotation Configuration:"
echo "- Rotation frequency: Every 6 hours (0 */6 * * *)"
echo "- Log retention: 2 days"
echo "- Compression: Enabled"
echo "- Rotation script: $ROTATION_SCRIPT"
echo "- Rotation logs: $SCRIPT_DIR/log_rotation.log"
echo ""
echo "📝 Current cron jobs:"
crontab -l | grep -E "(ec2_monitoring|rotate_monitoring)"
echo ""
echo "🔍 Log files that will be rotated:"
echo "- $SCRIPT_DIR/ec2_monitoring.log"
echo "- $SCRIPT_DIR/ec2_monitoring_cron.log"
echo ""
echo "📝 To test log rotation manually:"
echo "python $ROTATION_SCRIPT"
echo ""
echo "📝 To view rotation logs:"
echo "tail -f $SCRIPT_DIR/log_rotation.log"
echo ""
echo "🚨 Log Rotation Schedule:"
echo "- New log files: Every 6 hours"
echo "- Old files deleted: After 2 days"
echo "- Compressed files: Automatic"
echo ""
