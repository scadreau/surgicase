# Created: 2025-07-15 09:20:13
# Last Modified: 2025-07-29 02:20:15
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
    Utility function to log request details from any endpoint
    
    Args:
        request: FastAPI Request object
        execution_time_ms: Time taken to process the request in milliseconds
        response_status: HTTP response status code
        user_id: Optional user ID associated with the request
        response_data: Optional response payload to log
        error_message: Optional error message if request failed
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