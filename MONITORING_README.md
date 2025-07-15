# SurgiCase Monitoring Implementation

This document describes the comprehensive monitoring implementation for the SurgiCase application, covering both Step 2 (Monitoring Utility Module) and Step 3 (Metrics Endpoint) from the monitoring plan.

## Overview

The monitoring system provides:
- **Prometheus metrics** for operational monitoring
- **Structured logging** with JSON format
- **Custom decorators** for easy metrics collection
- **Database monitoring** utilities
- **System resource monitoring**
- **Business metrics** tracking

## Files Created/Modified

### New Files
- `utils/monitoring.py` - Core monitoring utilities
- `endpoints/metrics.py` - Metrics endpoints for Prometheus scraping
- `test_monitoring.py` - Test script to verify implementation
- `MONITORING_README.md` - This documentation

### Modified Files
- `main.py` - Enabled Prometheus instrumentation and added metrics router
- `core/database.py` - Integrated database connection monitoring

## Installation

1. Install monitoring dependencies:
```bash
pip install -r monitoring-requirements.txt
```

2. Run the test script to verify implementation:
```bash
python test_monitoring.py
```

## Usage

### Starting the Application

```bash
python main.py
```

The application will start with monitoring enabled and expose metrics at:
- `http://localhost:8000/metrics` - Prometheus metrics (text format)
- `http://localhost:8000/metrics/summary` - Human-readable metrics summary
- `http://localhost:8000/metrics/health` - Metrics system health check
- `http://localhost:8000/metrics/system` - System resource metrics (JSON)
- `http://localhost:8000/metrics/database` - Database metrics (JSON)

### Using Monitoring Decorators

#### Track Business Operations
```python
from utils.monitoring import track_business_operation

@track_business_operation("create", "case")
async def create_case(case_data):
    # Your case creation logic
    pass
```

#### Track Database Operations
```python
from utils.monitoring import track_database_operation

@track_database_operation("select", "cases")
async def get_cases():
    # Your database query logic
    pass
```

#### Track Request Metrics
```python
from utils.monitoring import track_request_metrics

@track_request_metrics
async def get_case(case_id: str):
    # Your endpoint logic
    pass
```

### Manual Metrics Recording

```python
from utils.monitoring import business_metrics, system_monitor, db_monitor

# Update business metrics
business_metrics.update_case_metrics(42)
business_metrics.record_case_operation("create", "success", "case-123")

# Update system metrics
system_monitor.update_system_metrics()

# Get connection stats
stats = db_monitor.get_connection_stats()
```

## Metrics Available

### Request Metrics
- `http_requests_total` - Total HTTP requests by method, endpoint, and status
- `http_request_duration_seconds` - Request duration histograms

### Business Metrics
- `case_operations_total` - Case operations by type and status
- `user_operations_total` - User operations by type and status
- `facility_operations_total` - Facility operations by type and status
- `surgeon_operations_total` - Surgeon operations by type and status
- `active_cases_total` - Current number of active cases
- `active_users_total` - Current number of active users
- `case_creation_duration_seconds` - Case creation time summaries

### Database Metrics
- `database_query_duration_seconds` - Query duration by operation and table
- `database_connections_active` - Number of active database connections
- `database_connection_errors_total` - Total database connection errors

### System Metrics
- `system_cpu_usage_percent` - CPU usage percentage
- `system_memory_usage_percent` - Memory usage percentage
- `system_disk_usage_percent` - Disk usage percentage

## Logging

The system uses structured logging with JSON format. Log levels include:
- `DEBUG` - Detailed debugging information
- `INFO` - General information about application flow
- `WARNING` - Warning messages for potential issues
- `ERROR` - Error messages for failed operations

Example log output:
```json
{
  "timestamp": "2025-01-27T14:30:00.123Z",
  "level": "info",
  "logger": "utils.monitoring",
  "event": "request_completed",
  "method": "GET",
  "endpoint": "/case",
  "duration": 0.045,
  "status": "success"
}
```

## Database Monitoring

The database monitoring system tracks:
- Connection creation and closure
- Connection pool utilization
- Query performance
- Connection errors

Database connections are automatically monitored when using the `get_db_connection()` and `close_db_connection()` functions.

## System Monitoring

System monitoring provides real-time metrics for:
- CPU utilization
- Memory usage
- Disk usage
- Process resource consumption

## Prometheus Integration

The application automatically exposes Prometheus metrics at `/metrics`. These metrics can be scraped by:
- Prometheus server
- Grafana dashboards
- Other monitoring tools

### Example Prometheus Configuration
```yaml
scrape_configs:
  - job_name: 'surgicase'
    static_configs:
      - targets: ['localhost:8000']
    metrics_path: '/metrics'
    scrape_interval: 15s
```

## Health Checks

The monitoring system provides several health check endpoints:
- `/health` - Overall application health
- `/metrics/health` - Metrics collection health
- `/health/ready` - Kubernetes readiness check
- `/health/live` - Kubernetes liveness check

## Error Handling

The monitoring system includes comprehensive error handling:
- Graceful degradation when monitoring dependencies are unavailable
- Fallback logging when structured logging fails
- Error tracking and reporting
- Automatic recovery from monitoring failures

## Performance Impact

The monitoring system is designed to have minimal performance impact:
- Asynchronous logging
- Efficient metrics collection
- Optional monitoring features
- Configurable sampling rates

## Configuration

Monitoring behavior can be configured through environment variables:
- `LOG_LEVEL` - Set logging level (DEBUG, INFO, WARNING, ERROR)
- `METRICS_ENABLED` - Enable/disable metrics collection
- `PROMETHEUS_ENABLED` - Enable/disable Prometheus metrics

## Testing

Run the test script to verify the monitoring implementation:
```bash
python test_monitoring.py
```

This will test:
- Module imports
- Metrics generation
- Database monitoring
- System monitoring
- Logging functionality
- Business metrics

## Troubleshooting

### Common Issues

1. **Import Errors**: Ensure monitoring dependencies are installed
2. **Metrics Not Available**: Check that Prometheus instrumentation is enabled
3. **Database Monitoring Not Working**: Verify database connection monitoring is integrated
4. **Logging Issues**: Check log level configuration

### Debug Mode

Enable debug logging to see detailed monitoring information:
```bash
export LOG_LEVEL=DEBUG
python main.py
```

## Next Steps

1. **Deploy and Test**: Deploy the application and verify monitoring works in production
2. **Set Up Dashboards**: Configure Grafana dashboards for visualization
3. **Configure Alerts**: Set up Prometheus alerting rules
4. **Business Metrics**: Implement specific business metric queries
5. **Performance Tuning**: Optimize metrics collection based on usage patterns

## Support

For issues with the monitoring implementation:
1. Check the test script output
2. Review application logs
3. Verify dependencies are installed
4. Test individual components

The monitoring system is designed to be robust and provide comprehensive observability for the SurgiCase application. 