# Created: 2025-07-28 23:42:24
# Last Modified: 2025-07-28 23:42:26
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

from core.database import get_db_connection, close_db_connection, _initialize_pool


class TestConnectionPooling(unittest.TestCase):
    """Test cases for database connection pooling functionality"""
    
    def setUp(self):
        """Reset pool state before each test"""
        import core.database as db_module
        db_module._connection_pool = None
        db_module._credentials_cache = {}
        
    @patch('core.database._create_connection')
    @patch('core.database.get_db_credentials')
    def test_credential_caching(self, mock_get_credentials, mock_create_conn):
        """Test that AWS Secrets Manager credentials are cached for 5 minutes"""
        # Mock credentials response
        mock_credentials = {
            "rds_address": "test-host",
            "db_name": "test_db",
            "username": "test_user", 
            "password": "test_pass"
        }
        mock_get_credentials.return_value = mock_credentials
        
        # Mock connection
        mock_conn = MagicMock()
        mock_conn.open = True
        mock_create_conn.return_value = mock_conn
        
        # First call should fetch from AWS
        conn1 = get_db_connection()
        self.assertEqual(mock_get_credentials.call_count, 2)  # Called twice for different secrets
        
        # Second call within 5 minutes should use cache
        conn2 = get_db_connection()
        self.assertEqual(mock_get_credentials.call_count, 2)  # No additional calls
        
        close_db_connection(conn1)
        close_db_connection(conn2)
        
    @patch('core.database._create_connection')
    @patch('core.database.get_db_credentials')
    def test_connection_pool_reuse(self, mock_get_credentials, mock_create_conn):
        """Test that connections are reused from the pool"""
        # Mock credentials
        mock_get_credentials.return_value = {"test": "data"}
        
        # Mock connection
        mock_conn = MagicMock()
        mock_conn.open = True
        mock_conn.get_autocommit.return_value = False
        mock_create_conn.return_value = mock_conn
        
        # Get connection and return to pool
        conn1 = get_db_connection()
        close_db_connection(conn1)
        
        # Get another connection - should reuse from pool
        conn2 = get_db_connection()
        
        # Should only create one connection since second was reused
        self.assertEqual(mock_create_conn.call_count, 1)
        
        close_db_connection(conn2)
        
    @patch('core.database._create_connection')
    @patch('core.database.get_db_credentials')
    def test_concurrent_connections(self, mock_get_credentials, mock_create_conn):
        """Test handling of concurrent connection requests"""
        mock_get_credentials.return_value = {"test": "data"}
        
        # Create multiple mock connections
        mock_connections = []
        for i in range(5):
            mock_conn = MagicMock()
            mock_conn.open = True
            mock_conn.get_autocommit.return_value = False
            mock_connections.append(mock_conn)
        
        mock_create_conn.side_effect = mock_connections
        
        connections = []
        
        def get_connection():
            conn = get_db_connection()
            connections.append(conn)
            time.sleep(0.1)  # Simulate work
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
        
    @patch('core.database._create_connection')
    @patch('core.database.get_db_credentials')
    def test_invalid_connection_replacement(self, mock_get_credentials, mock_create_conn):
        """Test that invalid connections are replaced with new ones"""
        mock_get_credentials.return_value = {"test": "data"}
        
        # First connection (valid)
        mock_conn1 = MagicMock()
        mock_conn1.open = True
        mock_conn1.ping.return_value = None
        mock_conn1.get_autocommit.return_value = False
        
        # Second connection (invalid)
        mock_conn2 = MagicMock()
        mock_conn2.open = False
        mock_conn2.ping.side_effect = Exception("Connection lost")
        
        # Replacement connection
        mock_conn3 = MagicMock()
        mock_conn3.open = True
        mock_conn3.ping.return_value = None
        
        mock_create_conn.side_effect = [mock_conn1, mock_conn2, mock_conn3]
        
        # Get and return first connection
        conn1 = get_db_connection()
        close_db_connection(conn1)
        
        # Mock that connection became invalid
        mock_conn1.open = False
        mock_conn1.ping.side_effect = Exception("Connection lost")
        
        # Get connection again - should create new one since pooled one is invalid
        conn2 = get_db_connection()
        
        # Should have created 2 connections (original + replacement)
        self.assertGreaterEqual(mock_create_conn.call_count, 2)
        
        close_db_connection(conn2)
        
    def test_pool_initialization(self):
        """Test that pool is properly initialized with environment variables"""
        with patch.dict(os.environ, {
            'DB_POOL_SIZE': '5',
            'DB_POOL_MAX_OVERFLOW': '3',
            'DB_POOL_TIMEOUT': '15'
        }):
            with patch('core.database._create_connection') as mock_create:
                mock_conn = MagicMock()
                mock_conn.open = True
                mock_create.return_value = mock_conn
                
                with patch('core.database.get_db_credentials'):
                    _initialize_pool()
                    
                    import core.database as db_module
                    self.assertEqual(db_module._pool_config['pool_size'], 5)
                    self.assertEqual(db_module._pool_config['max_overflow'], 3)
                    self.assertEqual(db_module._pool_config['pool_timeout'], 15)


if __name__ == '__main__':
    unittest.main() 