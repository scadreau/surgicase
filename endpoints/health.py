# Created: 2025-07-15 09:20:13
# Last Modified: 2025-08-20 09:23:50
# Author: Scott Cadreau

# endpoints/health.py
from fastapi import APIRouter, HTTPException
from core.database import get_db_connection
from utils.monitoring import track_business_operation, business_metrics
import boto3
import os
import time
import json
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

router = APIRouter()

def get_logger():
    """Simple logger for health checks"""
    import logging
    logging.basicConfig(level=logging.INFO)
    return logging.getLogger(__name__)

logger = get_logger()

# Global cache for health check results
_health_cache = {
    "last_check": None,
    "results": None,
    "config": None
}

def load_health_config() -> Dict[str, Any]:
    """Load health configuration from JSON file"""
    if _health_cache["config"] is not None:
        return _health_cache["config"]
    
    try:
        config_path = Path(__file__).parent.parent / "utils" / "health_config.json"
        with open(config_path, 'r') as f:
            config = json.load(f)
        _health_cache["config"] = config
        return config
    except Exception as e:
        logger.error(f"Failed to load health config: {str(e)}")
        # Return minimal config as fallback
        return {
            "aws_resources": {"critical_services": [], "non_critical_services": []},
            "health_thresholds": {"database": {"healthy_ms": 500, "degraded_ms": 2000}, "aws_apis": {"healthy_ms": 1000, "degraded_ms": 3000}},
            "cache_settings": {"cache_duration_seconds": 600, "enable_caching": True}
        }

def is_cache_valid() -> bool:
    """Check if cached health results are still valid"""
    config = load_health_config()
    if not config["cache_settings"]["enable_caching"]:
        return False
    
    if _health_cache["last_check"] is None or _health_cache["results"] is None:
        return False
    
    cache_duration = timedelta(seconds=config["cache_settings"]["cache_duration_seconds"])
    return datetime.utcnow() - _health_cache["last_check"] < cache_duration

def get_status_from_response_time(response_time_ms: float, service_type: str) -> str:
    """Determine health status based on response time and service type"""
    config = load_health_config()
    thresholds = config["health_thresholds"].get(service_type, config["health_thresholds"]["aws_apis"])
    
    if response_time_ms <= thresholds["healthy_ms"]:
        return "healthy"
    elif response_time_ms <= thresholds["degraded_ms"]:
        return "degraded"
    else:
        return "unhealthy"

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

def check_amplify_health() -> Dict[str, Any]:
    """Check AWS Amplify app health"""
    start_time = time.time()
    try:
        config = load_health_config()
        amplify_config = None
        
        # Find amplify config
        for service in config["aws_resources"]["non_critical_services"]:
            if service["type"] == "amplify":
                amplify_config = service["config"]
                break
        
        if not amplify_config:
            return {
                "status": "unknown",
                "details": "Amplify configuration not found"
            }
        
        region = amplify_config.get("region", "us-east-1")
        app_id = amplify_config["app_id"]
        
        client = boto3.client("amplify", region_name=region)
        response = client.get_app(appId=app_id)
        
        app = response["app"]
        duration = time.time() - start_time
        response_time_ms = round(duration * 1000, 2)
        
        # Check app status
        if app["platform"] and app["name"]:
            status = get_status_from_response_time(response_time_ms, "aws_apis")
            logger.info(f"Amplify health check passed in {duration:.3f}s")
            
            return {
                "status": status,
                "response_time_ms": response_time_ms,
                "details": f"Amplify app '{app['name']}' is accessible",
                "app_name": app["name"],
                "platform": app["platform"],
                "region": region
            }
        else:
            return {
                "status": "unhealthy",
                "response_time_ms": response_time_ms,
                "details": "Amplify app data incomplete",
                "region": region
            }
            
    except Exception as e:
        duration = time.time() - start_time
        logger.error(f"Amplify health check failed after {duration:.3f}s: {str(e)}")
        
        return {
            "status": "unhealthy",
            "response_time_ms": round(duration * 1000, 2),
            "details": f"Amplify connectivity failed: {str(e)}",
            "error": str(e)
        }

