# Created: 2025-07-15 09:20:13
# Last Modified: 2025-07-15 11:17:09

# endpoints/health.py
from fastapi import APIRouter

router = APIRouter()

@router.get("/health")
async def health_check():
    """
    Health check endpoint
    """
    return {"status": "healthy"}