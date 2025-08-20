# Created: 2025-07-15 09:20:13
# Last Modified: 2025-08-20 08:38:53
# Author: Scott Cadreau

# core/database.py
import pymysql
import pymysql.cursors
import os
import time
import threading
from typing import Optional, Dict, Any
from queue import Queue, Empty

# Import monitoring utilities
try:
    from utils.monitoring import db_monitor, logger, track_database_operation
except ImportError:
    # Fallback if monitoring is not available
    db_monitor = None
    logger = None
    track_database_operation = lambda operation, table="unknown": lambda func: func

# Global connection pool
_connection_pool: Optional[Queue] = None
_pool_config: Dict[str, Any] = {}
_pool_lock = threading.Lock()

def get_db_credentials(secret_name: str) -> Dict[str, Any]:
    """
    Function to fetch database credentials from AWS Secrets Manager using centralized secrets manager
    """
    from utils.secrets_manager import get_secret
    return get_secret(secret_name, cache_ttl=14400)  # 4 hours cache (DB secret rotates weekly)

def _create_connection() -> pymysql.Connection:
    """Create a new database connection"""
    # Hardcoded values (optimization: eliminates one secrets call)
    rds_host = "dev1-metoray-aurora-a98fdy.cluster-cahckueig7sf.us-east-1.rds.amazonaws.com"
    db_name = "allstars"
    
    # Fetch credentials from Secrets Manager (cached)
    secretdb = get_db_credentials("arn:aws:secretsmanager:us-east-1:002118831669:secret:rds!cluster-9376049b-abee-46d9-9cdb-95b95d6cdda0-fjhTNH")
    db_user = secretdb["username"]
    db_pass = secretdb["password"]
    
    # Create connection with autocommit=False for transaction control
    connection = pymysql.connect(
        host=rds_host, 
        user=db_user, 
        password=db_pass, 
        database=db_name,
        autocommit=False,  # Explicitly disable autocommit
        charset='utf8mb4',
        cursorclass=pymysql.cursors.DictCursor
    )
    return connection

def _initialize_pool():
    """Initialize the connection pool"""
    global _connection_pool, _pool_config
    
    with _pool_lock:
        if _connection_pool is not None:
            return
            
        # Pool configuration - optimized for rapid requests
        pool_size = int(os.environ.get("DB_POOL_SIZE", "15"))
        _pool_config = {
            "pool_size": pool_size,
            "max_overflow": int(os.environ.get("DB_POOL_MAX_OVERFLOW", "10")),
            "pool_timeout": int(os.environ.get("DB_POOL_TIMEOUT", "10"))  # Faster timeout for rapid requests
        }
        
        _connection_pool = Queue(maxsize=pool_size + _pool_config["max_overflow"])
        
        # Pre-populate with initial connections
        for _ in range(min(pool_size, 3)):  # Start with 3 connections
            try:
                conn = _create_connection()
                _connection_pool.put(conn, block=False)
            except Exception as e:
                if logger:
                    logger.warning(f"Failed to pre-populate connection pool: {e}")
                break

def get_db_connection():
    """
    Helper function to establish database connection with connection pooling
    """
    global _connection_pool
    start_time = time.time()
    
    try:
        # Initialize pool if needed
        if _connection_pool is None:
            _initialize_pool()
        
        # Try to get connection from pool
        connection = None
        try:
            connection = _connection_pool.get(timeout=_pool_config["pool_timeout"])
            
            # Validate connection
            if is_connection_valid(connection):
                # Track successful connection from pool
                if db_monitor:
                    db_monitor.connection_created()
                    duration = time.time() - start_time
                    if logger:
                        logger.debug("database_connection_from_pool", duration=duration)
                return connection
            else:
                # Connection is stale, create new one
                if logger:
                    logger.debug("database_connection_invalid_replacing")
                connection.close() if connection else None
                connection = None
                
        except Empty:
            # Pool is empty, create new connection if under max limit
            if logger:
                logger.debug("database_connection_pool_empty_creating_new")
        
        # Create new connection if pool empty or connection invalid
        connection = _create_connection()
        
        # Track connection creation
        if db_monitor:
            db_monitor.connection_created()
            duration = time.time() - start_time
            if logger:
                logger.debug("database_connection_established", duration=duration)
        
        return connection
        
    except Exception as e:
        duration = time.time() - start_time
        
        # Track connection errors
        if db_monitor:
            db_monitor.connection_created()  # This will increment the error counter
            if logger:
                logger.error("database_connection_failed", duration=duration, error=str(e))
        
        raise

def is_connection_valid(connection: Optional[pymysql.Connection]) -> bool:
    """
    Check if a database connection is valid and open
    """
    if not connection:
        return False
    
    try:
        # Try to ping the connection
        connection.ping(reconnect=False)
        return connection.open
    except Exception:
        return False

def close_db_connection(connection: Optional[pymysql.Connection]):
    """
    Helper function to return connection to pool or close it
    """
    global _connection_pool
    
    if not connection:
        return
        
    try:
        # If connection is valid and pool isn't full, return to pool
        if (is_connection_valid(connection) and 
            _connection_pool is not None and 
            not _connection_pool.full()):
            
            # Reset connection state for reuse
            if not connection.get_autocommit():
                try:
                    connection.rollback()  # Reset any uncommitted transaction
                except Exception:
                    pass  # Ignore rollback errors
            
            _connection_pool.put(connection, block=False)
            
            # Track connection returned to pool
            if db_monitor:
                db_monitor.connection_closed()
                if logger:
                    logger.debug("database_connection_returned_to_pool")
            return
            
    except Exception as e:
        if logger:
            logger.warning(f"Failed to return connection to pool: {e}")
    
    # If we can't return to pool, close the connection
    try:
        connection.close()
        
        # Track connection closure
        if db_monitor:
            db_monitor.connection_closed()
            if logger:
                logger.debug("database_connection_closed")
            
    except Exception as e:
        if logger:
            logger.error("database_connection_close_failed", error=str(e))
        # Don't raise the exception for connection close failures
        pass