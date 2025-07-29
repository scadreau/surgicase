# Created: 2025-07-15 09:20:13
# Last Modified: 2025-07-29 01:46:58
# Author: Scott Cadreau

# endpoints/health.py
from fastapi import APIRouter, HTTPException
from core.database import get_db_connection
from utils.monitoring import track_business_operation, business_metrics
import boto3
import os
import time
import json
from datetime import datetime
from typing import Dict, Any

router = APIRouter()

def get_logger():
    """Simple logger for health checks"""
    import logging
    logging.basicConfig(level=logging.INFO)
    return logging.getLogger(__name__)

logger = get_logger()

def check_database_health() -> Dict[str, Any]:
    """Check database connectivity and health"""
    start_time = time.time()
    connection = None
    try:
        connection = get_db_connection()
        # Test a simple query
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        
        duration = time.time() - start_time
        logger.info(f"Database health check passed in {duration:.3f}s")
        
        return {
            "status": "healthy",
            "response_time_ms": round(duration * 1000, 2),
            "details": "Database connection and query test successful"
        }
    except Exception as e:
        duration = time.time() - start_time
        logger.error(f"Database health check failed after {duration:.3f}s: {str(e)}")
        
        return {
            "status": "unhealthy",
            "response_time_ms": round(duration * 1000, 2),
            "details": f"Database connection failed: {str(e)}",
            "error": str(e)
        }
    finally:
        # Always return connection to pool
        if connection:
            from core.database import close_db_connection
            close_db_connection(connection)

def check_aws_secrets_manager_health() -> Dict[str, Any]:
    """Check AWS Secrets Manager connectivity"""
    start_time = time.time()
    try:
        region = os.environ.get("AWS_REGION", "us-east-1")
        client = boto3.client("secretsmanager", region_name=region)
        
        # Test connectivity by listing secrets (limited to 1 to avoid performance impact)
        response = client.list_secrets(MaxResults=1)
        
        duration = time.time() - start_time
        logger.info(f"AWS Secrets Manager health check passed in {duration:.3f}s")
        
        return {
            "status": "healthy",
            "response_time_ms": round(duration * 1000, 2),
            "details": "AWS Secrets Manager connectivity successful",
            "region": region
        }
    except Exception as e:
        duration = time.time() - start_time
        logger.error(f"AWS Secrets Manager health check failed after {duration:.3f}s: {str(e)}")
        
        return {
            "status": "unhealthy",
            "response_time_ms": round(duration * 1000, 2),
            "details": f"AWS Secrets Manager connectivity failed: {str(e)}",
            "error": str(e)
        }

def check_system_resources() -> Dict[str, Any]:
    """Check system resource usage"""
    try:
        import psutil
        
        cpu_percent = psutil.cpu_percent(interval=0.1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        
        # Determine memory status
        memory_status = "healthy"
        if memory.percent > 90:
            memory_status = "critical"
        elif memory.percent > 80:
            memory_status = "warning"
        
        # Determine disk status
        disk_status = "healthy"
        if disk.percent > 90:
            disk_status = "critical"
        elif disk.percent > 80:
            disk_status = "warning"
        
        logger.info(f"System resources: CPU {cpu_percent}%, Memory {memory.percent}%, Disk {disk.percent}%")
        
        return {
            "status": "healthy" if memory_status == "healthy" and disk_status == "healthy" else "warning",
            "cpu_percent": round(cpu_percent, 2),
            "memory": {
                "percent": round(memory.percent, 2),
                "available_gb": round(memory.available / (1024**3), 2),
                "total_gb": round(memory.total / (1024**3), 2),
                "status": memory_status
            },
            "disk": {
                "percent": round(disk.percent, 2),
                "free_gb": round(disk.free / (1024**3), 2),
                "total_gb": round(disk.total / (1024**3), 2),
                "status": disk_status
            }
        }
    except ImportError:
        logger.warning("psutil not available, skipping system resource check")
        return {
            "status": "unknown",
            "details": "psutil not installed, system resource monitoring unavailable"
        }
    except Exception as e:
        logger.error(f"System resource check failed: {str(e)}")
        return {
            "status": "unhealthy",
            "details": f"System resource check failed: {str(e)}",
            "error": str(e)
        }

@router.get("/health")
@track_business_operation("check", "health")
def health_check():
    """
    Comprehensive health check endpoint with detailed component status
    """
    start_time = time.time()
    
    # Perform all health checks
    db_health = check_database_health()
    aws_health = check_aws_secrets_manager_health()
    system_health = check_system_resources()
    
    # Calculate overall health status
    critical_components = [db_health, aws_health]
    warning_components = [system_health]
    
    overall_status = "healthy"
    if any(comp["status"] == "unhealthy" for comp in critical_components):
        overall_status = "unhealthy"
    elif any(comp["status"] == "warning" for comp in warning_components):
        overall_status = "degraded"
    
    total_duration = time.time() - start_time
    
    health_response = {
        "status": overall_status,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "response_time_ms": round(total_duration * 1000, 2),
        "components": {
            "database": db_health,
            "aws_secrets_manager": aws_health,
            "system_resources": system_health
        },
        "version": "1.0.0",
        "service": "surgicase-api"
    }
    
    # Log health check result
    if overall_status == "healthy":
        logger.info(f"Health check passed in {total_duration:.3f}s")
    elif overall_status == "degraded":
        logger.warning(f"Health check degraded in {total_duration:.3f}s")
    else:
        logger.error(f"Health check failed in {total_duration:.3f}s")
    
    # Return appropriate HTTP status
    if overall_status == "unhealthy":
        raise HTTPException(status_code=503, detail=health_response)
    
    return health_response

@router.get("/health/ready")
@track_business_operation("check", "health_ready")
def readiness_check():
    """
    Kubernetes readiness check - indicates if the service is ready to receive traffic
    """
    try:
        health = health_check()
        
        # For readiness, we only care about critical components
        critical_components = [
            health["components"]["database"]["status"],
            health["components"]["aws_secrets_manager"]["status"]
        ]
        
        if any(status == "unhealthy" for status in critical_components):
            raise HTTPException(status_code=503, detail="Service not ready")
        
        return {"status": "ready"}
        
    except Exception as e:
        logger.error(f"Readiness check failed: {str(e)}")
        raise HTTPException(status_code=503, detail="Service not ready")

@router.get("/health/live")
@track_business_operation("check", "health_live")
def liveness_check():
    """
    Kubernetes liveness check - indicates if the service is alive and should not be restarted
    """
    try:
        # Simple check - just verify the service is responding
        return {"status": "alive", "timestamp": datetime.utcnow().isoformat() + "Z"}
    except Exception as e:
        logger.error(f"Liveness check failed: {str(e)}")
        raise HTTPException(status_code=503, detail="Service not alive")

@router.get("/health/simple")
@track_business_operation("check", "health_simple")
def simple_health_check():
    """
    Simple health check for load balancers and basic monitoring
    """
    return {"status": "healthy"}