# Created: 2025-07-16 11:24:30
# Last Modified: 2025-07-20 23:56:01

from fastapi import APIRouter, Query, HTTPException
import requests
from utils.smart_capitalize import smart_capitalize
from utils.monitoring import track_business_operation, business_metrics

router = APIRouter()

@router.get("/check_npi")
@track_business_operation("validate", "npi")
def check_npi(npi: str = Query(..., regex="^\\d{10}$")):
    # Validate NPI
    if not npi.isdigit() or len(npi) != 10:
        # Record failed NPI validation (invalid format)
        business_metrics.record_utility_operation("npi_validation", "invalid_format")
        raise HTTPException(status_code=400, detail="NPI must be a 10-digit number.")

    url = f"https://npiregistry.cms.hhs.gov/api/?number={npi}&version=2.1"
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        # Record failed NPI validation (external API error)
        business_metrics.record_utility_operation("npi_validation", "external_api_error")
        raise HTTPException(status_code=502, detail=f"Failed to contact NPI registry: {str(e)}")

    if data.get("result_count", 0) < 1 or not data.get("results"):
        # Record failed NPI validation (not found)
        business_metrics.record_utility_operation("npi_validation", "not_found")
        raise HTTPException(status_code=404, detail="NPI not found.")

    result = data["results"][0]
    basic = result.get("basic", {})
    first_name = basic.get("first_name")
    last_name = basic.get("last_name")
    if not first_name or not last_name:
        # Record failed NPI validation (missing name fields)
        business_metrics.record_utility_operation("npi_validation", "missing_fields")
        raise HTTPException(status_code=422, detail="NPI record missing name fields.")

    corrected_first = smart_capitalize(first_name)
    corrected_last = smart_capitalize(last_name)

    # Record successful NPI validation
    business_metrics.record_utility_operation("npi_validation", "success")

    return {
        "npi": npi,
        "first_name": corrected_first,
        "last_name": corrected_last
    }

# Expose router for FastAPI app inclusion
__all__ = ["router"] 