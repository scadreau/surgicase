# Created: 2025-07-15 09:20:13
# Last Modified: 2025-07-15 16:01:37

# core/database.py
import boto3
import json
import pymysql
import pymysql.cursors
import os
import time
from typing import Optional

# Import monitoring utilities
try:
    from utils.monitoring import db_monitor, logger, track_database_operation
except ImportError:
    # Fallback if monitoring is not available
    db_monitor = None
    logger = None
    track_database_operation = lambda operation, table="unknown": lambda func: func

def get_db_credentials(secret_name):
    """
    Function to fetch database credentials from AWS Secrets Manager
    """
    region = os.environ.get("AWS_REGION", "us-east-1")
    client = boto3.client("secretsmanager", region_name=region)
    response = client.get_secret_value(SecretId=secret_name)
    secret = json.loads(response["SecretString"])
    return secret

def get_db_connection():
    """
    Helper function to establish database connection with monitoring
    """
    start_time = time.time()
    
    try:
        # Fetch DB info from Secrets Manager
        secretdb = get_db_credentials("arn:aws:secretsmanager:us-east-1:002118831669:secret:prod/rds/serverinfo-MyhF8S")
        rds_host = secretdb["rds_address"]
        db_name = secretdb["db_name"]    
        secretdb = get_db_credentials("arn:aws:secretsmanager:us-east-1:002118831669:secret:rds!cluster-9376049b-abee-46d9-9cdb-95b95d6cdda0-fjhTNH")
        db_user = secretdb["username"]
        db_pass = secretdb["password"]
        
        # Create connection with autocommit=False for transaction control
        connection = pymysql.connect(
            host=rds_host, 
            user=db_user, 
            password=db_pass, 
            db=db_name,
            autocommit=False,  # Explicitly disable autocommit
            charset='utf8mb4',
            cursorclass=pymysql.cursors.DictCursor
        )
        
        # Track connection creation if monitoring is available
        if db_monitor:
            db_monitor.connection_created()
            duration = time.time() - start_time
            if logger:
                logger.debug("database_connection_established", duration=duration, host=rds_host)
        
        return connection
        
    except Exception as e:
        duration = time.time() - start_time
        
        # Track connection errors if monitoring is available
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
    Helper function to close database connection with monitoring
    """
    if connection and is_connection_valid(connection):
        try:
            connection.close()
            
            # Track connection closure if monitoring is available
            if db_monitor:
                db_monitor.connection_closed()
                if logger:
                    logger.debug("database_connection_closed")
                
        except Exception as e:
            if logger:
                logger.error("database_connection_close_failed", error=str(e))
            # Don't raise the exception for connection close failures
            pass