# Created: 2025-07-15 09:20:13
# Last Modified: 2025-08-27 00:36:35
# Author: Scott Cadreau

# main.py
from fastapi import FastAPI, Request
from prometheus_fastapi_instrumentator import Instrumentator

# Import all routers
from endpoints.case.get_case import router as get_case_router
from endpoints.case.create_case import router as create_case_router
from endpoints.case.update_case import router as update_case_router
from endpoints.case.delete_case import router as delete_case_router
from endpoints.case.filter_cases import router as filter_cases_router
from endpoints.case.group_cases import router as group_cases_router

from endpoints.user.get_user import router as get_user_router
from endpoints.user.create_user import router as create_user_router
from endpoints.user.update_user import router as update_user_router
from endpoints.user.delete_user import router as delete_user_router
from endpoints.user.change_password import router as change_password_router

from endpoints.facility.create_facility import router as create_facility_router
from endpoints.facility.delete_facility import router as delete_facility_router
from endpoints.facility.get_facilities import router as get_facilities_router
from endpoints.facility.search_facility import router as search_facility_router

from endpoints.surgeon.create_surgeon import router as create_surgeon_router
from endpoints.surgeon.delete_surgeon import router as delete_surgeon_router
from endpoints.surgeon.get_surgeons import router as get_surgeons_router
from endpoints.surgeon.search_surgeon import router as search_surgeon_router

from endpoints.utility.get_doctypes import router as get_doctypes_router
from endpoints.utility.get_cpt_codes import router as get_cpt_codes_router
from endpoints.utility.log_request import router as log_request_router
from endpoints.utility.check_npi import router as check_npi_router
from endpoints.utility.get_user_environment import router as get_user_environment_router
from endpoints.utility.get_timezones import router as get_timezones_router
from endpoints.utility.get_lists import router as get_lists_router
from endpoints.utility.add_to_lists import router as add_to_lists_router
from endpoints.utility.bugs import router as bugs_router

from endpoints.health import router as health_router
from endpoints.metrics import router as metrics_router

from endpoints.backoffice.get_cases_by_status import router as get_cases_by_status_router

# Import scheduler functionality
import os
import logging
from endpoints.backoffice.get_users import router as get_users_router
from endpoints.backoffice.case_dashboard_data import router as case_dashboard_data_router
from endpoints.backoffice.user_dashboard_data import router as user_dashboard_data_router
from endpoints.backoffice.bulk_update_case_status import router as bulk_update_case_status_router
from endpoints.backoffice.get_case_images import router as get_case_images_router
from endpoints.backoffice.build_dashboard import router as build_dashboard_router

from endpoints.reports import provider_payment_report_router, provider_payment_summary_report_router, referral_report_router

from endpoints.exports.quickbooks_export import router as quickbooks_export_router
from endpoints.exports.case_export import router as case_export_router

# Import monitoring utilities
from utils.monitoring import monitor_request, system_monitor, db_monitor, logger

def get_main_config() -> dict:
    """
    Fetch main configuration from AWS Secrets Manager using centralized secrets manager
    """
    try:
        from utils.secrets_manager import get_secret
        return get_secret("surgicase/main")
    except Exception as e:
        logging.error(f"Error fetching main configuration from Secrets Manager: {str(e)}")
        # Return default configuration if secrets are unavailable
        return {"ENABLE_SCHEDULER": "true"}

# Create FastAPI instance
app = FastAPI(
    title="SurgiCase API",
    description="API for surgical case management",
    version="0.8.0"
)

# Add request monitoring middleware
@app.middleware("http")
def monitoring_middleware(request: Request, call_next):
    return monitor_request(request, call_next)

# Prometheus monitoring setup
Instrumentator().instrument(app).expose(app)

# Include all routers
# Case endpoints
app.include_router(get_case_router, tags=["cases"])
app.include_router(create_case_router, tags=["cases"])
app.include_router(update_case_router, tags=["cases"])
app.include_router(delete_case_router, tags=["cases"])
app.include_router(filter_cases_router, tags=["cases"])
app.include_router(group_cases_router, tags=["cases"])

# User endpoints
app.include_router(get_user_router, tags=["users"])
app.include_router(create_user_router, tags=["users"])
app.include_router(update_user_router, tags=["users"])
app.include_router(delete_user_router, tags=["users"])
app.include_router(change_password_router, tags=["users"])

# Facility endpoints
app.include_router(create_facility_router, tags=["facilities"])
app.include_router(delete_facility_router, tags=["facilities"])
app.include_router(get_facilities_router, tags=["facilities"])
app.include_router(search_facility_router, tags=["facilities"])

# Surgeon endpoints
app.include_router(create_surgeon_router, tags=["surgeons"])
app.include_router(delete_surgeon_router, tags=["surgeons"])
app.include_router(get_surgeons_router, tags=["surgeons"])
app.include_router(search_surgeon_router, tags=["surgeons"])

# Utility endpoints
app.include_router(get_doctypes_router, tags=["utility"])
app.include_router(get_cpt_codes_router, tags=["utility"])
app.include_router(log_request_router)
app.include_router(check_npi_router, tags=["utility"])
app.include_router(get_user_environment_router, tags=["utility"])
app.include_router(get_timezones_router, tags=["utility"])
app.include_router(get_lists_router, tags=["utility"])
app.include_router(add_to_lists_router, tags=["utility"])
app.include_router(bugs_router, tags=["utility"])

