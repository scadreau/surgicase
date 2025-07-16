# Created: 2025-07-16 11:24:30
# Last Modified: 2025-07-16 11:26:02

from fastapi import APIRouter, Query, HTTPException
import requests
from utils.smart_capitalize import smart_capitalize

router = APIRouter()

@router.get("/check_npi")
def check_npi(npi: str = Query(..., regex="^\\d{10}$")):
    # Validate NPI
    if not npi.isdigit() or len(npi) != 10:
        raise HTTPException(status_code=400, detail="NPI must be a 10-digit number.")

    url = f"https://npiregistry.cms.hhs.gov/api/?number={npi}&version=2.1"
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Failed to contact NPI registry: {str(e)}")

    if data.get("result_count", 0) < 1 or not data.get("results"):
        raise HTTPException(status_code=404, detail="NPI not found.")

    result = data["results"][0]
    basic = result.get("basic", {})
    first_name = basic.get("first_name")
    last_name = basic.get("last_name")
    if not first_name or not last_name:
        raise HTTPException(status_code=422, detail="NPI record missing name fields.")

    corrected_first = smart_capitalize(first_name)
    corrected_last = smart_capitalize(last_name)

    return {
        "npi": npi,
        "first_name": corrected_first,
        "last_name": corrected_last
    }

# Expose router for FastAPI app inclusion
__all__ = ["router"] 