# Created: 2025-01-27
# Last Modified: 2025-07-29 01:39:21

# utils/monitoring.py
import time
import functools
import structlog
from typing import Dict, Any, Optional, Callable
from prometheus_client import Counter, Histogram, Gauge, Summary, generate_latest, CONTENT_TYPE_LATEST
from fastapi import Request, Response
import psutil
import threading
from datetime import datetime
import json

# Configure structured logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer()
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

# Get logger instance
logger = structlog.get_logger()

# Prometheus Metrics Definitions

# Request metrics
REQUEST_COUNT = Counter(
    'http_requests_total',
    'Total number of HTTP requests',
    ['method', 'endpoint', 'status']
)

REQUEST_DURATION = Histogram(
    'http_request_duration_seconds',
    'HTTP request duration in seconds',
    ['method', 'endpoint'],
    buckets=[0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
)

# Business metrics
CASE_OPERATIONS = Counter(
    'case_operations_total',
    'Total number of case operations',
    ['operation', 'status']
)

USER_OPERATIONS = Counter(
    'user_operations_total',
    'Total number of user operations',
    ['operation', 'status']
)

FACILITY_OPERATIONS = Counter(
    'facility_operations_total',
    'Total number of facility operations',
    ['operation', 'status']
)

SURGEON_OPERATIONS = Counter(
    'surgeon_operations_total',
    'Total number of surgeon operations',
    ['operation', 'status']
)

# Database metrics
DB_QUERY_DURATION = Histogram(
    'database_query_duration_seconds',
    'Database query duration in seconds',
    ['operation', 'table'],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0]
)

DB_CONNECTION_ACTIVE = Gauge(
    'database_connections_active',
    'Number of active database connections'
)

DB_CONNECTION_ERRORS = Counter(
    'database_connection_errors_total',
    'Total number of database connection errors'
)

# System metrics
SYSTEM_CPU_USAGE = Gauge(
    'system_cpu_usage_percent',
    'System CPU usage percentage'
)

SYSTEM_MEMORY_USAGE = Gauge(
    'system_memory_usage_percent',
    'System memory usage percentage'
)

SYSTEM_DISK_USAGE = Gauge(
    'system_disk_usage_percent',
    'System disk usage percentage'
)

# Custom business metrics
ACTIVE_CASES = Gauge(
    'active_cases_total',
    'Total number of active cases'
)

ACTIVE_USERS = Gauge(
    'active_users_total',
    'Total number of active users'
)

CASE_CREATION_RATE = Summary(
    'case_creation_duration_seconds',
    'Time taken to create a case'
)

# Metrics collection decorators

def track_request_metrics(func: Callable) -> Callable:
    """Decorator to track HTTP request metrics"""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.time()
        status = "success"
        
        try:
            result = func(*args, **kwargs)
            return result
        except Exception as e:
            status = "error"
            raise
        finally:
            duration = time.time() - start_time
            
            # Extract endpoint info from function
            endpoint = func.__name__
            
            # Record metrics
            REQUEST_COUNT.labels(method="GET", endpoint=endpoint, status=status).inc()
            REQUEST_DURATION.labels(method="GET", endpoint=endpoint).observe(duration)
            
            # Log request
            logger.info(
                "request_processed",
                endpoint=endpoint,
                duration=duration,
                status=status
            )
    
    return wrapper

def track_business_operation(operation_type: str, entity: str):
    """Decorator to track business operation metrics"""
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.time()
            status = "success"
            
            try:
                result = func(*args, **kwargs)
                return result
            except Exception as e:
                status = "error"
                logger.error(
                    "business_operation_failed",
                    operation=operation_type,
                    entity=entity,
                    error=str(e)
                )
                raise
            finally:
                duration = time.time() - start_time
                
                # Record business metrics
                if entity == "case":
                    CASE_OPERATIONS.labels(operation=operation_type, status=status).inc()
                    if operation_type == "create":
                        CASE_CREATION_RATE.observe(duration)
                elif entity == "user":
                    USER_OPERATIONS.labels(operation=operation_type, status=status).inc()
                elif entity == "facility":
                    FACILITY_OPERATIONS.labels(operation=operation_type, status=status).inc()
                elif entity == "surgeon":
                    SURGEON_OPERATIONS.labels(operation=operation_type, status=status).inc()
                
                # Log operation
                logger.info(
                    "business_operation_completed",
                    operation=operation_type,
                    entity=entity,
                    duration=duration,
                    status=status
                )
        
        return wrapper
    return decorator

