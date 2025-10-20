# Created: 2025-07-15 09:20:13
# Last Modified: 2025-10-20 12:59:39
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
_connection_metadata: Dict[int, Dict[str, float]] = {}  # Track connection creation/last_used times
_secrets_health: Dict[str, Any] = {"last_success": time.time(), "consecutive_failures": 0}  # Track secrets manager health

def get_db_credentials(secret_name: str) -> Dict[str, Any]:
    """
    Function to fetch database credentials from AWS Secrets Manager using centralized secrets manager.
    Tracks secrets manager health for connection pool management.
    """
    global _secrets_health
    
    from utils.secrets_manager import get_secret
    
    try:
        credentials = get_secret(secret_name, cache_ttl=14400)  # 4 hours cache (DB secret rotates weekly)
        
        # Update health tracking on success
        _secrets_health["last_success"] = time.time()
        _secrets_health["consecutive_failures"] = 0
        
        return credentials
        
    except Exception as e:
        # Track failure but don't block - secrets_manager will use stale cache
        _secrets_health["consecutive_failures"] = _secrets_health.get("consecutive_failures", 0) + 1
        if logger:
            logger.debug(f"Secret fetch issue (will use stale cache): {str(e)}")
        raise

def drain_connection_pool():
    """
    Drain all connections from the pool (they likely have stale credentials).
    This is called when credential rotation is detected.
    """
    global _connection_pool, _connection_metadata
    
    if not _connection_pool:
        return
        
    drained_count = 0
    with _pool_lock:
        # Drain all connections from pool
        while not _connection_pool.empty():
            try:
                conn = _connection_pool.get_nowait()
                conn_id = id(conn)
                
                # Clean up metadata
                if conn_id in _connection_metadata:
                    del _connection_metadata[conn_id]
                
                # Close the connection
                try:
                    conn.close()
                    drained_count += 1
                except Exception:
                    pass  # Ignore close errors for stale connections
                    
            except Exception:
                break  # Queue is empty
    
    if logger and drained_count > 0:
        logger.info(f"🔄 Drained {drained_count} connections from pool due to credential rotation")

