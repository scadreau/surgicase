# Created: 2025-07-28 23:42:24
# Last Modified: 2025-07-28 23:49:54
# Author: Scott Cadreau

import unittest
import time
import threading
from unittest.mock import patch, MagicMock
import sys
import os

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)


class TestConnectionPooling(unittest.TestCase):
    """Test cases for database connection pooling functionality"""
    
    def setUp(self):
        """Reset pool state before each test"""
        # Reset global state
        import core.database as db_module
        db_module._connection_pool = None
        db_module._credentials_cache = {}
        db_module._pool_config = {}
        
    @patch('core.database.boto3.client')
    def test_credential_caching(self, mock_boto_client):
        """Test that AWS Secrets Manager credentials are cached for 5 minutes"""
        from core.database import get_db_credentials
        
        # Mock the boto3 client and response
        mock_secrets_client = MagicMock()
        mock_boto_client.return_value = mock_secrets_client
        
        mock_response = {
            "SecretString": '{"rds_address": "test-host", "db_name": "test_db", "username": "test_user", "password": "test_pass"}'
        }
        mock_secrets_client.get_secret_value.return_value = mock_response
        
        # First call should fetch from AWS
        result1 = get_db_credentials("test-secret-1")
        self.assertEqual(mock_secrets_client.get_secret_value.call_count, 1)
        
        # Second call within 5 minutes should use cache
        result2 = get_db_credentials("test-secret-1")
        self.assertEqual(mock_secrets_client.get_secret_value.call_count, 1)  # No additional calls
        
        # Results should be the same
        self.assertEqual(result1, result2)
        
    @patch('core.database.boto3.client')
    @patch('core.database.pymysql.connect')
    def test_connection_pool_reuse(self, mock_pymysql_connect, mock_boto_client):
        """Test that connections are reused from the pool"""
        from core.database import get_db_connection, close_db_connection
        
        # Mock boto3 client
        mock_secrets_client = MagicMock()
        mock_boto_client.return_value = mock_secrets_client
        mock_response = {
            "SecretString": '{"rds_address": "test-host", "db_name": "test_db", "username": "test_user", "password": "test_pass"}'
        }
        mock_secrets_client.get_secret_value.return_value = mock_response
        
        # Mock pymysql connection
        mock_conn = MagicMock()
        mock_conn.open = True
        mock_conn.get_autocommit.return_value = False
        mock_conn.ping.return_value = None
        mock_pymysql_connect.return_value = mock_conn
        
        # Get connection and return to pool
        conn1 = get_db_connection()
        initial_calls = mock_pymysql_connect.call_count
        close_db_connection(conn1)
        
        # Get another connection - should reuse from pool
        conn2 = get_db_connection()
        
        # Should not create additional connections since second was reused
        self.assertEqual(mock_pymysql_connect.call_count, initial_calls)
        
        close_db_connection(conn2)
        
    @patch('core.database.boto3.client')
    @patch('core.database.pymysql.connect')
    def test_concurrent_connections(self, mock_pymysql_connect, mock_boto_client):
        """Test handling of concurrent connection requests"""
        from core.database import get_db_connection, close_db_connection
        
        # Mock boto3 client
        mock_secrets_client = MagicMock()
        mock_boto_client.return_value = mock_secrets_client
        mock_response = {
            "SecretString": '{"rds_address": "test-host", "db_name": "test_db", "username": "test_user", "password": "test_pass"}'
        }
        mock_secrets_client.get_secret_value.return_value = mock_response
        
        # Create multiple mock connections
        def create_mock_connection(*args, **kwargs):
            mock_conn = MagicMock()
            mock_conn.open = True
            mock_conn.get_autocommit.return_value = False
            mock_conn.ping.return_value = None
            return mock_conn
        
        mock_pymysql_connect.side_effect = create_mock_connection
        
        connections = []
        
        def get_connection():
            conn = get_db_connection()
            connections.append(conn)
            time.sleep(0.05)  # Simulate work
            close_db_connection(conn)
        
        # Start multiple threads
        threads = []
        for i in range(3):
            t = threading.Thread(target=get_connection)
            threads.append(t)
            t.start()
        
        # Wait for all threads to complete
        for t in threads:
            t.join()
        
        # Should have created connections for concurrent requests
        self.assertEqual(len(connections), 3)
        # Should have created some connections (but may reuse some from pool)
        self.assertGreater(mock_pymysql_connect.call_count, 0)
        
    @patch('core.database.boto3.client')
    @patch('core.database.pymysql.connect')
    def test_invalid_connection_replacement(self, mock_pymysql_connect, mock_boto_client):
        """Test that invalid connections are replaced with new ones"""
        from core.database import get_db_connection, close_db_connection
        
        # Mock boto3 client
        mock_secrets_client = MagicMock()
        mock_boto_client.return_value = mock_secrets_client
        mock_response = {
            "SecretString": '{"rds_address": "test-host", "db_name": "test_db", "username": "test_user", "password": "test_pass"}'
        }
        mock_secrets_client.get_secret_value.return_value = mock_response
        
        # Create mock connections that will be invalid when pinged
        def create_invalid_then_valid_connection(*args, **kwargs):
            mock_conn = MagicMock()
            mock_conn.open = True
            mock_conn.get_autocommit.return_value = False
            
            # First few connections will be "invalid" when retrieved from pool
            if mock_pymysql_connect.call_count <= 3:
                mock_conn.ping.side_effect = Exception("Connection lost")
            else:
                mock_conn.ping.return_value = None
            
            return mock_conn
            
        mock_pymysql_connect.side_effect = create_invalid_then_valid_connection
        
        # This should trigger connection creation and potentially replacement
        conn1 = get_db_connection()
        conn2 = get_db_connection()
        
        # Should have created some connections
        self.assertGreater(mock_pymysql_connect.call_count, 0)
        
        close_db_connection(conn1)
        close_db_connection(conn2)
        
    @patch.dict(os.environ, {
        'DB_POOL_SIZE': '5',
        'DB_POOL_MAX_OVERFLOW': '3',
        'DB_POOL_TIMEOUT': '15'
    })
    @patch('core.database.boto3.client')
    @patch('core.database.pymysql.connect')
    def test_pool_initialization(self, mock_pymysql_connect, mock_boto_client):
        """Test that pool is properly initialized with environment variables"""
        from core.database import _initialize_pool
        
        # Mock boto3 client
        mock_secrets_client = MagicMock()
        mock_boto_client.return_value = mock_secrets_client
        mock_response = {
            "SecretString": '{"rds_address": "test-host", "db_name": "test_db", "username": "test_user", "password": "test_pass"}'
        }
        mock_secrets_client.get_secret_value.return_value = mock_response
        
        # Mock connection
        mock_conn = MagicMock()
        mock_conn.open = True
        mock_conn.ping.return_value = None
        mock_pymysql_connect.return_value = mock_conn
        
        _initialize_pool()
        
        import core.database as db_module
        self.assertEqual(db_module._pool_config['pool_size'], 5)
        self.assertEqual(db_module._pool_config['max_overflow'], 3)
        self.assertEqual(db_module._pool_config['pool_timeout'], 15)

    @patch('core.database.boto3.client')
    def test_credential_cache_expiry(self, mock_boto_client):
        """Test that cached credentials expire after 5 minutes"""
        from core.database import get_db_credentials
        import core.database as db_module
        
        # Mock the boto3 client
        mock_secrets_client = MagicMock()
        mock_boto_client.return_value = mock_secrets_client
        
        mock_response = {
            "SecretString": '{"test": "data"}'
        }
        mock_secrets_client.get_secret_value.return_value = mock_response
        
        # First call
        result1 = get_db_credentials("test-secret")
        self.assertEqual(mock_secrets_client.get_secret_value.call_count, 1)
        
        # Simulate time passing (6 minutes)
        original_time = time.time
        with patch('core.database.time.time', return_value=original_time() + 360):  # 6 minutes later
            result2 = get_db_credentials("test-secret")
            # Should fetch again since cache expired
            self.assertEqual(mock_secrets_client.get_secret_value.call_count, 2)


if __name__ == '__main__':
    unittest.main() 