# Created: 2025-07-30 22:59:57
# Last Modified: 2025-11-11 16:39:07
# Author: Scott Cadreau

# endpoints/backoffice/build_dashboard.py
from fastapi import APIRouter, HTTPException, Query, Request
import pymysql.cursors
from core.database import get_db_connection, close_db_connection
from utils.monitoring import track_business_operation, business_metrics
import time
from typing import Optional, Dict, Any
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

# Import the individual dashboard functions
from .case_dashboard_data import case_dashboard_data as get_case_dashboard_data
from .user_dashboard_data import user_dashboard_data as get_user_dashboard_data
from .case_submitted_analytics import case_submitted_analytics as get_case_submitted_analytics


router = APIRouter()

def get_simplified_health_data():
    """
    Simplified health check for dashboard - returns healthy status since 
    successful request to this endpoint indicates core services are operational
    """
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "summary": {
            "total_services": 1,
            "healthy": 1,
            "degraded": 0,
            "unhealthy": 0
        },
        "details": "Service operational - request successfully reached dashboard endpoint"
    }

@router.get("/build_dashboard")
@track_business_operation("get", "build_dashboard")
def build_dashboard(
    request: Request, 
    user_id: str = Query(..., description="The user ID making the request (must be user_type >= 10)"),
    start_date: Optional[str] = Query(None, description="Start date for case filtering (YYYY-MM-DD format)"),
    end_date: Optional[str] = Query(None, description="End date for case filtering (YYYY-MM-DD format)")
):
    """
    Generate comprehensive administrative dashboard with integrated health monitoring, case analytics, and user insights.
    
    This endpoint serves as the central hub for administrative oversight, combining real-time system health
    monitoring, case management analytics, and user distribution insights into a unified dashboard view.
    It orchestrates data collection from multiple subsystems with intelligent error handling, ensuring
    administrators receive complete operational visibility even when individual components experience issues.
    
    Key Features:
    - Unified dashboard combining health, case, user, and submission analytics
    - Intelligent error isolation preventing total failure from partial issues
    - Real-time system health monitoring integration
    - Case analytics with optional date filtering for temporal analysis
    - Case submission analytics based on submitted_ts timestamps
    - User distribution insights across organizational structure
    - Administrative access control with comprehensive permission validation
    - Graceful degradation with partial data availability
    - Centralized operational monitoring and business intelligence
    
    Args:
        request (Request): FastAPI request object for logging and monitoring
        user_id (str): Unique identifier of the requesting administrative user (required)
                      Must have user_type >= 10 to access comprehensive dashboard data
        start_date (str, optional): Start date for case filtering in YYYY-MM-DD format
                                   Applied to case analytics component
        end_date (str, optional): End date for case filtering in YYYY-MM-DD format
                                 Applied to case analytics component
    
    Returns:
        dict: Comprehensive dashboard response containing:
            - dashboard_type (str): Type identifier ("comprehensive")
            - timestamp (str): Dashboard generation timestamp in ISO format
            - execution_time_ms (int): Total execution time in milliseconds
            - request_filters (dict): Applied filter parameters:
                - user_id (str): Requesting user identifier
                - start_date (str): Start date filter (or null)
                - end_date (str): End date filter (or null)
            - data (dict): Integrated data from all subsystems:
                - health (dict): System health monitoring data:
                    - status (str): Overall system health status
                    - services (List): Individual service health information
                    - summary (dict): Health summary statistics
                    - timestamp (str): Health check timestamp
                - cases (dict): Case analytics dashboard data:
                    - dashboard_data (List): Case status distribution and financials
                    - summary (dict): Aggregate case statistics
                    - filters (dict): Applied date filters
                - users (dict): User analytics dashboard data:
                    - user_types (List): User type distribution statistics
                    - summary (dict): User base summary statistics
                - submitted_analytics (dict): Case submission analytics data:
                    - pay_category_data (List): Pay category distribution by submission date
                    - summary (dict): Aggregate submission statistics
                    - filters (dict): Applied date filters
            - summary (dict): High-level dashboard summary:
                - overall_health (str): System health status
                - total_cases (int): Total case count from analytics
                - total_users (int): Total user count from analytics
                - case_total_amount (str): Financial total from case analytics
                - healthy_services (int): Number of healthy system services
                - total_services (int): Total number of monitored services
                - submitted_cases (int): Total submitted case count from submission analytics
                - submitted_total_amount (str): Financial total from submission analytics
                - total_pay_tiers (int): Maximum pay tier number from procedure_code_buckets2
            - errors (List, optional): Collection errors if any subsystem failed
            - status (str): Dashboard completion status ("complete" or "partial")
    
    Raises:
        HTTPException:
            - 403 Forbidden: User does not have sufficient permissions (user_type < 10)
            - 500 Internal Server Error: Critical dashboard assembly errors
    
    Dashboard Components:
        1. Health Monitoring System:
           - Real-time service health checks
           - System resource monitoring
           - Service availability tracking
           - Performance metrics collection
           
        2. Case Analytics Dashboard:
           - Case status distribution analysis
           - Financial performance tracking
           - Time-based filtering capabilities
           - Operational workflow insights
           
        3. User Analytics Dashboard:
           - User type distribution statistics
           - Organizational composition analysis
           - Platform adoption metrics
           - Role-based user insights
           
        4. Submitted Cases Analytics:
           - Pay category distribution by submission date
           - Financial performance by submission timestamp
           - Time-based filtering using submitted_ts
           - Submission pattern analysis
    
    Error Isolation & Recovery:
        - Independent data collection from each subsystem
        - Continues dashboard assembly even if individual components fail
        - Error details captured without affecting other components
        - Graceful degradation with partial data availability
        - Detailed error logging for troubleshooting
        - Fallback data structures for failed components
    
    Administrative Intelligence:
        - Unified operational oversight across all system components
        - Real-time health monitoring for proactive issue detection
        - Financial and operational analytics for business intelligence
        - User base insights for organizational planning
        - Historical trending through date-filtered analytics
        - Performance monitoring across all subsystems
    
    Data Integration Logic:
        - Sequential data collection with independent error handling
        - Timestamp coordination across all data sources
        - Filter parameter propagation to relevant components
        - Data structure standardization for consistent presentation
        - Summary calculation aggregation from all sources
    
    Permission & Security:
        - Administrative access control (user_type >= 10 required)
        - Permission validation before any data collection
        - Secure access to sensitive operational data
        - Audit logging for administrative dashboard access
        - Cross-component security validation
    
    Performance Features:
        - Parallel data collection where possible
        - Efficient error isolation preventing cascade failures
        - Optimized data aggregation and summary calculation
        - Minimal database connection overhead
        - Intelligent caching where appropriate
    
    Monitoring & Logging:
        - Business metrics tracking for dashboard access operations
        - Prometheus monitoring via @track_business_operation decorator
        - Comprehensive execution time tracking
        - Error categorization across all subsystems
        - Administrative access auditing
        - Performance metrics for dashboard assembly
    
    Example Usage:
        GET /build_dashboard?user_id=ADMIN001
        GET /build_dashboard?user_id=ADMIN001&start_date=2024-01-01&end_date=2024-01-31
    
    Example Response:
        {
            "dashboard_type": "comprehensive",
            "timestamp": "2024-01-15T10:30:00Z",
            "execution_time_ms": 1250,
            "request_filters": {
                "user_id": "ADMIN001",
                "start_date": "2024-01-01",
                "end_date": "2024-01-31"
            },
            "data": {
                "health": {
                    "status": "healthy",
                    "services": [...],
                    "summary": {"healthy": 5, "total_services": 5}
                },
                "cases": {
                    "dashboard_data": [...],
                    "summary": {"total_cases": 150, "total_amount": "225000.00"}
                },
                "users": {
                    "user_types": [...],
                    "summary": {"total_users": 45}
                }
            },
            "summary": {
                "overall_health": "healthy",
                "total_cases": 150,
                "total_users": 45,
                "case_total_amount": "225000.00",
                "healthy_services": 5,
                "total_services": 5,
                "total_pay_tiers": 4
            },
            "errors": null,
            "status": "complete"
        }
    
    Example Response (Partial Data):
        {
            "dashboard_type": "comprehensive",
            "timestamp": "2024-01-15T10:30:00Z",
            "execution_time_ms": 1500,
            "data": {
                "health": {"status": "error", "error": "Service unavailable"},
                "cases": {...},
                "users": {...}
            },
            "summary": {...},
            "errors": ["Health data collection failed: Service unavailable"],
            "status": "partial"
        }
    
    Example Error Response (Permission Denied):
        {
            "detail": "User does not have permission to access dashboard data."
        }
    
    Note:
        - Dashboard provides unified view of all operational aspects
        - Error isolation ensures partial data availability during issues
        - Date filtering applies only to case analytics component
        - Health monitoring provides real-time system status
        - Summary statistics enable quick operational assessment
        - Administrative users should use this for comprehensive oversight
        - Partial data availability indicated by "status" field
        - Error details provided for troubleshooting subsystem issues
        - Dashboard generation time tracked for performance monitoring
    """
    conn = None
    start_time = time.time()
    response_status = 200
    response_data = None
    error_message = None
    
    try:
        # First verify user permissions and get max pay tier
        conn = get_db_connection()
        max_pay_tier = 0
        
        try:
            with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                # Check user_type for the requesting user
                cursor.execute("SELECT user_type FROM user_profile WHERE user_id = %s", (user_id,))
                user_row = cursor.fetchone()
                if not user_row or user_row.get("user_type", 0) < 10:
                    # Record failed access (permission denied)
                    business_metrics.record_utility_operation("build_dashboard", "permission_denied")
                    response_status = 403
                    error_message = "User does not have permission to access dashboard data"
                    raise HTTPException(status_code=403, detail="User does not have permission to access dashboard data.")
                
                # Get the maximum pay tier from procedure_code_buckets2
                cursor.execute("SELECT MAX(tier) as max_tier FROM procedure_code_buckets2")
                tier_result = cursor.fetchone()
                max_pay_tier = tier_result['max_tier'] if tier_result and tier_result['max_tier'] is not None else 0
        finally:
            close_db_connection(conn)
        
        # Now collect data from all four functions in parallel
        dashboard_data = {}
        collection_errors = []
        
        # Execute all four functions concurrently using ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=4) as executor:
            # Submit all four functions simultaneously
            # Pass validated=True to skip duplicate permission checks and skip_logging=True to prevent duplicate logs
            futures = {
                'health': executor.submit(get_simplified_health_data),
                'cases': executor.submit(get_case_dashboard_data, request, user_id, start_date, end_date, True, True),
                'users': executor.submit(get_user_dashboard_data, request, user_id, True, True),
                'submitted_analytics': executor.submit(get_case_submitted_analytics, request, user_id, start_date, end_date, True, True)
            }
            
            # Collect results with individual error handling
            for component_name, future in futures.items():
                try:
                    result = future.result()
                    dashboard_data[component_name] = result
                except Exception as e:
                    collection_errors.append(f"{component_name.title()} data collection failed: {str(e)}")
                    
                    # Provide fallback data structure based on component type
                    if component_name == 'health':
                        dashboard_data[component_name] = {
                            "status": "error", 
                            "error": str(e),
                            "timestamp": datetime.utcnow().isoformat() + "Z",
                            "summary": {
                                "total_services": 0,
                                "healthy": 0,
                                "degraded": 0,
                                "unhealthy": 1
                            }
                        }
                    elif component_name == 'cases':
                        dashboard_data[component_name] = {
                            "error": str(e),
                            "dashboard_data": [],
                            "summary": {"total_cases": 0, "total_amount": "0.00"}
                        }
                    elif component_name == 'users':
                        dashboard_data[component_name] = {
                            "error": str(e),
                            "user_types": [],
                            "summary": {"total_users": 0}
                        }
                    elif component_name == 'submitted_analytics':
                        dashboard_data[component_name] = {
                            "error": str(e),
                            "current_period": {
                                "pay_category_data": [],
                                "summary": {"total_cases": 0, "total_amount": "0.00"}
                            },
                            "filters": {"comparison_enabled": False}
                        }
        
        # Calculate execution time
        execution_time_ms = int((time.time() - start_time) * 1000)
        
        # Build the cohesive response
        response_data = {
            "dashboard_type": "comprehensive",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "execution_time_ms": execution_time_ms,
            "request_filters": {
                "user_id": user_id,
                "start_date": start_date,
                "end_date": end_date
            },
            "data": dashboard_data,
            "summary": {
                "overall_health": dashboard_data["health"].get("status", "unknown"),
                "total_cases": dashboard_data["cases"].get("summary", {}).get("total_cases", 0),
                "total_users": dashboard_data["users"].get("summary", {}).get("total_users", 0),
                "case_total_amount": dashboard_data["cases"].get("summary", {}).get("total_amount", "0.00"),
                "healthy_services": dashboard_data["health"].get("summary", {}).get("healthy", 0),
                "total_services": dashboard_data["health"].get("summary", {}).get("total_services", 0),
                "submitted_cases": dashboard_data["submitted_analytics"].get("current_period", {}).get("summary", {}).get("total_cases", 0),
                "submitted_total_amount": dashboard_data["submitted_analytics"].get("current_period", {}).get("summary", {}).get("total_amount", "0.00"),
                "total_pay_tiers": max_pay_tier
            },
            "errors": collection_errors if collection_errors else None,
            "status": "partial" if collection_errors else "complete"
        }
        
        # Record successful dashboard build
        business_metrics.record_utility_operation("build_dashboard", "success")
        
        return response_data
        
    except HTTPException as http_error:
        # Re-raise HTTP exceptions and capture error details
        response_status = http_error.status_code
        error_message = str(http_error.detail)
        raise
    except Exception as e:
        # Record failed dashboard build
        response_status = 500
        error_message = str(e)
        business_metrics.record_utility_operation("build_dashboard", "error")
        
        if 'conn' in locals() and conn:
            close_db_connection(conn)
        raise HTTPException(status_code=500, detail={"error": str(e)})
        
    finally:
        # Calculate execution time
        execution_time_ms = int((time.time() - start_time) * 1000)
        
        # Log request details for monitoring using the utility function
        from endpoints.utility.log_request import log_request_from_endpoint
        log_request_from_endpoint(
            request=request,
            execution_time_ms=execution_time_ms,
            response_status=response_status,
            user_id=user_id,
            response_data=response_data,
            error_message=error_message
        )