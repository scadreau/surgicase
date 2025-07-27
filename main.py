# Created: 2025-07-15 09:20:13
# Last Modified: 2025-07-27 01:03:07

# main.py
from fastapi import FastAPI, Request
from prometheus_fastapi_instrumentator import Instrumentator

# Import all routers
from endpoints.case.get_case import router as get_case_router
from endpoints.case.create_case import router as create_case_router
from endpoints.case.update_case import router as update_case_router
from endpoints.case.delete_case import router as delete_case_router
from endpoints.case.filter_cases import router as filter_cases_router
from endpoints.case.bulk_update_case_status import router as bulk_update_case_status_router

from endpoints.user.get_user import router as get_user_router
from endpoints.user.create_user import router as create_user_router
from endpoints.user.update_user import router as update_user_router
from endpoints.user.delete_user import router as delete_user_router

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

from endpoints.health import router as health_router
from endpoints.metrics import router as metrics_router

from endpoints.backoffice.get_cases_by_status import router as get_cases_by_status_router
from endpoints.backoffice.get_users import router as get_users_router

from endpoints.reports.provider_payment_report import router as provider_payment_report_router
from endpoints.exports.quickbooks_export import router as quickbooks_export_router

# Import monitoring utilities
from utils.monitoring import monitor_request, system_monitor, db_monitor, logger

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
app.include_router(bulk_update_case_status_router, tags=["cases"])

# User endpoints
app.include_router(get_user_router, tags=["users"])
app.include_router(create_user_router, tags=["users"])
app.include_router(update_user_router, tags=["users"])
app.include_router(delete_user_router, tags=["users"])

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

# Health check
app.include_router(health_router, tags=["health"])

# Metrics endpoints
app.include_router(metrics_router, tags=["monitoring"])

# Backoffice endpoints
app.include_router(get_cases_by_status_router, tags=["backoffice"])
app.include_router(get_users_router, tags=["backoffice"])

# Report endpoints
app.include_router(provider_payment_report_router, tags=["reports"])

# Export endpoints
app.include_router(quickbooks_export_router, tags=["exports"])

if __name__ == "__main__":
    import uvicorn
    import os
    
    # Optional: Start the scheduler service in background
    # Handles: Case status updates (Mon/Thu), NPI data updates (Tue)
    # Set ENABLE_SCHEDULER=true environment variable to enable
    if os.getenv("ENABLE_SCHEDULER", "false").lower() == "true":
        from utils.scheduler import run_scheduler_in_background
        run_scheduler_in_background()
    
    uvicorn.run(app, host="0.0.0.0", port=8000)