def check_api_gateway_health() -> Dict[str, Any]:
    """Check AWS API Gateway health"""
    start_time = time.time()
    try:
        config = load_health_config()
        gateway_config = None
        
        # Find API Gateway config
        for service in config["aws_resources"]["critical_services"]:
            if service["type"] == "api_gateway":
                gateway_config = service["config"]
                break
        
        if not gateway_config:
            return {
                "status": "unknown",
                "details": "API Gateway configuration not found"
            }
        
        region = gateway_config.get("region", "us-east-1")
        api_id = gateway_config["api_id"]
        
        client = boto3.client("apigateway", region_name=region)
        response = client.get_rest_api(restApiId=api_id)
        
        duration = time.time() - start_time
        response_time_ms = round(duration * 1000, 2)
        
        # Check API Gateway status
        if response["id"] and response["name"]:
            status = get_status_from_response_time(response_time_ms, "aws_apis")
            logger.info(f"API Gateway health check passed in {duration:.3f}s")
            
            return {
                "status": status,
                "response_time_ms": response_time_ms,
                "details": f"API Gateway '{response['name']}' is accessible",
                "api_name": response["name"],
                "api_id": response["id"],
                "region": region
            }
        else:
            return {
                "status": "unhealthy",
                "response_time_ms": response_time_ms,
                "details": "API Gateway data incomplete",
                "region": region
            }
            
    except Exception as e:
        duration = time.time() - start_time
        logger.error(f"API Gateway health check failed after {duration:.3f}s: {str(e)}")
        
        return {
            "status": "unhealthy",
            "response_time_ms": round(duration * 1000, 2),
            "details": f"API Gateway connectivity failed: {str(e)}",
            "error": str(e)
        }

def check_s3_health() -> Dict[str, Any]:
    """Check AWS S3 bucket health"""
    start_time = time.time()
    try:
        config = load_health_config()
        s3_config = None
        
        # Find S3 config
        for service in config["aws_resources"]["non_critical_services"]:
            if service["type"] == "s3":
                s3_config = service["config"]
                break
        
        if not s3_config:
            return {
                "status": "unknown",
                "details": "S3 configuration not found"
            }
        
        region = s3_config.get("region", "us-east-1")
        bucket_name = s3_config["bucket_name"]
        
        client = boto3.client("s3", region_name=region)
        
        # Test bucket accessibility - head_bucket is lightweight
        client.head_bucket(Bucket=bucket_name)
        
        # Test read access by listing root directory (with prefix to limit results)
        response = client.list_objects_v2(Bucket=bucket_name, MaxKeys=1)
        
        duration = time.time() - start_time
        response_time_ms = round(duration * 1000, 2)
        
        status = get_status_from_response_time(response_time_ms, "aws_apis")
        logger.info(f"S3 health check passed in {duration:.3f}s")
        
        return {
            "status": status,
            "response_time_ms": response_time_ms,
            "details": f"S3 bucket '{bucket_name}' is accessible",
            "bucket_name": bucket_name,
            "region": region,
            "has_objects": "Contents" in response
        }
        
    except Exception as e:
        duration = time.time() - start_time
        logger.error(f"S3 health check failed after {duration:.3f}s: {str(e)}")
        
        return {
            "status": "unhealthy",
            "response_time_ms": round(duration * 1000, 2),
            "details": f"S3 connectivity failed: {str(e)}",
            "error": str(e)
        }

