# Created: 2025-07-21 16:40:47
# Last Modified: 2025-08-29 23:09:55
# Author: Scott Cadreau

# endpoints/facility/search_facility.py
from fastapi import APIRouter, HTTPException, Query, Request
import pymysql.cursors
from core.database import get_db_connection, close_db_connection
from utils.monitoring import track_business_operation, business_metrics
from utils.text_formatting import capitalize_name_field, capitalize_facility_field, capitalize_address_field
from utils.secrets_manager import get_secret
import time
import json

router = APIRouter()

@router.get("/search_facility")
@track_business_operation("search", "facility")
def search_facility(
    request: Request,
    facility_name: str = Query(..., description="Facility name to search for, or a valid 10-digit NPI number"),
    user_id: str = Query(None, description="Optional user ID for enhanced logging and monitoring")
):
    """
    Search for healthcare facilities by name or NPI number using optimized search tables.
    
    This endpoint provides intelligent facility search functionality across the national NPI registry including:
    - High-performance search across millions of facility records
    - Dual search modes: facility name (A-Z partitioned) or direct NPI lookup
    - Optimized A-Z table partitioning for sub-50ms query times on name searches
    - Direct NPI lookup using search_facility_all table for exact matches
    - Partial name matching with intelligent text formatting
    - Comprehensive monitoring and business metrics tracking
    - Full request logging and execution time tracking
    - Prometheus metrics integration for operational monitoring
    
    Search Strategy & Performance:
        Name Search:
        - Determines appropriate search table based on first letter of facility_name
        - Uses optimized search_facility_[a-z] tables (26 partitions)
        - Distributes millions of records across smaller indexed tables (~20K-100K each)
        - Leverages database indexes (idx_npi, idx_facility_name) for fast execution
        - Performs LIKE search with wildcards for partial matching
        - Typical query time: <50ms vs >3000ms for full table scan
        
        NPI Search:
        - Detects 10-digit numeric input as NPI number
        - Uses search_facility_all table for direct NPI lookup
        - Exact match search for fastest possible retrieval
        - Eliminates need to scan multiple A-Z tables for NPI searches
    
    Table Structure & Data Source:
        Name Search Tables: search_surgeon_facility.search_facility_a through search_facility_z
        - Primary indexes: idx_npi (unique), idx_facility_name (search optimized)
        - Data source: npi_data_2 (Organization providers from National NPI registry)
        - Record types: Hospitals, clinics, surgical centers, labs, pharmacies
        
        NPI Search Table: search_surgeon_facility.search_facility_all
        - Contains all facility records for direct NPI lookup
        - Optimized for exact NPI matching
    
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
                            OR a valid 10-digit NPI number for exact facility lookup
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
    
    Examples:
        Name Search:
        GET /search-facility?facility_name=General Hospital&user_id=user123
        
        NPI Search:
        GET /search-facility?facility_name=1234567890&user_id=user123
        
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
        - Name search is case-insensitive and supports partial matching
        - NPI search performs exact match on 10-digit numbers
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
        
        # Check if the search string is a valid 10-digit NPI number
        search_term = facility_name.strip()
        is_npi_search = search_term.isdigit() and len(search_term) == 10
        
        try:
            with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                if is_npi_search:
                    # Search by NPI in the search_facility_all table
                    cursor.execute("""
                        SELECT npi, facility_name, address, city, state, zip
                        FROM search_surgeon_facility.search_facility_all
                        WHERE npi = %s
                    """, (search_term,))
                else:
                    # Determine which table to search based on first letter of facility name
                    first_letter = search_term[0].lower()
                    if not first_letter.isalpha():
                        # For non-alphabetic characters, default to 'a' table
                        first_letter = 'a'
                    
                    table_name = f"search_facility_{first_letter}"
                    
                    # Search using LIKE for partial matching on facility name in the appropriate A-Z table
                    cursor.execute(f"""
                        SELECT npi, facility_name, address, city, state, zip
                        FROM search_surgeon_facility.{table_name}
                        WHERE facility_name LIKE %s order by state, city, facility_name
                    """, (f"%{search_term}%",))
                
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


@router.get("/search_facility_ai")
@track_business_operation("ai_search", "facility")
def search_facility_ai(
    request: Request,
    facility_name: str = Query(..., description="Facility name to search for using AI enhancement"),
    city: str = Query(..., description="City where facility is located"),
    state: str = Query(..., description="State where facility is located (2-letter abbreviation preferred)"),
    user_id: str = Query(None, description="Optional user ID for enhanced logging and monitoring")
):
    """
    AI-powered facility search that uses OpenAI GPT-4 to resolve facility names to official NPI records.
    
    This endpoint addresses the common problem where facility names on buildings differ from their
    official NPI registry names due to mergers, acquisitions, marketing names, or historical naming.
    The AI helps bridge this gap by understanding the relationship between colloquial facility names
    and their official organizational identities.
    
    Workflow:
        1. User provides facility name as they know it (e.g., "St. Mary's")
        2. AI API call resolves to official name and NPI (e.g., "St. Mary's Medical Center", NPI: 1234567890)
        3. Direct NPI lookup in optimized database using existing infrastructure
        4. Return precise facility match with full details
    
    Use Cases:
        - Facility names that don't match NPI registry exactly
        - Merged/acquired facilities with multiple names
        - Marketing names vs. legal entity names
        - Historical facility names still in common use
        - Regional variations of national chains
    
    Args:
        request (Request): FastAPI request object for logging and monitoring
        facility_name (str): Facility name as known by user (partial or colloquial names accepted)
        city (str): City where facility is located (helps AI disambiguation)
        state (str): State where facility is located (2-letter abbreviation preferred)
        user_id (str, optional): User ID for enhanced logging and monitoring
    
    Returns:
        dict: Response containing:
            - statusCode (int): HTTP status code (200 for successful resolution)
            - body (dict): Response data including:
                - message (str): AI resolution result summary
                - search_criteria (dict): Echo of search parameters used
                - ai_resolution (dict): AI processing details including:
                    - suggested_name (str): Official facility name suggested by AI
                    - suggested_npi (str): NPI number identified by AI
                    - confidence (str): AI confidence level (high/medium/low)
                    - ai_response_time_ms (int): Time taken for AI API call
                - facilities (List[dict]): Array with exact facility match (if found):
                    - npi (str): National Provider Identifier
                    - facility_name (str): Official formatted facility name
                    - address (str): Formatted street address
                    - city (str): Formatted city name
                    - state (str): State abbreviation
                    - zip (str): ZIP/postal code
    
    Raises:
        HTTPException:
            - 400 Bad Request: Missing required parameters or invalid input
            - 500 Internal Server Error: AI API failures, database issues, or processing errors
            - 503 Service Unavailable: OpenAI API temporarily unavailable
    
    AI Integration:
        - Uses OpenAI GPT-4 for intelligent facility name resolution
        - Structured JSON response parsing for reliable data extraction
        - Comprehensive error handling for AI API failures
        - Response time tracking for performance monitoring
    
    Database Operations:
        - Leverages existing optimized NPI lookup infrastructure
        - Uses search_facility_all table for direct NPI matching
        - Applies same text formatting as standard facility search
        - Maintains consistent response structure with regular search
    
    Monitoring & Logging:
        - Business metrics tracking for AI facility search operations
        - Prometheus monitoring via @track_business_operation decorator
        - AI response time and success rate tracking
        - Comprehensive request logging with execution time
        - Error categorization (AI vs. database vs. parsing errors)
    
    Examples:
        Request:
        GET /search_facility_ai?facility_name=St. Mary's&city=Dallas&state=TX&user_id=user123
        
        Response (Success):
        {
            "statusCode": 200,
            "body": {
                "message": "AI successfully resolved facility to exact match",
                "search_criteria": {
                    "facility_name": "St. Mary's",
                    "city": "Dallas",
                    "state": "TX",
                    "user_id": "user123"
                },
                "ai_resolution": {
                    "suggested_name": "St. Mary's Medical Center of Dallas",
                    "suggested_npi": "1234567890",
                    "confidence": "high",
                    "ai_response_time_ms": 1250
                },
                "facilities": [
                    {
                        "npi": "1234567890",
                        "facility_name": "St. Mary's Medical Center Of Dallas",
                        "address": "3434 Live Oak St",
                        "city": "Dallas",
                        "state": "TX",
                        "zip": "75204"
                    }
                ]
            }
        }
    
    Note:
        - Requires OpenAI API key configured in AWS Secrets Manager (surgicase/main -> OPENAI_API_KEY)
        - AI responses are parsed for structured data extraction
        - Falls back gracefully if AI cannot resolve facility name
        - Maintains same security and monitoring standards as regular facility search
        - Designed for occasional use when standard search is insufficient
    """
    conn = None
    start_time = time.time()
    ai_start_time = None
    ai_response_time_ms = 0
    response_status = 200
    response_data = None
    error_message = None
    
    try:
        # Validate required parameters
        if not facility_name.strip():
            response_status = 400
            error_message = "facility_name is required and cannot be empty"
            raise HTTPException(status_code=400, detail={"error": "facility_name is required and cannot be empty"})
        
        if not city.strip():
            response_status = 400
            error_message = "city is required and cannot be empty"
            raise HTTPException(status_code=400, detail={"error": "city is required and cannot be empty"})
            
        if not state.strip():
            response_status = 400
            error_message = "state is required and cannot be empty"
            raise HTTPException(status_code=400, detail={"error": "state is required and cannot be empty"})

        # Get OpenAI API key from AWS Secrets Manager
        try:
            main_config = get_secret("surgicase/main")
            openai_api_key = main_config.get("OPENAI_API_KEY")
            if not openai_api_key:
                response_status = 500
                error_message = "OpenAI API key not configured in secrets"
                raise HTTPException(status_code=500, detail={"error": "AI service not properly configured"})
        except Exception as e:
            response_status = 500
            error_message = f"Failed to retrieve OpenAI API key: {str(e)}"
            raise HTTPException(status_code=500, detail={"error": "AI service configuration error"})


        
        # Prepare AI prompt with structured JSON response requirement
        ai_prompt = f"""You are a healthcare facility database expert with access to National Provider Identifier (NPI) registry information. I need you to find the official organization name and NPI number for a medical facility.

