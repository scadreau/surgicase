# Created: 2025-07-15 09:20:13
# Last Modified: 2025-07-15 11:17:36

# main_case_read.py
# Example: Deployment configuration for read-only case operations
# This can be scaled independently for high-read traffic

from fastapi import FastAPI

# Import only read case routers
from endpoints.case.get_case import router as get_case_router
from endpoints.case.filter_cases import router as filter_cases_router
from endpoints.health import router as health_router

# Create FastAPI instance
app = FastAPI(title="Case Read Service", version="1.0.0")

# Include only read routers
app.include_router(get_case_router, tags=["cases"])
app.include_router(filter_cases_router, tags=["cases"])
app.include_router(health_router, tags=["health"])

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)