def check_ec2_health() -> Dict[str, Any]:
    """Check EC2 instances health"""
    start_time = time.time()
    try:
        config = load_health_config()
        ec2_config = None
        
        # Find EC2 config
        for service in config["aws_resources"]["critical_services"]:
            if service["type"] == "ec2":
                ec2_config = service["config"]
                break
        
        if not ec2_config:
            return {
                "status": "unknown",
                "details": "EC2 configuration not found"
            }
        
        region = ec2_config.get("region", "us-east-1")
        instance_ids = ec2_config["instance_ids"]
        
        client = boto3.client("ec2", region_name=region)
        
        # Check instance status
        response = client.describe_instance_status(
            InstanceIds=instance_ids,
            IncludeAllInstances=True
        )
        
        duration = time.time() - start_time
        response_time_ms = round(duration * 1000, 2)
        
        instance_statuses = []
        all_healthy = True
        
        for status_info in response["InstanceStatuses"]:
            instance_id = status_info["InstanceId"]
            instance_state = status_info["InstanceState"]["Name"]
            system_status = status_info.get("SystemStatus", {}).get("Status", "unknown")
            instance_status = status_info.get("InstanceStatus", {}).get("Status", "unknown")
            
            is_healthy = (
                instance_state == "running" and 
                system_status == "ok" and 
                instance_status == "ok"
            )
            
            if not is_healthy:
                all_healthy = False
            
            instance_statuses.append({
                "instance_id": instance_id,
                "state": instance_state,
                "system_status": system_status,
                "instance_status": instance_status,
                "healthy": is_healthy
            })
        
        if all_healthy:
            status = get_status_from_response_time(response_time_ms, "aws_apis")
            logger.info(f"EC2 health check passed in {duration:.3f}s")
        else:
            status = "unhealthy"
            logger.warning(f"EC2 health check found unhealthy instances in {duration:.3f}s")
        
        return {
            "status": status,
            "response_time_ms": response_time_ms,
            "details": f"Checked {len(instance_ids)} EC2 instance(s)",
            "region": region,
            "instances": instance_statuses,
            "total_instances": len(instance_ids),
            "healthy_instances": sum(1 for inst in instance_statuses if inst["healthy"])
        }
        
    except Exception as e:
        duration = time.time() - start_time
        logger.error(f"EC2 health check failed after {duration:.3f}s: {str(e)}")
        
        return {
            "status": "unhealthy",
            "response_time_ms": round(duration * 1000, 2),
            "details": f"EC2 connectivity failed: {str(e)}",
            "error": str(e)
        }

def perform_comprehensive_health_check() -> Dict[str, Any]:
    """Perform comprehensive health check of all configured services"""
    start_time = time.time()
    
    # Execute all health checks in parallel using ThreadPoolExecutor
    # Note: Amplify and API Gateway checks removed - if they're down, requests wouldn't reach this endpoint
    with ThreadPoolExecutor(max_workers=5) as executor:
        # Submit all health check functions simultaneously
        futures = {
            'database': executor.submit(check_database_health),
            'aws_secrets_manager': executor.submit(check_aws_secrets_manager_health),
            'system_resources': executor.submit(check_system_resources),
            's3_storage': executor.submit(check_s3_health),
            'ec2_instances': executor.submit(check_ec2_health)
        }
        
        # Collect results from all futures
        health_results = {}
        for component_name, future in futures.items():
            try:
                health_results[component_name] = future.result()
            except Exception as e:
                logger.error(f"Health check failed for {component_name}: {str(e)}")
                # Provide fallback error structure
                health_results[component_name] = {
                    "status": "unhealthy",
                    "details": f"Health check failed: {str(e)}",
                    "error": str(e)
                }
    
    # Organize components by criticality using the threaded results
    critical_components = {
        "database": health_results['database'],
        "aws_secrets_manager": health_results['aws_secrets_manager'],
        "ec2_instances": health_results['ec2_instances']
    }
    
    non_critical_components = {
        "s3_storage": health_results['s3_storage'],
        "system_resources": health_results['system_resources']
    }
    
    # Calculate overall health status
    critical_statuses = [comp["status"] for comp in critical_components.values() if comp["status"] != "unknown"]
    non_critical_statuses = [comp["status"] for comp in non_critical_components.values() if comp["status"] != "unknown"]
    
    overall_status = "healthy"
    if any(status == "unhealthy" for status in critical_statuses):
        overall_status = "unhealthy"
    elif any(status in ["unhealthy", "degraded"] for status in non_critical_statuses) or any(status == "degraded" for status in critical_statuses):
        overall_status = "degraded"
    
    # Count service statuses for summary
    all_components = {**critical_components, **non_critical_components}
    total_services = len([comp for comp in all_components.values() if comp["status"] != "unknown"])
    healthy_count = len([comp for comp in all_components.values() if comp["status"] == "healthy"])
    degraded_count = len([comp for comp in all_components.values() if comp["status"] == "degraded"])
    unhealthy_count = len([comp for comp in all_components.values() if comp["status"] == "unhealthy"])
    
    total_duration = time.time() - start_time
    
    return {
        "status": overall_status,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "response_time_ms": round(total_duration * 1000, 2),
        "summary": {
            "total_services": total_services,
            "healthy": healthy_count,
            "degraded": degraded_count,
            "unhealthy": unhealthy_count
        },
        "components": all_components,
        "version": "2.0.0",
        "service": "surgicase-api"
    }

