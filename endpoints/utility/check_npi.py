# Created: 2025-07-16 11:24:30
# Last Modified: 2025-08-29 19:29:54
# Author: Scott Cadreau

# endpoints/utility/check_npi.py
from fastapi import APIRouter, Query, HTTPException, Request
import requests
from utils.text_formatting import capitalize_name_field
from utils.monitoring import track_business_operation, business_metrics
import time

router = APIRouter()

@router.get("/check_npi")
@track_business_operation("validate", "npi")
def check_npi(request: Request, npi: str = Query(..., regex="^\\d{10}$"), facility: bool = Query(False)):
    """
    Validate and retrieve provider or facility information from a National Provider Identifier (NPI).
    
    This endpoint validates a 10-digit NPI number by querying the official CMS National
    Provider Identifier (NPI) Registry API. It supports both individual providers (Type 1)
    and organizational facilities (Type 2). It performs comprehensive validation including
    format checking, external API verification, and data extraction with automatic name
    formatting standardization.
    
    Args:
        request (Request): FastAPI request object for logging and monitoring
        npi (str): 10-digit National Provider Identifier number to validate.
                  Must be exactly 10 digits, validated by regex pattern "^\\d{10}$"
        facility (bool): Optional query parameter to specify lookup type.
                        False (default): Look up individual provider (Type 1)
                        True: Look up organizational facility (Type 2)
    
    Returns:
        dict: Response containing validated provider/facility information:
            - npi (str): The validated 10-digit NPI number
            - first_name (str): For individuals: Provider's first name with proper capitalization
                               For facilities: Organization name with proper capitalization
            - last_name (str): For individuals: Provider's last name with proper capitalization
                              For facilities: Empty string
    
    Raises:
        HTTPException:
            - 400 Bad Request: Invalid NPI format (not 10 digits)
            - 404 Not Found: NPI not found in the CMS registry
            - 422 Unprocessable Entity: NPI record missing required fields
                                       (name fields for individuals, organization name for facilities)
            - 502 Bad Gateway: Failed to contact external NPI registry API
            - 500 Internal Server Error: Unexpected processing errors
    
    External Dependencies:
        - CMS NPI Registry API (https://npiregistry.cms.hhs.gov/api/)
        - 10-second timeout on external API calls
        - API version 2.1 for comprehensive provider data
    
    Data Processing:
        - Automatic name capitalization using capitalize_name_field utility
        - Validation of required fields based on lookup type:
          - Individual providers: first_name, last_name
          - Facilities: organization_name
        - JSON response parsing with error handling for malformed data
    
    Monitoring & Logging:
        - Business metrics tracking with detailed operation categorization:
          - "success": Valid NPI with complete provider/facility information
          - "invalid_format": Improper NPI format provided
          - "not_found": NPI not found in registry
          - "missing_fields": NPI found but missing required data (names or organization name)
          - "external_api_error": CMS API communication failure
          - "error": Unexpected system errors
        - Prometheus monitoring via @track_business_operation decorator
        - Comprehensive request logging with execution time tracking
        - Error logging with full exception details and status codes
    
    Example Usage:
        Individual Provider: GET /check_npi?npi=1234567890
        Facility: GET /check_npi?npi=1234567890&facility=true
    
    Example Responses:
        Individual Provider:
        {
            "npi": "1234567890",
            "first_name": "John",
            "last_name": "Smith"
        }
        
        Facility:
        {
            "npi": "1234567890",
            "first_name": "General Hospital",
            "last_name": ""
        }
    
    Security Considerations:
        - Input validation prevents SQL injection through regex pattern
        - External API timeout prevents indefinite hanging
        - No sensitive data stored or logged from external responses
        - Rate limiting handled by external CMS API
    
    Notes:
        - No authentication required for this utility endpoint
        - Names are automatically formatted for consistent presentation
        - Supports both individual providers (Type 1) and organizational facilities (Type 2)
        - Use facility=true parameter to lookup organizational facilities
        - For facilities, organization name is returned in the first_name field
    """
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
        
        if facility:
            # For facilities (Type 2), look for organization name
            organization_name = basic.get("organization_name")
            if not organization_name:
                # Record failed NPI validation (missing organization name)
                business_metrics.record_utility_operation("npi_validation", "missing_fields")
                response_status = 422
                error_message = "NPI record missing organization name"
                raise HTTPException(status_code=422, detail="NPI record missing organization name.")
            
            corrected_org_name = capitalize_name_field(organization_name)
            
            # Record successful NPI validation
            business_metrics.record_utility_operation("npi_validation", "success")
            
            response_data = {
                "npi": npi,
                "first_name": corrected_org_name,  # Using first_name field for organization name
                "last_name": ""  # Empty last_name for facilities
            }
        else:
            # For individual providers (Type 1), look for first and last name
            first_name = basic.get("first_name")
            last_name = basic.get("last_name")
            if not first_name or not last_name:
                # Record failed NPI validation (missing name fields)
                business_metrics.record_utility_operation("npi_validation", "missing_fields")
                response_status = 422
                error_message = "NPI record missing name fields"
                raise HTTPException(status_code=422, detail="NPI record missing name fields.")

            corrected_first = capitalize_name_field(first_name)
            corrected_last = capitalize_name_field(last_name)

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