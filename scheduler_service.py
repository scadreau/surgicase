# Created: 2025-01-15
# Last Modified: 2025-07-27 03:43:36
# Author: Scott Cadreau

"""
Standalone scheduler service for SurgiCase weekly case status updates.

This script can be run as a Linux service to handle scheduled case status updates
from status 10 to status 15 every Monday at 08:00 UTC.

Usage:
    python scheduler_service.py

To run as a systemd service, create a service file:
    sudo nano /etc/systemd/system/surgicase-scheduler.service

Service file content:
    [Unit]
    Description=SurgiCase Weekly Case Status Scheduler
    After=network.target

    [Service]
    Type=simple
    User=your-user
    WorkingDirectory=/path/to/surgicase
    ExecStart=/usr/bin/python3 /path/to/surgicase/scheduler_service.py
    Restart=always
    RestartSec=10

    [Install]
    WantedBy=multi-user.target

Then enable and start:
    sudo systemctl daemon-reload
    sudo systemctl enable surgicase-scheduler.service
    sudo systemctl start surgicase-scheduler.service
"""

import logging
import sys
import signal
import os
from utils.weekly_case_status_scheduler import run_scheduler

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/var/log/surgicase-scheduler.log'),
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)

def signal_handler(signum, frame):
    """Handle shutdown signals gracefully."""
    logger.info(f"Received signal {signum}, shutting down scheduler service...")
    sys.exit(0)

def main():
    """Main entry point for the scheduler service."""
    logger.info("Starting SurgiCase Weekly Case Status Scheduler Service...")
    
    # Register signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        # Run the scheduler (this will run indefinitely)
        run_scheduler()
    except KeyboardInterrupt:
        logger.info("Scheduler service interrupted by user")
    except Exception as e:
        logger.error(f"Unexpected error in scheduler service: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main() 