@router.get("/health")
@track_business_operation("check", "health")
def health_check():
    """
    Comprehensive health check endpoint with detailed component status and caching
    """
    # Check if we have valid cached results
    if is_cache_valid():
        logger.info("Returning cached health check results")
        return _health_cache["results"]
    
    # Perform fresh health check
    health_response = perform_comprehensive_health_check()
    
    # Cache the results
    _health_cache["last_check"] = datetime.utcnow()
    _health_cache["results"] = health_response
    
    # Log health check result
    if health_response["status"] == "healthy":
        logger.info(f"Health check passed in {health_response['response_time_ms']}ms")
    elif health_response["status"] == "degraded":
        logger.warning(f"Health check degraded in {health_response['response_time_ms']}ms")
    else:
        logger.error(f"Health check failed in {health_response['response_time_ms']}ms")
    
    # Return appropriate HTTP status
    if health_response["status"] == "unhealthy":
        raise HTTPException(status_code=503, detail=health_response)
    
    return health_response

@router.get("/health/system")
@track_business_operation("check", "health_system")
def system_health_check():
    """
    Simplified system health check endpoint - returns only overall status
    Perfect for user login checks and external monitoring
    """
    # Check if we have valid cached results
    if is_cache_valid():
        cached_result = _health_cache["results"]
        return {
            "status": cached_result["status"],
            "timestamp": cached_result["timestamp"],
            "response_time_ms": cached_result["response_time_ms"],
            "summary": cached_result["summary"],
            "version": cached_result["version"],
            "service": cached_result["service"]
        }
    
    # Perform fresh health check
    health_response = perform_comprehensive_health_check()
    
    # Cache the results
    _health_cache["last_check"] = datetime.utcnow()
    _health_cache["results"] = health_response
    
    # Return simplified response
    simplified_response = {
        "status": health_response["status"],
        "timestamp": health_response["timestamp"],
        "response_time_ms": health_response["response_time_ms"],
        "summary": health_response["summary"],
        "version": health_response["version"],
        "service": health_response["service"]
    }
    
    # Log health check result
    if health_response["status"] == "healthy":
        logger.info(f"System health check passed in {health_response['response_time_ms']}ms")
    elif health_response["status"] == "degraded":
        logger.warning(f"System health check degraded in {health_response['response_time_ms']}ms")
    else:
        logger.error(f"System health check failed in {health_response['response_time_ms']}ms")
    
    # Return appropriate HTTP status
    if health_response["status"] == "unhealthy":
        raise HTTPException(status_code=503, detail=simplified_response)
    
    return simplified_response

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
            health["components"]["aws_secrets_manager"]["status"],
            health["components"]["ec2_instances"]["status"]
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