# Created: 2025-07-15 09:20:13
# Last Modified: 2025-07-15 20:45:27

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from core.database import get_db_connection, close_db_connection
from datetime import datetime
import pymysql
from core.models import LogRequestModel
from utils.monitoring import track_business_operation, business_metrics

router = APIRouter()

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