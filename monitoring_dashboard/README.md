# EC2 Monitoring Dashboard

A Streamlit-based real-time monitoring dashboard for the SurgiCase primary API server (EC2 instance `i-089794865fce8cb91`).

## Overview

This dashboard provides comprehensive monitoring and visualization of:
- **CPU utilization** with warning/critical thresholds
- **Memory usage** with system capacity indicators  
- **Network I/O** traffic patterns
- **Disk I/O** read/write activity
- **System health scoring** and alerts
- **Historical trends** and capacity planning

## Quick Start

### 1. Install Dependencies
```bash
cd /home/scadreau/surgicase/monitoring_dashboard
pip install -r requirements.txt --break-system-packages
```

### 2. Start Dashboard
```bash
./run_dashboard.sh
```

### 3. Access Dashboard
- **URL**: http://your-server-ip:8501
- **Local**: http://localhost:8501 (if running locally)

## Features

### 📊 Real-time Metrics
- Current CPU, memory, network status
- System health score (0-100)
- Last update timestamps
- Status indicators (🟢🟡🔴)

### 📈 Interactive Charts
- **Overview**: Combined system metrics
- **CPU Timeline**: Usage over time with thresholds
- **Memory Timeline**: Utilization trends
- **Network I/O**: Input/output traffic
- **Disk I/O**: Read/write activity

### ⚙️ Dashboard Controls
- **Time Ranges**: 1 hour to 1 week
- **Auto-refresh**: 30-300 second intervals  
- **Manual refresh** button
- **Capacity planning** indicators

### 🚨 Alert Monitoring
- Recent alerts and warnings
- Threshold breach notifications
- System status messages

## Time Range Options

- **Last Hour**: Detailed minute-by-minute data
- **Last 6 Hours**: Full resolution monitoring
- **Last 24 Hours**: Hourly aggregated data
- **Last 3 Days**: Hourly trends
- **Last Week**: Long-term patterns

## System Thresholds

### CPU Utilization
- **🟢 Normal**: 0-70%
- **🟡 Warning**: 70-80%
- **🔴 Critical**: 80%+

### Memory Utilization  
- **🟢 Normal**: 0-70%
- **🟡 Warning**: 70-80%
- **🔴 Critical**: 80%+

## Data Source

The dashboard connects to your existing monitoring infrastructure:
- **Database**: MySQL `ec2_monitoring` table
- **Update Frequency**: Every minute via cron
- **Data Retention**: 2 days (with log rotation)

## File Structure

```
monitoring_dashboard/
├── dashboard.py              # Main Streamlit application
├── requirements.txt          # Python dependencies  
├── run_dashboard.sh         # Startup script
├── README.md               # This documentation
└── utils/
    ├── dashboard_db.py     # Database query functions
    └── dashboard_charts.py # Chart creation functions
```

## Usage During User Onboarding

### Pre-Onboarding
1. Start dashboard: `./run_dashboard.sh`
2. Verify baseline metrics (CPU ~1-2%, Memory ~8-10%)
3. Confirm system health score >90

### During Onboarding
1. Monitor real-time metrics every 15-30 minutes
2. Watch for threshold breaches (yellow/red indicators)
3. Track trends in 6-hour and 24-hour views
4. Check alerts panel for warnings

### Capacity Planning
- **Current baseline**: ~1% CPU, ~8% memory
- **Expected with 100 users**: ~15-30% CPU, ~40-60% memory
- **Safety margins**: CPU <70%, Memory <80%
- **m8g.8xlarge capacity**: 32 vCPUs, 128GB RAM

## Troubleshooting

### Dashboard Won't Start
```bash
# Check dependencies
python -c "import streamlit, plotly, pandas"

# Install missing packages
pip install streamlit plotly pandas --break-system-packages

# Check database connection
python -c "from utils.dashboard_db import get_latest_monitoring_data; print(get_latest_monitoring_data())"
```

### No Data Showing
1. Verify EC2 monitoring cron job is running: `crontab -l`
2. Check monitoring logs: `tail -f tests/ec2_monitoring_cron.log`
3. Verify database connection in main SurgiCase app

### Performance Issues
1. Use longer time ranges (24h+) for better aggregation
2. Disable auto-refresh if not needed
3. Check server resources if dashboard is slow

## Stopping the Dashboard

Press `Ctrl+C` in the terminal where the dashboard is running, or:
```bash
# Find and kill the Streamlit process
ps aux | grep streamlit
kill <process_id>
```

## Security Notes

- Dashboard runs on port 8501 (different from main API on 8000)
- No authentication built-in (runs on internal network)
- Uses existing database connections (no additional credentials)
- Consider nginx reverse proxy for production external access

## Cleanup After Onboarding

When the 6-week monitoring period is complete:
```bash
# Stop the dashboard (Ctrl+C)
# Remove the dashboard directory
cd /home/scadreau/surgicase
rm -rf monitoring_dashboard/
```

## Support

For issues:
1. Check dashboard logs in terminal output
2. Verify EC2 monitoring system is working: `python tests/ec2_monitoring_script.py`
3. Check database connectivity from main application

---

**Purpose**: Temporary monitoring dashboard for 100+ user onboarding period
**Duration**: ~6 weeks (easily removable when complete)
**Impact**: Minimal server resources, independent of main application