Facility: {facility_name.strip()}
Location: {city.strip()}, {state.strip()}

INSTRUCTIONS:
1. Identify the exact legal organization name as it appears in the NPI registry
2. Find the actual 10-digit NPI number from the official registry
3. If you know this facility exists but cannot recall the exact NPI, use "UNKNOWN" 
4. NEVER fabricate, guess, or create fake NPI numbers like "1234567890" or "9876543210"
5. Consider common variations: "Hospital" vs "Medical Center", "Inc." vs "LLC", etc.

Examples of what I need:
- "Sunrise Mountain View" might be "Sunrise Mountainview Hospital, Inc." with NPI 1104870187
- "Banner Desert" might be "Banner Desert Medical Center" with a specific real NPI
- "Mayo Clinic" locations have different NPIs for different campuses

Respond ONLY with valid JSON in this exact format:
{{
    "npi": "1234567890",
    "official_name": "Exact Legal Organization Name",
    "address": "Street Address",
    "city": "City Name", 
    "state": "State",
    "zip": "ZIP Code",
    "confidence": "high"
}}

Confidence levels:
- "high": You are certain of both the name and NPI
- "medium": You know the facility but not certain of exact NPI (use "UNKNOWN" for NPI)
- "low": You are unsure about the facility identification (use "UNKNOWN" for NPI)

