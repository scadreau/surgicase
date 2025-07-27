# SurgiCase Weekly Case Status Scheduler

This document describes the weekly scheduled tasks that automatically update case statuses in the workflow.

## Overview

The scheduler provides automatic weekly case status progression with two separate update jobs:

### Pending Payment Update
- **Source Status**: 10 (cases ready for billing)
- **Target Status**: 15 (pending payment)
- **Schedule**: Monday at 08:00 UTC
- **Function**: `weekly_pending_payment_update()`

### Paid Update
- **Source Status**: 15 (pending payment)
- **Target Status**: 20 (paid/completed)
- **Schedule**: Thursday at 08:00 UTC
- **Function**: `weekly_paid_update()`

Both updates use the existing `bulk_update_case_status` function for reliable processing.

## Files Created

### Core Scheduler Module
- `utils/weekly_case_status_scheduler.py` - Main scheduler implementation
- `scheduler_service.py` - Standalone service runner
- `SCHEDULER_README.md` - This documentation

### Modified Files
- `requirements.txt` - Added `schedule` dependency
- `main.py` - Optional scheduler integration
- `utils/monitoring.py` - Added `record_timing` method to BusinessMetrics class

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
from utils.weekly_case_status_scheduler import (
    run_pending_payment_update_now,
    run_paid_update_now,
    run_update_now  # backward compatibility - runs pending payment update
)

# Run the pending payment update immediately (status 10 -> 15)
run_pending_payment_update_now()

# Run the paid update immediately (status 15 -> 20)
run_paid_update_now()

# Original function (backward compatibility)
run_update_now()
```

## Configuration

### Changing Schedule

To modify the days and times, edit `utils/weekly_case_status_scheduler.py`:

```python
def setup_weekly_scheduler():
    """
    Schedules both weekly update functions:
    - weekly_pending_payment_update: Monday at 08:00 UTC (status 10 -> 15)
    - weekly_paid_update: Thursday at 08:00 UTC (status 15 -> 20)
    
    To change days/times: modify the schedule lines below
    """
    # Schedule pending payment update for Monday at 08:00 UTC
    schedule.every().monday.at("08:00").do(weekly_pending_payment_update)
    
    # Schedule paid update for Thursday at 08:00 UTC
    schedule.every().thursday.at("08:00").do(weekly_paid_update)
    
    # Examples of other schedule options:
    # schedule.every().tuesday.at("10:30").do(weekly_pending_payment_update)
    # schedule.every().friday.at("16:00").do(weekly_paid_update)
    # schedule.every().sunday.at("02:00").do(weekly_pending_payment_update)
```

### Status Configuration

The functions are currently configured as:

**Pending Payment Update:**
- **Find**: Cases with `case_status = 10`
- **Update to**: `case_status = 15`
- **Force**: `false` (prevents backward progression)

**Paid Update:**
- **Find**: Cases with `case_status = 15`
- **Update to**: `case_status = 20`
- **Force**: `false` (prevents backward progression)

To change these values, modify the respective functions in `utils/weekly_case_status_scheduler.py`.

## Functionality

### Main Functions

1. **`get_cases_with_status(status: int)`**
   - Queries database for cases with specified status
   - Returns list of case IDs
   - Handles database connections safely

2. **`weekly_pending_payment_update()`**
   - Scheduled function for status 10 → 15 progression
   - Finds cases ready for billing
   - Updates them to pending payment status
   - Runs Monday at 08:00 UTC

3. **`weekly_paid_update()`**
   - Scheduled function for status 15 → 20 progression
   - Finds cases in pending payment status
   - Updates them to paid/completed status
   - Runs Thursday at 08:00 UTC

4. **`setup_weekly_scheduler()`**
   - Configures both schedules
   - Monday 08:00 UTC for pending payment update
   - Thursday 08:00 UTC for paid update

5. **`run_scheduler()`**
   - Continuous scheduler loop
   - Checks for scheduled tasks every hour (optimized for weekly schedules)
   - Handles both update types
   - Supports graceful shutdown via signal handling

6. **`run_scheduler_in_background()`**
   - Starts scheduler in background thread
   - Non-blocking for main application

7. **Testing Utilities:**
   - **`run_pending_payment_update_now()`** - Test pending payment update immediately
   - **`run_paid_update_now()`** - Test paid update immediately
   - **`run_update_now()`** - Backward compatibility (runs pending payment update)

### Error Handling

The scheduler includes robust error handling:
- Database connection errors
- Case processing exceptions
- Graceful degradation
- Comprehensive logging for both update types
- Signal-based graceful shutdown (SIGTERM, SIGINT)
- Automatic cleanup of daemon threads

### Logging

All operations are logged with appropriate levels:
- **INFO**: Normal operations, results summary
- **WARNING**: Cases that couldn't be updated
- **ERROR**: Database errors, unexpected failures

Log output includes:
- Number of cases found for each status
- Processing results for each update type
- Individual case exceptions
- Performance metrics
- Clear identification of which update job is running

## Monitoring

The scheduler integrates with the existing monitoring system:
- Uses business metrics tracking
- Leverages database monitoring
- Follows established logging patterns
- Tracks both update workflows separately

## Security

- Uses existing database credential management
- Leverages AWS Secrets Manager
- Follows established connection patterns
- No additional security configuration needed

## Troubleshooting

### Common Issues

1. **No cases found**: Normal if no cases have the target status
2. **Database connection errors**: Check AWS credentials and network
3. **Permission errors**: Ensure proper user permissions for log files
4. **Import errors**: Verify all dependencies are installed
5. **BusinessMetrics errors**: Ensure `record_timing` method exists in monitoring.py

### Debugging

Enable debug logging:
```python
import logging
logging.getLogger().setLevel(logging.DEBUG)
```

Test individual updates immediately:
```python
from utils.weekly_case_status_scheduler import (
    run_pending_payment_update_now,
    run_paid_update_now
)

# Test pending payment update (10 -> 15)
run_pending_payment_update_now()

# Test paid update (15 -> 20)
run_paid_update_now()
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

## Production Testing

The scheduler has been successfully tested on live data:

### Test Results ✅
- **Function tested**: `weekly_paid_update()`
- **Cases processed**: 5 cases successfully moved from status 15 → 20
- **Database verification**: All updates confirmed in live database tables
- **Performance**: Clean execution with proper logging and metrics
- **Error handling**: Successfully resolved BusinessMetrics compatibility issue

### Test Commands
```python
# Test pending payment update (10 -> 15)
from utils.weekly_case_status_scheduler import run_pending_payment_update_now
run_pending_payment_update_now()

# Test paid update (15 -> 20) 
from utils.weekly_case_status_scheduler import run_paid_update_now
run_paid_update_now()
```

## Integration Notes

- Uses existing `bulk_update_case_status` endpoint logic
- Maintains transaction safety for both update types
- Follows established database patterns
- Compatible with existing monitoring
- No changes to database schema required
- Backward compatibility maintained with original function names
- Production tested and verified on live data 