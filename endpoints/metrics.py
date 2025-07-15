# Created: 2025-01-27
# Last Modified: 2025-07-15 13:51:22

# endpoints/metrics.py
from fastapi import APIRouter, Response, HTTPException
from fastapi.responses import PlainTextResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest, CollectorRegistry, multiprocess
import os
from typing import Dict, Any
import structlog

from utils.monitoring import (
    get_metrics, 
    get_metrics_summary, 
    system_monitor, 
    db_monitor,
    logger
)

router = APIRouter()

@router.get("/metrics")
async def prometheus_metrics():
    """
    Expose Prometheus metrics for scraping
    Returns metrics in Prometheus text format
    """
    try:
        # Update system metrics before generating
        system_monitor.update_system_metrics()
        
        # Generate Prometheus metrics
        metrics_data = get_metrics()
        
        logger.debug("metrics_endpoint_accessed", endpoint="/metrics")
        
        return Response(
            content=metrics_data,
            media_type=CONTENT_TYPE_LATEST,
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0"
            }
        )
    except Exception as e:
        logger.error("metrics_generation_failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to generate metrics: {str(e)}")

@router.get("/metrics/summary")
async def metrics_summary():
    """
    Get a human-readable summary of all metrics
    Useful for debugging and monitoring dashboard
    """
    try:
        summary = get_metrics_summary()
        
        logger.debug("metrics_summary_accessed", endpoint="/metrics/summary")
        
        return {
            "status": "success",
            "data": summary
        }
    except Exception as e:
        logger.error("metrics_summary_generation_failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to generate metrics summary: {str(e)}")

@router.get("/metrics/health")
async def metrics_health():
    """
    Health check specifically for metrics collection
    Verifies that metrics can be generated successfully
    """
    try:
        # Test metrics generation
        metrics_data = get_metrics()
        
        # Test system stats collection
        system_stats = system_monitor.get_system_stats()
        
        # Test database stats collection
        db_stats = db_monitor.get_connection_stats()
        
        health_status = {
            "status": "healthy",
            "metrics_generation": "success",
            "system_stats": "success",
            "database_stats": "success",
            "timestamp": system_stats.get("timestamp", "unknown")
        }
        
        logger.info("metrics_health_check_passed")
        
        return health_status
    except Exception as e:
        logger.error("metrics_health_check_failed", error=str(e))
        
        health_status = {
            "status": "unhealthy",
            "error": str(e),
            "metrics_generation": "failed"
        }
        
        raise HTTPException(status_code=503, detail=health_status)

@router.get("/metrics/system")
async def system_metrics():
    """
    Get detailed system metrics in JSON format
    Useful for monitoring dashboards
    """
    try:
        system_stats = system_monitor.get_system_stats()
        
        logger.debug("system_metrics_accessed", endpoint="/metrics/system")
        
        return {
            "status": "success",
            "data": system_stats
        }
    except Exception as e:
        logger.error("system_metrics_collection_failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to collect system metrics: {str(e)}")

@router.get("/metrics/database")
async def database_metrics():
    """
    Get detailed database metrics in JSON format
    Useful for database monitoring
    """
    try:
        db_stats = db_monitor.get_connection_stats()
        
        logger.debug("database_metrics_accessed", endpoint="/metrics/database")
        
        return {
            "status": "success",
            "data": db_stats
        }
    except Exception as e:
        logger.error("database_metrics_collection_failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to collect database metrics: {str(e)}")

@router.get("/metrics/business")
async def business_metrics():
    """
    Get business-specific metrics in JSON format
    Useful for business intelligence dashboards
    """
    try:
        # This would typically query the database for business metrics
        # For now, we'll return a placeholder structure
        business_stats = {
            "active_cases": "Query from database",
            "active_users": "Query from database", 
            "cases_created_today": "Query from database",
            "users_registered_today": "Query from database",
            "timestamp": "2025-01-27T00:00:00Z"
        }
        
        logger.debug("business_metrics_accessed", endpoint="/metrics/business")
        
        return {
            "status": "success",
            "data": business_stats,
            "note": "Business metrics require database queries - implement based on specific needs"
        }
    except Exception as e:
        logger.error("business_metrics_collection_failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to collect business metrics: {str(e)}")

@router.get("/metrics/endpoints")
async def endpoint_metrics():
    """
    Get endpoint-specific metrics in JSON format
    Useful for API performance monitoring
    """
    try:
        # This would typically aggregate metrics from the monitoring system
        # For now, we'll return a placeholder structure
        endpoint_stats = {
            "total_requests": "Aggregated from Prometheus metrics",
            "average_response_time": "Calculated from histograms",
            "error_rate": "Calculated from counters",
            "most_used_endpoints": "Top N from request counters",
            "slowest_endpoints": "Top N from duration histograms",
            "timestamp": "2025-01-27T00:00:00Z"
        }
        
        logger.debug("endpoint_metrics_accessed", endpoint="/metrics/endpoints")
        
        return {
            "status": "success",
            "data": endpoint_stats,
            "note": "Endpoint metrics require aggregation from Prometheus data - implement based on specific needs"
        }
    except Exception as e:
        logger.error("endpoint_metrics_collection_failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to collect endpoint metrics: {str(e)}")

# Optional: Add metrics for the metrics endpoint itself
@router.get("/metrics/self")
async def metrics_self_monitoring():
    """
    Self-monitoring for the metrics collection system
    Tracks metrics about metrics collection itself
    """
    try:
        self_stats = {
            "metrics_endpoints_available": [
                "/metrics",
                "/metrics/summary", 
                "/metrics/health",
                "/metrics/system",
                "/metrics/database",
                "/metrics/business",
                "/metrics/endpoints",
                "/metrics/self"
            ],
            "prometheus_format_supported": True,
            "json_format_supported": True,
            "health_check_available": True,
            "timestamp": "2025-01-27T00:00:00Z"
        }
        
        logger.debug("metrics_self_monitoring_accessed", endpoint="/metrics/self")
        
        return {
            "status": "success",
            "data": self_stats
        }
    except Exception as e:
        logger.error("metrics_self_monitoring_failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to collect self-monitoring metrics: {str(e)}") 