def _rewarm_secrets_and_pool():
    """
    Background function to rewarm secrets cache and connection pool after credential rotation.
    Runs in a separate thread to avoid blocking the main request.
    """
    try:
        # Rewarm the database credentials cache
        from utils.secrets_manager import get_secret
        secret_name = "arn:aws:secretsmanager:us-east-1:002118831669:secret:rds!cluster-9376049b-abee-46d9-9cdb-95b95d6cdda0-fjhTNH"
        get_secret(secret_name, cache_ttl=14400)  # Rewarm with normal TTL
        
        if logger:
            logger.info("🔥 Database credentials cache rewarmed")
        
        # Rewarm connection pool (create some connections in advance)
        if _connection_pool:
            target_connections = min(_pool_config.get("pool_size", 50) // 2, 50)  # Rewarm half the pool, max 10
            created_count = 0
            
            for _ in range(target_connections):
                try:
                    if not _connection_pool.full():
                        conn = _create_connection()
                        _connection_pool.put(conn, block=False)
                        
                        # Track connection metadata
                        conn_id = id(conn)
                        current_time = time.time()
                        _connection_metadata[conn_id] = {
                            "created_at": current_time,
                            "last_used": current_time
                        }
                        created_count += 1
                    else:
                        break
                except Exception as e:
                    if logger:
                        logger.warning(f"Failed to create connection during rewarm: {e}")
                    break
            
            if logger and created_count > 0:
                logger.info(f"🔥 Connection pool rewarmed with {created_count} new connections")
                
    except Exception as e:
        if logger:
            logger.error(f"❌ Error during background rewarm: {e}")

def _create_connection() -> pymysql.Connection:
    """Create a new database connection with automatic credential rotation handling"""
    # Hardcoded values (optimization: eliminates one secrets call)
    rds_host = "dev1-metoray-aurora-a98fdy.cluster-cahckueig7sf.us-east-1.rds.amazonaws.com"
    db_name = "allstars"
    secret_name = "arn:aws:secretsmanager:us-east-1:002118831669:secret:rds!cluster-9376049b-abee-46d9-9cdb-95b95d6cdda0-fjhTNH"
    
    try:
        # Fetch credentials from Secrets Manager (cached)
        secretdb = get_db_credentials(secret_name)
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
        
    except pymysql.OperationalError as e:
        # Check if this is an authentication failure (credential rotation)
        if "Access denied" in str(e) or "authentication" in str(e).lower():
            if logger:
                logger.warning("🔄 Database authentication failed - credential rotation detected")
                logger.info("✨ Implementing automagic recovery logic - doing some cool shit to fix this!")
            
            # Clear the secrets cache immediately
            from utils.secrets_manager import secrets_manager
            secrets_manager.clear_cache(secret_name)
            
            # Drain the connection pool (all connections have stale credentials)
            drain_connection_pool()
            
            # Start background rewarm thread (non-blocking)
            import threading
            rewarm_thread = threading.Thread(target=_rewarm_secrets_and_pool, daemon=True)
            rewarm_thread.start()
            
            if logger:
                logger.info("🔄 Cache cleared, pool drained, background rewarm started")
            
            # Retry connection with fresh credentials
            try:
                secretdb = get_db_credentials(secret_name)
                db_user = secretdb["username"]
                db_pass = secretdb["password"]
                
                connection = pymysql.connect(
                    host=rds_host, 
                    user=db_user, 
                    password=db_pass, 
                    database=db_name,
                    autocommit=False,
                    charset='utf8mb4',
                    cursorclass=pymysql.cursors.DictCursor
                )
                
                if logger:
                    logger.info("✅ Database connection recovered after credential rotation")
                
                return connection
                
            except Exception as retry_error:
                if logger:
                    logger.error(f"❌ Failed to recover database connection after credential rotation: {retry_error}")
                raise
        else:
            # Not an auth error, re-raise original exception
            raise

def _initialize_pool():
    """Initialize the connection pool"""
    global _connection_pool, _pool_config
    
    with _pool_lock:
        if _connection_pool is not None:
            return
            
        # Pool configuration - hardcoded for 16vCPU/64GB dedicated server
        # Optimized based on: 16 vCPUs × 3 = 48 base connections + 25 overflow = 75 total max
        _pool_config = {
            "pool_size": 50,           # Base pool size
            "max_overflow": 50,        # Additional connections during traffic spikes
            "pool_timeout": 3,         # Connection acquisition timeout (seconds)
            "max_idle_time": 3600,     # Close connections idle > 1 hour
            "max_lifetime": 14400      # Close connections older than 4 hours
        }
        pool_size = _pool_config["pool_size"]
        
        _connection_pool = Queue(maxsize=pool_size + _pool_config["max_overflow"])
        
        # Pre-populate with initial connections - more aggressive for dedicated server
        for _ in range(min(pool_size, 50)):  # Start with 50 connections
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
                # Update last_used time
                conn_id = id(connection)
                if conn_id in _connection_metadata:
                    _connection_metadata[conn_id]["last_used"] = time.time()
                
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
        
        # Track connection metadata
        conn_id = id(connection)
        current_time = time.time()
        _connection_metadata[conn_id] = {
            "created_at": current_time,
            "last_used": current_time
        }
        
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
        # Clean up metadata
        conn_id = id(connection)
        if conn_id in _connection_metadata:
            del _connection_metadata[conn_id]
            
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

def cleanup_stale_connections() -> Dict[str, Any]:
    """
    Clean up stale connections from the pool based on TTL settings.
    
    During AWS Secrets Manager outages, extends connection lifetimes to preserve
    existing authenticated connections, as they will continue to work even when
    we can't refresh credentials.
    
    Returns:
        Dict with cleanup statistics
    """
    global _connection_pool, _connection_metadata, _secrets_health
    
    if not _connection_pool:
        return {"status": "no_pool", "cleaned": 0}
    
    current_time = time.time()
    max_idle = _pool_config.get("max_idle_time", 3600)
    max_lifetime = _pool_config.get("max_lifetime", 14400)
    
    # Check if secrets manager is having issues (stale cache being used)
    time_since_last_success = current_time - _secrets_health.get("last_success", current_time)
    secrets_degraded = time_since_last_success > 3600  # No successful refresh in 1+ hour
    
    # During secrets issues, extend connection lifetimes 2x
    # Existing connections are already authenticated and will work fine
    if secrets_degraded:
        max_idle = max_idle * 2
        max_lifetime = max_lifetime * 2
        if logger:
            logger.info(f"🛡️ Secrets Manager degraded - extending connection lifetimes (idle: {max_idle/3600:.1f}h, lifetime: {max_lifetime/3600:.1f}h)")
    
    cleaned_connections = 0
    stale_connections = []
    
    with _pool_lock:
        # Create a new queue to hold valid connections
        temp_connections = []
        
        # Check all connections in pool
        while not _connection_pool.empty():
            try:
                connection = _connection_pool.get_nowait()
                conn_id = id(connection)
                
                # Check if connection has metadata
                if conn_id not in _connection_metadata:
                    # No metadata, assume stale
                    stale_connections.append(connection)
                    continue
                
                metadata = _connection_metadata[conn_id]
                age = current_time - metadata["created_at"]
                idle_time = current_time - metadata["last_used"]
                
                # Check if connection is stale
                if age > max_lifetime or idle_time > max_idle:
                    stale_connections.append(connection)
                elif not is_connection_valid(connection):
                    stale_connections.append(connection)
                else:
                    # Connection is still good
                    temp_connections.append(connection)
                    
            except Exception:
                break
        
        # Put valid connections back in pool
        for conn in temp_connections:
            try:
                _connection_pool.put_nowait(conn)
            except Exception:
                # Pool full, close excess connection
                stale_connections.append(conn)
    
    # Close stale connections
    for conn in stale_connections:
        try:
            conn_id = id(conn)
            if conn_id in _connection_metadata:
                del _connection_metadata[conn_id]
            conn.close()
            cleaned_connections += 1
        except Exception as e:
            if logger:
                logger.warning(f"Error closing stale connection: {e}")
    
    if logger and cleaned_connections > 0:
        logger.info(f"🧹 Cleaned up {cleaned_connections} stale database connections")
    
    return {
        "status": "success",
        "cleaned": cleaned_connections,
        "remaining_in_pool": _connection_pool.qsize() if _connection_pool else 0,
        "tracked_connections": len(_connection_metadata),
        "secrets_degraded": secrets_degraded,
        "extended_lifetimes": secrets_degraded
    }

def prewarm_connection_pool(target_connections: int = None) -> Dict[str, Any]:
    """
    Pre-warm the connection pool by creating connections up to target size.
    
    Args:
        target_connections: Number of connections to ensure in pool (default: pool_size)
    
    Returns:
        Dict with prewarming statistics
    """
    global _connection_pool
    
    if not _connection_pool:
        _initialize_pool()
    
    if target_connections is None:
        target_connections = _pool_config.get("pool_size", 50)
    
    current_size = _connection_pool.qsize()
    connections_needed = max(0, target_connections - current_size)
    
    if connections_needed == 0:
        return {
            "status": "already_warm",
            "current_size": current_size,
            "target_size": target_connections,
            "created": 0
        }
    
    created_connections = 0
    
    for _ in range(connections_needed):
        try:
            if _connection_pool.full():
                break
                
            conn = _create_connection()
            
            # Track connection metadata
            conn_id = id(conn)
            current_time = time.time()
            _connection_metadata[conn_id] = {
                "created_at": current_time,
                "last_used": current_time
            }
            
            _connection_pool.put_nowait(conn)
            created_connections += 1
            
        except Exception as e:
            if logger:
                logger.warning(f"Error creating connection during prewarming: {e}")
            break
    
    if logger and created_connections > 0:
        logger.info(f"🔥 Pre-warmed connection pool: created {created_connections} connections")
    
    return {
        "status": "success",
        "current_size": _connection_pool.qsize(),
        "target_size": target_connections,
        "created": created_connections
    }

def get_pool_stats() -> Dict[str, Any]:
    """
    Get current connection pool statistics.
    
    Returns:
        Dict with pool statistics
    """
    global _connection_pool, _connection_metadata
    
    if not _connection_pool:
        return {"status": "no_pool"}
    
    current_time = time.time()
    stats = {
        "pool_size": _connection_pool.qsize(),
        "max_pool_size": _pool_config.get("pool_size", 50),
        "max_overflow": _pool_config.get("max_overflow", 25),
        "tracked_connections": len(_connection_metadata),
        "connection_ages": [],
        "idle_times": []
    }
    
    # Calculate connection ages and idle times
    for conn_id, metadata in _connection_metadata.items():
        age = current_time - metadata["created_at"]
        idle_time = current_time - metadata["last_used"]
        stats["connection_ages"].append(age)
        stats["idle_times"].append(idle_time)
    
    if stats["connection_ages"]:
        stats["avg_connection_age"] = sum(stats["connection_ages"]) / len(stats["connection_ages"])
        stats["max_connection_age"] = max(stats["connection_ages"])
        stats["avg_idle_time"] = sum(stats["idle_times"]) / len(stats["idle_times"])
        stats["max_idle_time"] = max(stats["idle_times"])
    
    return stats