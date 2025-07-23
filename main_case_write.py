# Created: 2025-07-15 09:20:13
# Last Modified: 2025-07-23 11:59:10

# main_case_write.py
# Example: Deployment configuration for write case operations
# This can be scaled with different resource allocations

from fastapi import FastAPI

# Import only write case routers
from endpoints.case.create_case import router as create_case_router
from endpoints.case.update_case import router as update_case_router
from endpoints.case.delete_case import router as delete_case_router
from endpoints.health import router as health_router

# Create FastAPI instance
app = FastAPI(title="Case Write Service", version="1.0.0")

# Include only write routers
app.include_router(create_case_router, tags=["cases"])
app.include_router(update_case_router, tags=["cases"])
app.include_router(delete_case_router, tags=["cases"])
app.include_router(health_router, tags=["health"])

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)