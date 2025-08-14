#!/bin/bash
# Created: 2025-08-14 15:55:48
# Last Modified: 2025-08-14 15:58:57
# Author: Scott Cadreau

# Setup script for EC2 monitoring cron job
# This script will configure a cron job to run the EC2 monitoring script every minute

echo "Setting up EC2 monitoring cron job..."

# Define paths
SCRIPT_DIR="/home/scadreau/surgicase/tests"
SCRIPT_PATH="$SCRIPT_DIR/ec2_monitoring_script.py"
LOG_PATH="$SCRIPT_DIR/ec2_monitoring_cron.log"
CRON_ENTRY="* * * * * cd /home/scadreau/surgicase && python $SCRIPT_PATH >> $LOG_PATH 2>&1"

# Check if the monitoring script exists
if [ ! -f "$SCRIPT_PATH" ]; then
    echo "Error: Monitoring script not found at $SCRIPT_PATH"
    exit 1
fi

# Make sure the script is executable
chmod +x "$SCRIPT_PATH"

# Create the log directory if it doesn't exist
mkdir -p "$SCRIPT_DIR"

# Check if cron entry already exists
if crontab -l 2>/dev/null | grep -q "ec2_monitoring_script.py"; then
    echo "Cron job for EC2 monitoring already exists"
    echo "Current monitoring cron jobs:"
    crontab -l | grep "ec2_monitoring_script.py"
else
    # Add the cron job
    echo "Adding cron job for EC2 monitoring..."
    (crontab -l 2>/dev/null; echo "$CRON_ENTRY") | crontab -
    
    if [ $? -eq 0 ]; then
        echo "✅ Cron job added successfully!"
        echo "The monitoring script will run every minute"
        echo "Logs will be written to: $LOG_PATH"
    else
        echo "❌ Failed to add cron job"
        exit 1
    fi
fi

echo ""
echo "📊 Monitoring Configuration:"
echo "- Instance ID: i-099fb57644b0c33ba"
echo "- Frequency: Every minute"
echo "- Log file: $LOG_PATH"
echo "- Database table: ec2_monitoring"
echo ""
echo "📝 To view current cron jobs: crontab -l"
echo "📝 To remove the monitoring cron job: crontab -e (then delete the line)"
echo "📝 To view monitoring logs: tail -f $LOG_PATH"
echo ""
echo "🚨 Important Notes:"
echo "- Make sure AWS credentials are configured (aws configure)"
echo "- Ensure CloudWatch agent is installed on the EC2 instance for memory metrics"
echo "- The m8g.2xlarge instance should easily handle 100+ concurrent users"
echo ""
