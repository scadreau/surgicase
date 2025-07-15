from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from core.database import get_db_connection
from datetime import datetime
import pymysql

router = APIRouter()

class LogRequestModel(BaseModel):
    timestamp: datetime = Field(default_factory=datetime.now)
    user_id: str | None = None
    endpoint: str
    method: str
    request_payload: str | None = None
    query_params: str | None = None
    response_status: int
    response_payload: str | None = None
    execution_time_ms: int
    error_message: str | None = None
    client_ip: str | None = None

@router.post("/log_request")
async def log_request(log: LogRequestModel):
    try:
        conn = get_db_connection()
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
        conn.close()
        return {"success": True}
    except Exception as e:
        if 'conn' in locals():
            conn.close()
        raise HTTPException(status_code=500, detail={"error": str(e)}) 