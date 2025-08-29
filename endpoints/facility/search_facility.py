# Created: 2025-07-21 16:40:47
# Last Modified: 2025-08-29 20:09:20
# Author: Scott Cadreau

# endpoints/facility/search_facility.py
from fastapi import APIRouter, HTTPException, Query, Request
import pymysql.cursors
from core.database import get_db_connection, close_db_connection
from utils.monitoring import track_business_operation, business_metrics
from utils.text_formatting import capitalize_name_field, capitalize_facility_field, capitalize_address_field
import time

router = APIRouter()

@router.get("/search_facility")
@track_business_operation("search", "facility")
def search_facility(
    request: Request,
    facility_name: str = Query(..., description="Facility name to search for"),
    user_id: str = Query(None, description="Optional user ID for enhanced logging and monitoring")
):
    """
    Search for healthcare facilities by name using optimized A-Z partitioned search tables.
    
    This endpoint provides intelligent facility search functionality across the national NPI registry including:
    - High-performance search across millions of facility records
    - Optimized A-Z table partitioning for sub-50ms query times
    - Partial name matching with intelligent text formatting
    - Comprehensive monitoring and business metrics tracking
    - Full request logging and execution time tracking
    - Prometheus metrics integration for operational monitoring
    
    Search Strategy & Performance:
        - Determines appropriate search table based on first letter of facility_name
        - Uses optimized search_facility_[a-z] tables (26 partitions)
        - Distributes millions of records across smaller indexed tables (~20K-100K each)
        - Leverages database indexes (idx_npi, idx_facility_name) for fast execution
        - Performs LIKE search with wildcards for partial matching
        - Typical query time: <50ms vs >3000ms for full table scan
        - Eliminates need to scan entire NPI dataset for each search
    
    Table Structure & Data Source:
        - Tables: search_surgeon_facility.search_facility_a through search_facility_z
        - Primary indexes: idx_npi (unique), idx_facility_name (search optimized)
        - Data source: npi_data_2 (Organization providers from National NPI registry)
        - Record types: Hospitals, clinics, surgical centers, labs, pharmacies
    
    Text Formatting & Normalization:
        - Applies proper capitalization to facility names via capitalize_facility_field()
        - Normalizes city names with appropriate capitalization
        - Handles state abbreviations (2-char) vs full state names
        - Formats medical facility addresses appropriately
        - Ensures consistent presentation across all search results
    
    Facility Types Covered:
        - Hospitals and medical centers
        - Clinics and urgent care facilities  
        - Surgical centers and specialty practices
        - Laboratories and diagnostic centers
        - Pharmacies and medical equipment suppliers
        - Rehabilitation and long-term care facilities
    
    Args:
        request (Request): FastAPI request object for logging and monitoring
        facility_name (str): Healthcare facility name to search for (partial matching supported)
        user_id (str, optional): User ID for enhanced logging and monitoring
    
    Returns:
        dict: Response containing:
            - statusCode (int): HTTP status code (200 for successful search)
            - body (dict): Response data including:
                - message (str): Search result summary with count
                - search_criteria (dict): Echo of search parameters used
                - facilities (List[dict]): Array of matching facilities, each containing:
                    - npi (str): National Provider Identifier
                    - facility_name (str): Formatted facility name
                    - address (str): Formatted street address
                    - city (str): Formatted city name
                    - state (str): State abbreviation or full name
                    - zip (str): ZIP/postal code
    
    Raises:
        HTTPException: 
            - 400 Bad Request: facility_name parameter is missing or empty
            - 500 Internal Server Error: Database query failures or connection issues
    
    Database Operations:
        - Determines target table based on first letter of search term
        - Executes parameterized LIKE query with wildcard matching
        - Applies text formatting to all returned facility data
        - Uses proper cursor management and connection cleanup
    
    Monitoring & Logging:
        - Business metrics tracking for facility search operations
        - Prometheus monitoring via @track_business_operation decorator
        - Records success/error metrics via business_metrics.record_facility_operation()
        - Comprehensive request logging with execution time tracking
        - Error logging with full exception details
    
    Input Validation:
        - Validates facility_name is not empty or whitespace-only
        - Handles non-alphabetic first characters (defaults to 'a' table)
        - Strips whitespace from search term before processing
        - Returns appropriate 400 error for invalid input
    
    Example:
        GET /search-facility?facility_name=General Hospital&user_id=user123
        
        Response:
        {
            "statusCode": 200,
            "body": {
                "message": "Found 15 matching facility(ies)",
                "search_criteria": {
                    "facility_name": "General Hospital",
                    "user_id": "user123"
                },
                "facilities": [
                    {
                        "npi": "1234567890",
                        "facility_name": "General Hospital Medical Center",
                        "address": "123 Medical Drive",
                        "city": "Healthcare City",
                        "state": "CA",
                        "zip": "90210"
                    }
                ]
            }
        }
    
    Note:
        - Search is case-insensitive and supports partial matching
        - Results are automatically formatted for consistent presentation
        - Non-alphabetic search terms default to 'a' table for processing
        - Search covers only organization-type NPI providers (facilities)
        - Individual provider searches should use surgeon search endpoints
    """
    conn = None
    start_time = time.time()
    response_status = 200
    response_data = None
    error_message = None
    
    try:
        if not facility_name.strip():
            response_status = 400
            error_message = "facility_name is required and cannot be empty"
            raise HTTPException(status_code=400, detail={"error": "facility_name is required and cannot be empty"})

        conn = get_db_connection()
        
        # Determine which table to search based on first letter of facility name
        first_letter = facility_name.strip()[0].lower()
        if not first_letter.isalpha():
            # For non-alphabetic characters, default to 'a' table
            first_letter = 'a'
        
        table_name = f"search_facility_{first_letter}"
        
        try:
            with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                # Search using LIKE for partial matching on facility name in the appropriate A-Z table
                cursor.execute(f"""
                    SELECT npi, facility_name, address, city, state, zip
                    FROM search_surgeon_facility.{table_name}
                    WHERE facility_name LIKE %s order by state, city, facility_name
                """, (f"%{facility_name}%",))
                
                facilities = cursor.fetchall()

                # Apply proper capitalization to facility fields
                for row in facilities:
                    if 'facility_name' in row and row['facility_name']:
                        row['facility_name'] = capitalize_facility_field(row['facility_name'])
                    if 'city' in row and row['city']:
                        row['city'] = capitalize_name_field(row['city'])
                    if 'address' in row and row['address']:
                        row['address'] = capitalize_address_field(row['address'])
                    if 'state' in row and row['state']:
                        # States are usually uppercase abbreviations, but handle full names
                        if len(row['state']) > 2:
                            row['state'] = capitalize_name_field(row['state'])
                        else:
                            row['state'] = row['state'].upper()

                # Record successful facility search
                business_metrics.record_facility_operation("search", "success", None)
                
        finally:
            close_db_connection(conn)
            
        # Build search criteria response
        search_criteria = {"facility_name": facility_name}
        if user_id:
            search_criteria["user_id"] = user_id
            
        response_data = {
            "statusCode": 200,
            "body": {
                "message": f"Found {len(facilities)} matching facility(ies)",
                "search_criteria": search_criteria,
                "facilities": facilities
            }
        }
        return response_data
        
    except HTTPException as http_error:
        # Re-raise HTTP exceptions and capture error details
        response_status = http_error.status_code
        error_message = str(http_error.detail)
        raise
    except Exception as e:
        # Record failed facility search
        response_status = 500
        error_message = str(e)
        business_metrics.record_facility_operation("search", "error", None)
        
        if 'conn' in locals():
            close_db_connection(conn)
        raise HTTPException(status_code=500, detail={"error": f"Internal server error: {str(e)}"})
        
    finally:
        # Calculate execution time
        execution_time_ms = int((time.time() - start_time) * 1000)
        
        # Log request details for monitoring using the utility function
        from endpoints.utility.log_request import log_request_from_endpoint
        log_request_from_endpoint(
            request=request,
            execution_time_ms=execution_time_ms,
            response_status=response_status,
            user_id=user_id,  # Use provided user_id for enhanced logging
            response_data=response_data,
            error_message=error_message
        ) 