def track_database_operation(operation: str, table: str = "unknown"):
    """Decorator to track database operation metrics"""
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.time()
            status = "success"
            
            try:
                result = func(*args, **kwargs)
                return result
            except Exception as e:
                status = "error"
                logger.error(
                    "database_operation_failed",
                    operation=operation,
                    table=table,
                    error=str(e)
                )
                raise
            finally:
                duration = time.time() - start_time
                
                # Record database metrics
                DB_QUERY_DURATION.labels(operation=operation, table=table).observe(duration)
                
                # Log operation
                logger.info(
                    "database_operation_completed",
                    operation=operation,
                    table=table,
                    duration=duration,
                    status=status
                )
        
        return wrapper
    return decorator

# Database monitoring utilities

# Database monitoring - functional approach
_db_connection_count = 0
_db_connection_lock = threading.Lock()

def db_connection_created():
    """Called when a new database connection is created"""
    global _db_connection_count
    with _db_connection_lock:
        _db_connection_count += 1
        DB_CONNECTION_ACTIVE.set(_db_connection_count)
        logger.debug("database_connection_created", active_connections=_db_connection_count)

def db_connection_closed():
    """Called when a database connection is closed"""
    global _db_connection_count
    with _db_connection_lock:
        _db_connection_count = max(0, _db_connection_count - 1)
        DB_CONNECTION_ACTIVE.set(_db_connection_count)
        logger.debug("database_connection_closed", active_connections=_db_connection_count)

def get_db_connection_stats() -> Dict[str, Any]:
    """Get current database connection statistics"""
    return {
        "active_connections": _db_connection_count,
        "timestamp": datetime.utcnow().isoformat() + "Z"
    }

# System monitoring utilities

def update_system_metrics():
    """Update system resource metrics"""
    try:
        # CPU usage
        cpu_percent = psutil.cpu_percent(interval=0.1)
        SYSTEM_CPU_USAGE.set(cpu_percent)
        
        # Memory usage
        memory = psutil.virtual_memory()
        SYSTEM_MEMORY_USAGE.set(memory.percent)
        
        # Disk usage
        disk = psutil.disk_usage('/')
        SYSTEM_DISK_USAGE.set(disk.percent)
        
        logger.debug(
            "system_metrics_updated",
            cpu_percent=cpu_percent,
            memory_percent=memory.percent,
            disk_percent=disk.percent
        )
        
    except Exception as e:
        logger.error("system_metrics_update_failed", error=str(e))

