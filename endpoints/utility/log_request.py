# Created: 2025-07-15 09:20:13
# Last Modified: 2025-08-06 15:44:12
# Author: Scott Cadreau

# endpoints/utility/log_request.py
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from core.database import get_db_connection, close_db_connection
from datetime import datetime
import pymysql.cursors
import json
from core.models import LogRequestModel
from utils.monitoring import track_business_operation, business_metrics

router = APIRouter()

def log_request_from_endpoint(request: Request, execution_time_ms: int, response_status: int, user_id: str = None, response_data: dict = None, error_message: str = None):
    """
    Comprehensive utility function for logging request details from any application endpoint.
    
    This function provides standardized request logging capabilities that can be called
    from any endpoint to ensure consistent audit trails, performance monitoring, and
    debugging information across the entire application. It extracts comprehensive
    request metadata and forwards it to the centralized logging system.
    
    Args:
        request (Request): FastAPI Request object containing:
            - URL path and method information
            - Headers including forwarded IP addresses
            - Request body/payload if available
            - Query parameters
        execution_time_ms (int): Total time taken to process the request in milliseconds.
                                Used for performance monitoring and optimization.
        response_status (int): HTTP response status code (200, 404, 500, etc.).
                              Used for success/failure tracking and error analysis.
        user_id (str, optional): User identifier associated with the request.
                                Used for user activity tracking and authorization auditing.
        response_data (dict, optional): Response payload data to be logged.
                                       Useful for debugging and request replay scenarios.
        error_message (str, optional): Error message if the request failed.
                                      Critical for error tracking and debugging.
    
    Data Extraction:
        - Client IP Address: Extracted from multiple sources with priority:
          1. request.client.host (direct connection)
          2. x-forwarded-for header (proxy/load balancer)
          3. x-real-ip header (alternative proxy header)
        - Request Payload: Decoded from request._body with UTF-8 encoding fallback
        - Query Parameters: Converted to dictionary format for structured logging
        - Timestamp: Automatically generated using current datetime
    
    Processing:
        - Constructs LogRequestModel with all extracted and provided data
        - Handles JSON serialization of complex objects with string fallback
        - Forwards to centralized log_request function for database storage
        - Implements defensive programming to prevent logging failures from affecting main operations
    
    Error Handling:
        - Never raises exceptions to prevent interference with main endpoint logic
        - Logs internal logging errors to application logger for monitoring
        - Gracefully handles missing or malformed request data
        - Provides fallback values for missing optional data
    
    Example Usage:
        from endpoints.utility.log_request import log_request_from_endpoint
        
        # In any endpoint's finally block:
        log_request_from_endpoint(
            request=request,
            execution_time_ms=execution_time_ms,
            response_status=response_status,
            user_id=user_id,
            response_data=response_data,
            error_message=error_message
        )
    
    Notes:
        - Designed to be non-blocking and fail-safe
        - Should be called in finally blocks to ensure logging even during exceptions
        - Automatically handles complex data serialization
        - Provides standardized logging format across all endpoints
        - Essential for compliance, debugging, and performance monitoring
    """
    try:
        # Get client IP from request
        client_ip = None
        if request.client:
            client_ip = request.client.host
        elif "x-forwarded-for" in request.headers:
            client_ip = request.headers["x-forwarded-for"].split(",")[0].strip()
        elif "x-real-ip" in request.headers:
            client_ip = request.headers["x-real-ip"]
        
        # Get request body if available
        request_payload = None
        if hasattr(request, '_body') and request._body:
            try:
                request_payload = request._body.decode('utf-8')
            except:
                request_payload = str(request._body)
        
        # Get query parameters
        query_params = dict(request.query_params) if request.query_params else None
        
        # Create log entry
        log_entry = LogRequestModel(
            timestamp=datetime.now(),
            user_id=user_id,
            endpoint=request.url.path,
            method=request.method,
            request_payload=request_payload,
            query_params=json.dumps(query_params, indent=2) if query_params else None,
            response_status=response_status,
            response_payload=json.dumps(response_data, default=str, indent=2) if response_data else None,
            execution_time_ms=execution_time_ms,
            error_message=error_message,
            client_ip=client_ip
        )
        
        # Use the existing log_request function
        log_request(log_entry)
        
    except Exception as e:
        # Don't fail the main operation if logging fails
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error logging request details: {e}")