# Health check
app.include_router(health_router, tags=["health"])

# Metrics endpoints
app.include_router(metrics_router, tags=["monitoring"])

# Secrets cache monitoring
from endpoints.monitoring.secrets_cache_stats import router as secrets_cache_stats_router
app.include_router(secrets_cache_stats_router, tags=["monitoring"])

# Backoffice endpoints
app.include_router(get_cases_by_status_router, tags=["backoffice"])
app.include_router(get_users_router, tags=["backoffice"])
app.include_router(case_dashboard_data_router, tags=["backoffice"])
app.include_router(user_dashboard_data_router, tags=["backoffice"])
app.include_router(bulk_update_case_status_router, tags=["backoffice"])
app.include_router(get_case_images_router, tags=["backoffice"])
app.include_router(build_dashboard_router, tags=["backoffice"])

# Report endpoints
app.include_router(provider_payment_report_router, tags=["reports"])
app.include_router(provider_payment_summary_report_router, tags=["reports"])
app.include_router(referral_report_router, tags=["reports"])

# Export endpoints
app.include_router(quickbooks_export_router, tags=["exports"])
app.include_router(case_export_router, tags=["exports"])

# Warm secrets cache on startup for optimal performance
# Pre-loads all application secrets to eliminate cold start latency
try:
    from utils.secrets_manager import warm_all_secrets
    warming_results = warm_all_secrets()
    logger.info(f"Secrets cache warming completed: {warming_results['successful']}/{warming_results['total_secrets']} secrets loaded")
except Exception as e:
    logger.error(f"Failed to warm secrets cache: {str(e)}")
    logger.warning("Application will continue with on-demand secret loading")

# Warm user environment cache on startup for optimal performance (non-blocking)
# Starts background thread to pre-load all active users' environment data
# Server becomes available immediately while cache warming happens in background
try:
    from endpoints.utility.get_user_environment import start_background_cache_warming
    warming_thread = start_background_cache_warming()
    logger.info("🔥 User environment cache warming started in background thread (non-blocking)")
except Exception as e:
    logger.error(f"Failed to start user environment cache warming: {str(e)}")
    logger.warning("Application will continue with on-demand user environment loading")

# Warm database connection pool on startup for optimal performance
# Pre-creates database connections to eliminate first-request latency
try:
    from core.database import prewarm_connection_pool
    pool_results = prewarm_connection_pool(target_connections=50)
    if pool_results["status"] == "success":
        logger.info(f"🔥 Database pool warming completed: {pool_results['created']} connections created, {pool_results['current_size']}/{pool_results['target_size']} ready")
    elif pool_results["status"] == "already_warm":
        logger.info(f"✅ Database pool already warm: {pool_results['current_size']}/{pool_results['target_size']} connections ready")
    else:
        logger.warning(f"⚠️ Database pool warming status: {pool_results['status']}")
except Exception as e:
    logger.error(f"Failed to warm database connection pool: {str(e)}")
    logger.warning("Application will continue with on-demand connection creation")

# Warm cases cache on startup for optimal performance
# Pre-loads common admin queries to eliminate cold start latency
try:
    from endpoints.backoffice.get_cases_by_status import warm_cases_cache
    cache_results = warm_cases_cache()
    if cache_results["failed"] == 0:
        total_cases = sum(detail.get("case_count", 0) for detail in cache_results["details"] if detail["status"] == "success")
        logger.info(f"🔥 Cases cache warming completed: {cache_results['successful']} queries warmed ({total_cases} total cases) in {cache_results['duration_seconds']:.2f}s")
    else:
        logger.warning(f"⚠️ Cases cache warming partial: {cache_results['successful']}/{cache_results['total_queries']} queries warmed in {cache_results['duration_seconds']:.2f}s")
except Exception as e:
    logger.error(f"Failed to warm cases cache: {str(e)}")
    logger.warning("Application will continue with on-demand cache population")

# Start the scheduler service in background
# Handles: Case status updates (Mon/Thu), NPI data updates (Tue), Pool/Cache maintenance
# Configuration stored in AWS Secrets Manager: surgicase/main
try:
    main_config = get_main_config()
    enable_scheduler = main_config.get("ENABLE_SCHEDULER", "true").lower() == "true"
    scheduler_role = main_config.get("SCHEDULER_ROLE", "leader").lower()  # "leader" or "worker"
    
    if enable_scheduler:
        from utils.scheduler import run_scheduler_in_background
        run_scheduler_in_background(scheduler_role=scheduler_role)
        logger.info(f"Scheduler enabled in {scheduler_role.upper()} mode via AWS Secrets Manager configuration")
    else:
        logger.info("Scheduler disabled via AWS Secrets Manager configuration")
except Exception as e:
    logger.error(f"Failed to initialize scheduler: {str(e)}")
    # Fallback: enable scheduler in leader mode if configuration cannot be retrieved
    from utils.scheduler import run_scheduler_in_background
    run_scheduler_in_background(scheduler_role="leader")
    logger.warning("Scheduler enabled in LEADER mode as fallback due to configuration error")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)