def get_system_stats() -> Dict[str, Any]:
    """Get current system statistics"""
    try:
        cpu_percent = psutil.cpu_percent(interval=0.1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        
        return {
            "cpu_percent": round(cpu_percent, 2),
            "memory_percent": round(memory.percent, 2),
            "memory_available_gb": round(memory.available / (1024**3), 2),
            "disk_percent": round(disk.percent, 2),
            "disk_free_gb": round(disk.free / (1024**3), 2),
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
    except Exception as e:
        logger.error("system_stats_collection_failed", error=str(e))
        return {"error": str(e)}

# Business metrics utilities

def update_case_metrics(active_count: int):
    """Update active cases metric"""
    ACTIVE_CASES.set(active_count)
    logger.debug("case_metrics_updated", active_cases=active_count)

def update_user_metrics(active_count: int):
    """Update active users metric"""
    ACTIVE_USERS.set(active_count)
    logger.debug("user_metrics_updated", active_users=active_count)

def record_case_operation(operation: str, status: str, case_id: Optional[str] = None):
    """Record a case operation"""
    CASE_OPERATIONS.labels(operation=operation, status=status).inc()
    logger.info(
        "case_operation_recorded",
        operation=operation,
        status=status,
        case_id=case_id
    )

def record_user_operation(operation: str, status: str, user_id: Optional[str] = None):
    """Record a user operation"""
    USER_OPERATIONS.labels(operation=operation, status=status).inc()
    logger.info(
        "user_operation_recorded",
        operation=operation,
        status=status,
        user_id=user_id
    )

def record_surgeon_operation(operation: str, status: str, surgeon_id: Optional[int] = None):
    """Record a surgeon operation"""
    SURGEON_OPERATIONS.labels(operation=operation, status=status).inc()
    logger.info(
        "surgeon_operation_recorded",
        operation=operation,
        status=status,
        surgeon_id=surgeon_id
    )

def record_facility_operation(operation: str, status: str, facility_id: Optional[int] = None):
    """Record a facility operation"""
    FACILITY_OPERATIONS.labels(operation=operation, status=status).inc()
    logger.info(
        "facility_operation_recorded",
        operation=operation,
        status=status,
        facility_id=facility_id
    )

def record_utility_operation(operation: str, status: str):
    """Record a utility operation"""
    logger.info(
        "utility_operation_recorded",
        operation=operation,
        status=status
    )

def record_timing(operation: str, duration_ms: float):
    """Record operation timing metrics"""
    logger.info(
        "operation_timing_recorded",
        operation=operation,
        duration_ms=duration_ms
    )

# Request/Response monitoring middleware

def monitor_request(request: Request, call_next):
    """FastAPI middleware for request monitoring"""
    start_time = time.time()
    
    # Extract request info
    method = request.method
    endpoint = request.url.path
    user_agent = request.headers.get("user-agent", "unknown")
    client_ip = request.client.host if request.client else "unknown"
    
    # Log request start
    logger.info(
        "request_started",
        method=method,
        endpoint=endpoint,
        user_agent=user_agent,
        client_ip=client_ip
    )
    
    try:
        response = call_next(request)
        status = "success"
        
        # Record metrics
        REQUEST_COUNT.labels(method=method, endpoint=endpoint, status=status).inc()
        
        return response
    except Exception as e:
        status = "error"
        logger.error(
            "request_failed",
            method=method,
            endpoint=endpoint,
            error=str(e)
        )
        raise
    finally:
        duration = time.time() - start_time
        REQUEST_DURATION.labels(method=method, endpoint=endpoint).observe(duration)
        
        # Log request completion
        logger.info(
            "request_completed",
            method=method,
            endpoint=endpoint,
            duration=duration,
            status=status
        )

# Backward compatibility objects for existing code
class _DatabaseMonitorCompat:
    """Compatibility wrapper for old DatabaseMonitor usage"""
    def connection_created(self): return db_connection_created()
    def connection_closed(self): return db_connection_closed()
    def get_connection_stats(self): return get_db_connection_stats()

class _SystemMonitorCompat:
    """Compatibility wrapper for old SystemMonitor usage"""
    def update_system_metrics(self): return update_system_metrics()
    def get_system_stats(self): return get_system_stats()

class _BusinessMetricsCompat:
    """Compatibility wrapper for old BusinessMetrics usage"""
    def update_case_metrics(self, active_count: int): return update_case_metrics(active_count)
    def update_user_metrics(self, active_count: int): return update_user_metrics(active_count)
    def record_case_operation(self, operation: str, status: str, case_id: Optional[str] = None): return record_case_operation(operation, status, case_id)
    def record_user_operation(self, operation: str, status: str, user_id: Optional[str] = None): return record_user_operation(operation, status, user_id)
    def record_surgeon_operation(self, operation: str, status: str, surgeon_id: Optional[int] = None): return record_surgeon_operation(operation, status, surgeon_id)
    def record_facility_operation(self, operation: str, status: str, facility_id: Optional[int] = None): return record_facility_operation(operation, status, facility_id)
    def record_utility_operation(self, operation: str, status: str): return record_utility_operation(operation, status)
    def record_timing(self, operation: str, duration_ms: float): return record_timing(operation, duration_ms)

# Initialize compatibility instances for existing code
db_monitor = _DatabaseMonitorCompat()
system_monitor = _SystemMonitorCompat()
business_metrics = _BusinessMetricsCompat()

# Export all metrics for Prometheus
def get_metrics():
    """Get all Prometheus metrics in text format"""
    return generate_latest()

# Utility function to get all metrics as JSON for debugging
def get_metrics_summary() -> Dict[str, Any]:
    """Get a summary of all metrics for debugging purposes"""
    return {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "database": get_db_connection_stats(),
        "system": get_system_stats(),
        "metrics_info": {
            "request_count": "Total HTTP requests by method, endpoint, and status",
            "request_duration": "HTTP request duration histograms",
            "case_operations": "Case-related business operations",
            "user_operations": "User-related business operations",
            "facility_operations": "Facility-related business operations",
            "surgeon_operations": "Surgeon-related business operations",
            "db_query_duration": "Database query performance",
            "db_connections": "Database connection pool status",
            "system_resources": "CPU, memory, and disk usage"
        }
    } 