@router.post("/log_request")
@track_business_operation("log", "request")
def log_request(log: LogRequestModel):
    """
    Centralized endpoint for storing comprehensive request log data in the database.
    
    This endpoint serves as the central logging mechanism for all application requests,
    providing a standardized way to store detailed request information for auditing,
    debugging, performance monitoring, and compliance purposes. It accepts structured
    log data and persists it to the request_logs table with full transaction support.
    
    Args:
        log (LogRequestModel): Comprehensive log data model containing:
            - timestamp (datetime): When the request was processed
            - user_id (str, optional): User identifier for the request
            - endpoint (str): The API endpoint path that was called
            - method (str): HTTP method (GET, POST, PUT, DELETE, etc.)
            - request_payload (str, optional): JSON string of request body data
            - query_params (str, optional): JSON string of URL query parameters
            - response_status (int): HTTP response status code
            - response_payload (str, optional): JSON string of response data
            - execution_time_ms (int): Processing time in milliseconds
            - error_message (str, optional): Error details if request failed
            - client_ip (str, optional): Client IP address for the request
    
    Returns:
        dict: Simple success confirmation:
            - success (bool): True if log entry was successfully created
    
    Raises:
        HTTPException:
            - 500 Internal Server Error: Database connection or insertion failures
    
    Database Operations:
        - Inserts comprehensive log record into 'request_logs' table
        - Maps all LogRequestModel fields to corresponding database columns
        - Uses transaction management with automatic commit on success
        - Proper connection lifecycle management with guaranteed cleanup
    
    Monitoring & Logging:
        - Business metrics tracking for logging operations:
          - "success": Log entry successfully created
          - "error": Database or processing errors
        - Prometheus monitoring via @track_business_operation decorator
        - Self-referential logging (logs its own operations)
    
    Data Storage:
        - Timestamp: Exact datetime when original request was processed
        - User Activity: Links requests to specific users for audit trails
        - Performance Data: Execution times for performance analysis
        - Request Context: Full request/response data for debugging
        - Network Information: Client IP for security and analytics
        - Error Information: Detailed error messages for troubleshooting
    
    Example Request:
        POST /log_request
        {
            "timestamp": "2024-01-15T10:30:45.123456",
            "user_id": "USER123",
            "endpoint": "/cases",
            "method": "POST",
            "request_payload": "{\\"case_id\\": \\"CASE-001\\"}",
            "query_params": "{\\"user_id\\": \\"USER123\\"}",
            "response_status": 201,
            "response_payload": "{\\"message\\": \\"Success\\"}",
            "execution_time_ms": 245,
            "error_message": null,
            "client_ip": "192.168.1.100"
        }
    
    Example Response:
        {
            "success": true
        }
    
    Usage Patterns:
        - Called automatically by log_request_from_endpoint utility function
        - Can be called directly for custom logging scenarios
        - Used by all endpoints through standardized logging wrapper
        - Essential for compliance and audit trail requirements
    
    Security Considerations:
        - No authentication required as this is an internal utility
        - Request/response data may contain sensitive information
        - IP address logging for security monitoring
        - Complete audit trail for compliance requirements
    
    Notes:
        - Designed for high-volume logging operations
        - Minimal response to reduce overhead
        - Automatic transaction management for data consistency
        - Essential component of the application's observability stack
    """
    try:
        conn = get_db_connection()
        
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO request_logs (
                        timestamp, user_id, endpoint, method, request_payload, query_params, response_status, response_payload, execution_time_ms, error_message, client_ip
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        log.timestamp,
                        log.user_id,
                        log.endpoint,
                        log.method,
                        log.request_payload,
                        log.query_params,
                        log.response_status,
                        log.response_payload,
                        log.execution_time_ms,
                        log.error_message,
                        log.client_ip
                    )
                )
                conn.commit()

                # Record successful request logging
                business_metrics.record_utility_operation("log_request", "success")
                
        finally:
            close_db_connection(conn)
            
        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        # Record failed request logging
        business_metrics.record_utility_operation("log_request", "error")
        
        if 'conn' in locals():
            close_db_connection(conn)
        raise HTTPException(status_code=500, detail={"error": str(e)}) 