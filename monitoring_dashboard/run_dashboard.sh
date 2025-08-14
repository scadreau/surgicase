#!/bin/bash
# Created: 2025-08-14 17:40:31
# Last Modified: 2025-08-14 17:42:59
# Author: Scott Cadreau

# EC2 Monitoring Dashboard Startup Script
# This script starts the Streamlit monitoring dashboard

echo "Starting EC2 Monitoring Dashboard..."

# Change to the dashboard directory
cd "$(dirname "$0")"

# Check if required dependencies are installed
echo "Checking dependencies..."

if ! python -c "import streamlit" 2>/dev/null; then
    echo "Installing missing dependencies..."
    pip install -r requirements.txt --break-system-packages
fi

# Start the Streamlit dashboard
echo "Starting dashboard on port 8501..."
echo "Dashboard will be available at: http://your-server-ip:8501"
echo "Press Ctrl+C to stop the dashboard"

# Run Streamlit with production settings
streamlit run dashboard.py \
    --server.port 8501 \
    --server.address 0.0.0.0 \
    --server.headless true \
    --browser.gatherUsageStats false \
    --server.enableCORS false \
    --server.enableXsrfProtection false