Return ONLY the JSON object, no additional text."""

        # Make AI API call with timing - try Anthropic Claude first, fallback to OpenAI
        ai_start_time = time.time()
        ai_content = None
        ai_provider = "unknown"
        
        try:
            # Try Anthropic Claude first (often better for factual healthcare data)
            anthropic_api_key = main_config.get("ANTHROPIC_API_KEY")
            if anthropic_api_key:
                try:
                    import anthropic
                    anthropic_client = anthropic.Anthropic(api_key=anthropic_api_key)
                    
                    claude_response = anthropic_client.messages.create(
                        model="claude-3-5-sonnet-20241022",  # Latest Claude model with most recent training
                        max_tokens=300,
                        temperature=0.1,
                        system="You are a healthcare facility database expert. Respond only with valid JSON as requested.",
                        messages=[{"role": "user", "content": ai_prompt}]
                    )
                    
                    ai_content = claude_response.content[0].text.strip()
                    ai_provider = "claude-3.5-sonnet"
                    
                except Exception as claude_error:
                    # Claude failed, will try OpenAI as fallback
                    pass
            
            # Fallback to OpenAI if Claude not available or failed
            if not ai_content:
                from openai import OpenAI
                openai_client = OpenAI(api_key=openai_api_key)
                
                ai_response = openai_client.chat.completions.create(
                    model="gpt-5-2025-08-07",  # Using specific GPT-5 version with August 2025 training cutoff
                    messages=[
                        {"role": "system", "content": "You are a healthcare facility database expert. Respond only with valid JSON as requested."},
                        {"role": "user", "content": ai_prompt}
                    ],
                    max_tokens=300,
                    temperature=0.1  # Low temperature for more consistent, factual responses
                )
                
                ai_content = ai_response.choices[0].message.content.strip()
                ai_provider = "gpt-5-2025-08-07"
            
            ai_response_time_ms = int((time.time() - ai_start_time) * 1000)
            
            # Clean up response (remove any markdown formatting if present)
            if ai_content.startswith("```json"):
                ai_content = ai_content.replace("```json", "").replace("```", "").strip()
            elif ai_content.startswith("```"):
                ai_content = ai_content.replace("```", "").strip()
                
            ai_data = json.loads(ai_content)
            
            # Validate AI response structure
            required_fields = ["npi", "official_name", "confidence"]
            for field in required_fields:
                if field not in ai_data:
                    raise ValueError(f"AI response missing required field: {field}")
            
            # Validate NPI format
            suggested_npi = str(ai_data["npi"]).strip()
            if suggested_npi.upper() == "UNKNOWN":
                # AI couldn't find a definitive NPI - return response without database lookup
                response_data = {
                    "statusCode": 200,
                    "body": {
                        "message": "AI found facility information but could not determine exact NPI",
                        "search_criteria": {
                            "facility_name": facility_name,
                            "city": city,
                            "state": state
                        },
                        "ai_resolution": {
                            "suggested_name": ai_data.get("official_name", ""),
                            "suggested_npi": "UNKNOWN",
                            "confidence": ai_data.get("confidence", "unknown"),
                            "ai_response_time_ms": ai_response_time_ms,
                            "ai_provider": ai_provider
                        },
                        "facilities": [],
                        "recommendation": f"Try searching for '{ai_data.get('official_name', facility_name)}' in the regular facility search"
                    }
                }
                if user_id:
                    response_data["body"]["search_criteria"]["user_id"] = user_id
                business_metrics.record_facility_operation("ai_search", "unknown_npi", None)
                return response_data
            elif not (suggested_npi.isdigit() and len(suggested_npi) == 10):
                raise ValueError(f"AI returned invalid NPI format: {suggested_npi}")
                
        except Exception as openai_error:
            # Handle OpenAI-specific errors
            error_str = str(openai_error).lower()
            if "rate limit" in error_str or "quota" in error_str:
                response_status = 503
                error_message = "OpenAI API rate limit exceeded"
                business_metrics.record_facility_operation("ai_search", "rate_limit", None)
                raise HTTPException(status_code=503, detail={"error": "AI service temporarily unavailable due to rate limits"})
            elif "api" in error_str or "connection" in error_str or "timeout" in error_str:
                response_status = 503
                error_message = f"OpenAI API error: {str(openai_error)}"
                business_metrics.record_facility_operation("ai_search", "api_error", None)
                raise HTTPException(status_code=503, detail={"error": "AI service temporarily unavailable"})
            else:
                # Re-raise for other processing (JSON parsing, validation, etc.)
                raise
        except json.JSONDecodeError as e:
            response_status = 500
            error_message = f"Failed to parse AI response as JSON: {str(e)}"
            business_metrics.record_facility_operation("ai_search", "parse_error", None)
            raise HTTPException(status_code=500, detail={"error": "AI service returned invalid response format"})
        except Exception as e:
            response_status = 500
            error_message = f"AI processing error: {str(e)}"
            business_metrics.record_facility_operation("ai_search", "error", None)
            raise HTTPException(status_code=500, detail={"error": f"AI service error: {str(e)}"})

        # Use the AI-suggested NPI to perform direct database lookup
        conn = get_db_connection()
        
        try:
            with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                # Direct NPI lookup using existing optimized infrastructure
                cursor.execute("""
                    SELECT npi, facility_name, address, city, state, zip
                    FROM search_surgeon_facility.search_facility_all
                    WHERE npi = %s
                """, (suggested_npi,))
                
                facility_result = cursor.fetchone()
                
                if facility_result:
                    # Apply proper capitalization to facility fields (same as regular search)
                    if 'facility_name' in facility_result and facility_result['facility_name']:
                        facility_result['facility_name'] = capitalize_facility_field(facility_result['facility_name'])
                    if 'city' in facility_result and facility_result['city']:
                        facility_result['city'] = capitalize_name_field(facility_result['city'])
                    if 'address' in facility_result and facility_result['address']:
                        facility_result['address'] = capitalize_address_field(facility_result['address'])
                    if 'state' in facility_result and facility_result['state']:
                        if len(facility_result['state']) > 2:
                            facility_result['state'] = capitalize_name_field(facility_result['state'])
                        else:
                            facility_result['state'] = facility_result['state'].upper()
                    
                    facilities = [facility_result]
                    message = "AI successfully resolved facility to exact match"
                    business_metrics.record_facility_operation("ai_search", "success", None)
                else:
                    # NPI not found - try fallback search using AI-suggested facility name
                    suggested_name = ai_data.get("official_name", "").strip()
                    if suggested_name:
                        # Try searching by the AI-suggested name in the appropriate A-Z table
                        first_letter = suggested_name[0].lower()
                        if not first_letter.isalpha():
                            first_letter = 'a'
                        
                        table_name = f"search_facility_{first_letter}"
                        
                        cursor.execute(f"""
                            SELECT npi, facility_name, address, city, state, zip
                            FROM search_surgeon_facility.{table_name}
                            WHERE facility_name LIKE %s AND city LIKE %s AND state LIKE %s
                            ORDER BY 
                                CASE WHEN facility_name LIKE %s THEN 1 ELSE 2 END,
                                facility_name
                            LIMIT 5
                        """, (f"%{suggested_name}%", f"%{city.strip()}%", f"%{state.strip()}%", f"{suggested_name}%"))
                        
                        fallback_results = cursor.fetchall()
                        
                        if fallback_results:
                            # Apply formatting to fallback results
                            for row in fallback_results:
                                if 'facility_name' in row and row['facility_name']:
                                    row['facility_name'] = capitalize_facility_field(row['facility_name'])
                                if 'city' in row and row['city']:
                                    row['city'] = capitalize_name_field(row['city'])
                                if 'address' in row and row['address']:
                                    row['address'] = capitalize_address_field(row['address'])
                                if 'state' in row and row['state']:
                                    if len(row['state']) > 2:
                                        row['state'] = capitalize_name_field(row['state'])
                                    else:
                                        row['state'] = row['state'].upper()
                            
                            facilities = fallback_results
                            message = f"AI suggested NPI {suggested_npi} not found, but found {len(fallback_results)} facility(ies) matching AI-suggested name"
                            business_metrics.record_facility_operation("ai_search", "fallback_success", None)
                        else:
                            facilities = []
                            message = f"AI suggested NPI {suggested_npi} not found in database, and no facilities found matching suggested name"
                            business_metrics.record_facility_operation("ai_search", "npi_not_found", None)
                    else:
                        facilities = []
                        message = f"AI suggested NPI {suggested_npi} not found in database"
                        business_metrics.record_facility_operation("ai_search", "npi_not_found", None)
                    
        finally:
            close_db_connection(conn)
            
        # Build comprehensive response with AI resolution details
        search_criteria = {
            "facility_name": facility_name,
            "city": city,
            "state": state
        }
        if user_id:
            search_criteria["user_id"] = user_id
            
        ai_resolution = {
            "suggested_name": ai_data.get("official_name", ""),
            "suggested_npi": suggested_npi,
            "confidence": ai_data.get("confidence", "unknown"),
            "ai_response_time_ms": ai_response_time_ms,
            "ai_provider": ai_provider
        }
        
        response_data = {
            "statusCode": 200,
            "body": {
                "message": message,
                "search_criteria": search_criteria,
                "ai_resolution": ai_resolution,
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
        # Record failed AI facility search
        response_status = 500
        error_message = str(e)
        business_metrics.record_facility_operation("ai_search", "error", None)
        
        if 'conn' in locals() and conn:
            close_db_connection(conn)
        raise HTTPException(status_code=500, detail={"error": f"Internal server error: {str(e)}"})
        
    finally:
        # Calculate total execution time
        execution_time_ms = int((time.time() - start_time) * 1000)
        
        # Log request details for monitoring using the utility function
        from endpoints.utility.log_request import log_request_from_endpoint
        log_request_from_endpoint(
            request=request,
            execution_time_ms=execution_time_ms,
            response_status=response_status,
            user_id=user_id,
            response_data=response_data,
            error_message=error_message
        )