# Created: 2025-07-21 15:08:09
# Last Modified: 2025-09-05 16:40:42
# Author: Scott Cadreau

# endpoints/surgeon/search_surgeon.py
from fastapi import APIRouter, HTTPException, Query, Request
import pymysql.cursors
from core.database import get_db_connection, close_db_connection
from utils.monitoring import track_business_operation, business_metrics
from utils.text_formatting import capitalize_name_field, capitalize_address_field
import time

router = APIRouter()

@router.get("/search_surgeon")
@track_business_operation("search", "surgeon")
def search_surgeon(
    request: Request,
    first_name: str = Query(..., description="First name to search for, or a valid 10-digit NPI number"),
    last_name: str = Query(None, description="Last name to search for (not required for NPI search)"),
    user_id: str = Query(None, description="Optional user ID for enhanced logging and monitoring")
):
    """
    Search for surgeons by name or NPI using optimized search tables.
    
    This endpoint provides intelligent surgeon search functionality across the national NPI registry including:
    - High-performance search across millions of individual provider records
    - Dual search modes: surgeon name (A-Z partitioned) or direct NPI lookup
    - Optimized A-Z table partitioning for sub-100ms query times on name searches
    - Direct NPI lookup using search_surgeon_all table for exact matches
    - Dual-field name matching with intelligent text formatting
    - Comprehensive monitoring and business metrics tracking
    - Full request logging and execution time tracking
    - Prometheus metrics integration for operational monitoring
    
    Search Strategy & Performance:
        Name Search:
        - Determines appropriate search table based on first letter of last_name
        - Uses optimized search_surgeon_[a-z] tables (26 partitions)
        - Distributes millions of records across smaller indexed tables (~50K-200K each)
        - Leverages composite indexes (idx_last_first, idx_last_name, idx_first_name)
        - Performs dual LIKE searches on both first_name and last_name with wildcards
        - Typical query time: <100ms vs >5000ms for full table scan
        - Eliminates need to scan entire NPI dataset for each search
        
        NPI Search:
        - Detects 10-digit numeric input in first_name field as NPI number
        - Uses search_surgeon_all table for direct NPI lookup
        - Exact match search for fastest possible retrieval
        - Eliminates need to scan multiple A-Z tables for NPI searches
        - last_name parameter not required for NPI searches
    
    Table Structure & Data Source:
        Name Search Tables: search_surgeon_facility.search_surgeon_a through search_surgeon_z
        - Primary indexes: idx_npi (unique), idx_last_name, idx_first_name, idx_last_first (composite)
        - Data source: npi_data_1 (Individual providers from National NPI registry)
        - Record types: Physicians, surgeons, specialists, and other individual healthcare providers
        
        NPI Search Table: search_surgeon_facility.search_surgeon_all
        - Contains all surgeon records for direct NPI lookup
        - Optimized for exact NPI matching
    
    Text Formatting & Normalization:
        - Applies proper capitalization to names via capitalize_name_field()
        - Normalizes city names with appropriate capitalization
        - Handles state abbreviations (2-char) vs full state names
        - Formats medical provider addresses appropriately
        - Ensures consistent presentation across all search results
        - Converts search terms to uppercase for database matching
    
    Provider Types Covered:
        - Surgeons and surgical specialists
        - Physicians and medical doctors
        - Specialists (cardiologists, orthopedic surgeons, etc.)
        - Residents and fellows in training
        - Other individual healthcare providers with NPI numbers
    
    Args:
        request (Request): FastAPI request object for logging and monitoring
        first_name (str): Surgeon's first name to search for (partial matching supported)
                         OR a valid 10-digit NPI number for exact surgeon lookup
        last_name (str): Surgeon's last name to search for (partial matching supported)
                        Note: Not required when searching by NPI
        user_id (str, optional): User ID for enhanced logging and monitoring
    
    Returns:
        dict: Response containing:
            - statusCode (int): HTTP status code (200 for successful search)
            - body (dict): Response data including:
                - message (str): Search result summary with count
                - search_criteria (dict): Echo of search parameters used
                - surgeons (List[dict]): Array of matching surgeons, each containing:
                    - npi (str): National Provider Identifier
                    - first_name (str): Formatted first name
                    - last_name (str): Formatted last name
                    - address (str): Formatted street address
                    - city (str): Formatted city name
                    - state (str): State abbreviation or full name
                    - zip (str): ZIP/postal code
    
    Raises:
        HTTPException: 
            - 400 Bad Request: first_name or last_name parameters are missing or empty
            - 500 Internal Server Error: Database query failures or connection issues
    
    Database Operations:
        - Determines target table based on first letter of last_name
        - Executes parameterized dual LIKE query with wildcard matching
        - Converts search terms to uppercase for consistent matching
        - Applies text formatting to all returned surgeon data
        - Uses proper cursor management and connection cleanup
    
    Monitoring & Logging:
        - Business metrics tracking for surgeon search operations
        - Prometheus monitoring via @track_business_operation decorator
        - Records success/error metrics via business_metrics.record_surgeon_operation()
        - Comprehensive request logging with execution time tracking
        - Error logging with full exception details
    
    Input Validation:
        - For name search: Validates both first_name and last_name are not empty or whitespace-only
        - For NPI search: Validates first_name is a valid 10-digit number, last_name not required
        - Handles non-alphabetic first characters in last_name (defaults to 'a' table)
        - Strips whitespace from search terms before processing
        - Returns appropriate 400 error for invalid input
    
    Examples:
        Name Search:
        GET /search-surgeon?first_name=John&last_name=Smith&user_id=user123
        
        NPI Search:
        GET /search-surgeon?first_name=1234567890&user_id=user123
        
        Response:
        {
            "statusCode": 200,
            "body": {
                "message": "Found 12 matching surgeon(s)",
                "search_criteria": {
                    "first_name": "John",
                    "last_name": "Smith",
                    "user_id": "user123"
                },
                "surgeons": [
                    {
                        "npi": "1234567890",
                        "first_name": "John",
                        "last_name": "Smith",
                        "address": "123 Medical Plaza",
                        "city": "Surgery City",
                        "state": "CA",
                        "zip": "90210"
                    }
                ]
            }
        }
    
    Note:
        - Name search is case-insensitive and supports partial matching on both names
        - NPI search performs exact match on 10-digit numbers
        - Results are automatically formatted for consistent presentation
        - Non-alphabetic last_name characters default to 'a' table for processing
        - Search covers only individual provider NPI records (not organizations)
        - Facility searches should use facility search endpoints
        - For name search: both first_name and last_name are required parameters
        - For NPI search: only first_name (containing NPI) is required
    """
    conn = None
    start_time = time.time()
    response_status = 200
    response_data = None
    error_message = None
    
    try:
        # Check if the first_name is a valid 10-digit NPI number
        search_term = first_name.strip()
        is_npi_search = search_term.isdigit() and len(search_term) == 10
        
        if is_npi_search:
            # For NPI search, last_name is not required
            if not first_name.strip():
                response_status = 400
                error_message = "first_name is required and cannot be empty"
                raise HTTPException(status_code=400, detail={"error": "first_name is required and cannot be empty"})
        else:
            # For name search, both first_name and last_name are required
            if not first_name.strip() or not last_name or not last_name.strip():
                response_status = 400
                error_message = "Both first_name and last_name are required and cannot be empty for name search"
                raise HTTPException(status_code=400, detail={"error": "Both first_name and last_name are required and cannot be empty for name search"})

        conn = get_db_connection()
        
        try:
            with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                if is_npi_search:
                    # Search by NPI in the search_surgeon_all table
                    cursor.execute("""
                        SELECT npi, first_name, last_name, address, city, state, zip
                        FROM search_surgeon_facility.search_surgeon_all
                        WHERE npi = %s
                    """, (search_term,))
                else:
                    # Regular name search using A-Z partitioned tables
                    first_name_upper = first_name.upper()
                    last_name_upper = last_name.upper()

                    # Determine which table to search based on first letter of last name
                    first_letter = last_name.strip()[0].lower()
                    if not first_letter.isalpha():
                        # For non-alphabetic characters, default to 'a' table
                        first_letter = 'a'
                    
                    table_name = f"search_surgeon_{first_letter}"

                    # Search using LIKE for partial matching on both names in the appropriate A-Z table
                    cursor.execute(f"""
                        SELECT npi, first_name, last_name, address, city, state, zip
                        FROM search_surgeon_facility.{table_name}
                        WHERE last_name like %s AND first_name like %s order by state, city, last_name, first_name
                    """, (f"%{last_name_upper}%", f"%{first_name_upper}%"))
                
                surgeons = cursor.fetchall()

                for row in surgeons:
                    if 'first_name' in row and row['first_name']:
                        # Properly capitalize first name
                        row['first_name'] = capitalize_name_field(row['first_name'])
                    if 'last_name' in row and row['last_name']:
                        # Properly capitalize last name
                        row['last_name'] = capitalize_name_field(row['last_name'])
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

                # Record successful surgeon search
                business_metrics.record_surgeon_operation("search", "success", None)
                
        finally:
            close_db_connection(conn)
            
        # Build search criteria response
        search_criteria = {"first_name": first_name}
        if last_name:
            search_criteria["last_name"] = last_name
        if user_id:
            search_criteria["user_id"] = user_id
            
        response_data = {
            "statusCode": 200,
            "body": {
                "message": f"Found {len(surgeons)} matching surgeon(s)",
                "search_criteria": search_criteria,
                "surgeons": surgeons
            }
        }
        return response_data
        
    except HTTPException as http_error:
        # Re-raise HTTP exceptions and capture error details
        response_status = http_error.status_code
        error_message = str(http_error.detail)
        raise
    except Exception as e:
        # Record failed surgeon search
        response_status = 500
        error_message = str(e)
        business_metrics.record_surgeon_operation("search", "error", None)
        
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