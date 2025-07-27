# SurgiCase Weekly Case Status Scheduler

This document describes the weekly scheduled task that automatically updates case statuses from 10 to 15.

## Overview

The scheduler provides automatic weekly case status progression:
- **Source Status**: 10 (cases ready for status progression)
- **Target Status**: 15 (next stage in case processing)
- **Schedule**: Monday at 08:00 UTC (configurable)
- **Method**: Uses existing `bulk_update_case_status` function

## Files Created

### Core Scheduler Module
- `utils/weekly_case_status_scheduler.py` - Main scheduler implementation
- `scheduler_service.py` - Standalone service runner
- `SCHEDULER_README.md` - This documentation

### Modified Files
- `requirements.txt` - Added `schedule` dependency
- `main.py` - Optional scheduler integration

## Installation

1. Install the new dependency:
```bash
pip install schedule
```

2. Or install from requirements:
```bash
pip install -r requirements.txt
```

## Usage Options

### Option 1: Standalone Service (Recommended for Production)

Run as a separate Linux service:

```bash
# Test run
python scheduler_service.py

# Create systemd service
sudo nano /etc/systemd/system/surgicase-scheduler.service
```

Service file content:
```ini
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
```

Enable and start:
```bash
sudo systemctl daemon-reload
sudo systemctl enable surgicase-scheduler.service
sudo systemctl start surgicase-scheduler.service
sudo systemctl status surgicase-scheduler.service
```

### Option 2: Integrated with Main Application

Run alongside the FastAPI application:

```bash
# Enable scheduler in main app
export ENABLE_SCHEDULER=true
python main.py
```

### Option 3: Manual Testing

Test the scheduler functionality immediately:

```python
from utils.weekly_case_status_scheduler import run_update_now

# Run the update immediately (for testing)
run_update_now()
```

## Configuration

### Changing Schedule

To modify the day and time, edit `utils/weekly_case_status_scheduler.py`:

```python
def setup_weekly_scheduler():
    # Change day and time below as needed
    # Currently set to Monday at 08:00 UTC
    
    # Examples:
    # schedule.every().tuesday.at("10:30").do(weekly_case_status_update)  # Tuesday 10:30 UTC
    # schedule.every().friday.at("16:00").do(weekly_case_status_update)   # Friday 16:00 UTC
    # schedule.every().sunday.at("02:00").do(weekly_case_status_update)   # Sunday 02:00 UTC
    
    schedule.every().monday.at("08:00").do(weekly_case_status_update)
```

### Status Configuration

The function is currently configured to:
- **Find**: Cases with `case_status = 10`
- **Update to**: `case_status = 15`
- **Force**: `false` (prevents backward progression)

To change these values, modify the `weekly_case_status_update()` function in `utils/weekly_case_status_scheduler.py`.

## Functionality

### Main Functions

1. **`get_cases_with_status(status: int)`**
   - Queries database for cases with specified status
   - Returns list of case IDs
   - Handles database connections safely

2. **`weekly_case_status_update()`**
   - Main scheduled function
   - Finds cases with status 10
   - Updates them to status 15
   - Logs comprehensive results

3. **`setup_weekly_scheduler()`**
   - Configures the schedule
   - Currently: Monday at 08:00 UTC

4. **`run_scheduler()`**
   - Continuous scheduler loop
   - Checks for scheduled tasks every minute

5. **`run_scheduler_in_background()`**
   - Starts scheduler in background thread
   - Non-blocking for main application

6. **`run_update_now()`**
   - Utility for immediate testing
   - Bypasses schedule timing

### Error Handling

The scheduler includes robust error handling:
- Database connection errors
- Case processing exceptions
- Graceful degradation
- Comprehensive logging

### Logging

All operations are logged with appropriate levels:
- **INFO**: Normal operations, results summary
- **WARNING**: Cases that couldn't be updated
- **ERROR**: Database errors, unexpected failures

Log output includes:
- Number of cases found
- Processing results
- Individual case exceptions
- Performance metrics

## Monitoring

The scheduler integrates with the existing monitoring system:
- Uses business metrics tracking
- Leverages database monitoring
- Follows established logging patterns

## Security

- Uses existing database credential management
- Leverages AWS Secrets Manager
- Follows established connection patterns
- No additional security configuration needed

## Troubleshooting

### Common Issues

1. **No cases found**: Normal if no cases have status 10
2. **Database connection errors**: Check AWS credentials and network
3. **Permission errors**: Ensure proper user permissions for log files
4. **Import errors**: Verify all dependencies are installed

### Debugging

Enable debug logging:
```python
import logging
logging.getLogger().setLevel(logging.DEBUG)
```

Test immediately:
```python
from utils.weekly_case_status_scheduler import run_update_now
run_update_now()
```

### Service Status

Check service status:
```bash
sudo systemctl status surgicase-scheduler.service
sudo journalctl -u surgicase-scheduler.service -f
```

View logs:
```bash
tail -f /var/log/surgicase-scheduler.log
```

## Integration Notes

- Uses existing `bulk_update_case_status` endpoint logic
- Maintains transaction safety
- Follows established database patterns
- Compatible with existing monitoring
- No changes to database schema required 