# Created: 2025-07-16 11:24:30
# Last Modified: 2025-07-23 12:19:05

from fastapi import APIRouter, Query, HTTPException, Request
import requests
from utils.smart_capitalize import smart_capitalize
from utils.monitoring import track_business_operation, business_metrics
import time

router = APIRouter()

@router.get("/check_npi")
@track_business_operation("validate", "npi")
def check_npi(request: Request, npi: str = Query(..., regex="^\\d{10}$")):
    start_time = time.time()
    response_status = 200
    response_data = None
    error_message = None
    
    try:
        # Validate NPI
        if not npi.isdigit() or len(npi) != 10:
            # Record failed NPI validation (invalid format)
            business_metrics.record_utility_operation("npi_validation", "invalid_format")
            response_status = 400
            error_message = "NPI must be a 10-digit number"
            raise HTTPException(status_code=400, detail="NPI must be a 10-digit number.")

        url = f"https://npiregistry.cms.hhs.gov/api/?number={npi}&version=2.1"
        try:
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            # Record failed NPI validation (external API error)
            business_metrics.record_utility_operation("npi_validation", "external_api_error")
            response_status = 502
            error_message = f"Failed to contact NPI registry: {str(e)}"
            raise HTTPException(status_code=502, detail=f"Failed to contact NPI registry: {str(e)}")

        if data.get("result_count", 0) < 1 or not data.get("results"):
            # Record failed NPI validation (not found)
            business_metrics.record_utility_operation("npi_validation", "not_found")
            response_status = 404
            error_message = "NPI not found"
            raise HTTPException(status_code=404, detail="NPI not found.")

        result = data["results"][0]
        basic = result.get("basic", {})
        first_name = basic.get("first_name")
        last_name = basic.get("last_name")
        if not first_name or not last_name:
            # Record failed NPI validation (missing name fields)
            business_metrics.record_utility_operation("npi_validation", "missing_fields")
            response_status = 422
            error_message = "NPI record missing name fields"
            raise HTTPException(status_code=422, detail="NPI record missing name fields.")

        corrected_first = smart_capitalize(first_name)
        corrected_last = smart_capitalize(last_name)

        # Record successful NPI validation
        business_metrics.record_utility_operation("npi_validation", "success")

        response_data = {
            "npi": npi,
            "first_name": corrected_first,
            "last_name": corrected_last
        }
        return response_data
        
    except HTTPException as http_error:
        # Re-raise HTTP exceptions and capture error details
        response_status = http_error.status_code
        error_message = str(http_error.detail)
        raise
    except Exception as e:
        # Record failed NPI validation (unexpected error)
        response_status = 500
        error_message = str(e)
        business_metrics.record_utility_operation("npi_validation", "error")
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
            user_id=None,  # No user_id available in NPI validation
            response_data=response_data,
            error_message=error_message
        )

# Expose router for FastAPI app inclusion
__all__ = ["router"] 