# Created: 2025-08-08 15:34:05
# Last Modified: 2025-08-20 08:38:53
# Author: Scott Cadreau

# utils/secrets_manager.py
import boto3
import json
import time
import threading
import logging
from typing import Dict, Any, Optional
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)

class SecretsManager:
    """
    Centralized AWS Secrets Manager with intelligent caching and thread safety.
    
    This class provides a unified interface for accessing AWS Secrets Manager
    with automatic caching, thread safety, and error handling. It reduces
    API calls and improves performance by maintaining an in-memory cache
    with configurable TTL values.
    """
    
    def __init__(self, region: str = "us-east-1"):
        """
        Initialize the SecretsManager.
        
        Args:
            region: AWS region for Secrets Manager client
        """
        self._client = boto3.client("secretsmanager", region_name=region)
        self._cache: Dict[str, Dict] = {}
        self._lock = threading.Lock()
        self._region = region
        
    def get_secret(self, secret_name: str, cache_ttl: int = 3600) -> Dict[str, Any]:
        """
        Get complete secret data with intelligent caching.
        
        Args:
            secret_name: Name or ARN of the secret in AWS Secrets Manager
            cache_ttl: Cache time-to-live in seconds (default: 1 hour)
            
        Returns:
            Dictionary containing the secret data
            
        Raises:
            ClientError: If there's an error accessing the secret
            json.JSONDecodeError: If the secret value is not valid JSON
        """
        with self._lock:
            cache_key = f"{secret_name}_data"
            time_key = f"{secret_name}_time"
            
            # Check cache first
            if (cache_key in self._cache and 
                time_key in self._cache and
                time.time() - self._cache[time_key] < cache_ttl):
                logger.debug(f"Returning cached secret: {secret_name}")
                return self._cache[cache_key]
            
            # Fetch from AWS if not cached or expired
            logger.info(f"Fetching secret from AWS: {secret_name}")
            try:
                response = self._client.get_secret_value(SecretId=secret_name)
                secret_data = json.loads(response["SecretString"])
                
                # Update cache
                self._cache[cache_key] = secret_data
                self._cache[time_key] = time.time()
                
                logger.debug(f"Successfully cached secret: {secret_name}")
                return secret_data
                
            except ClientError as e:
                error_code = e.response['Error']['Code']
                if error_code == 'ResourceNotFoundException':
                    logger.error(f"Secret {secret_name} not found")
                elif error_code == 'InvalidRequestException':
                    logger.error(f"Invalid request for secret {secret_name}")
                elif error_code == 'InvalidParameterException':
                    logger.error(f"Invalid parameter for secret {secret_name}")
                else:
                    logger.error(f"Error retrieving secret {secret_name}: {e}")
                raise
            except json.JSONDecodeError as e:
                logger.error(f"Error parsing secret {secret_name} as JSON: {e}")
                raise
            except Exception as e:
                logger.error(f"Unexpected error retrieving secret {secret_name}: {e}")
                raise
    
    def get_secret_value(self, secret_name: str, key: str, cache_ttl: int = 3600) -> Optional[str]:
        """
        Get a specific key from a secret.
        
        Args:
            secret_name: Name or ARN of the secret in AWS Secrets Manager
            key: Key within the secret to retrieve
            cache_ttl: Cache time-to-live in seconds (default: 1 hour)
            
        Returns:
            The secret value for the specified key, or None if not found
            
        Raises:
            ClientError: If there's an error accessing the secret
            json.JSONDecodeError: If the secret value is not valid JSON
        """
        secret_data = self.get_secret(secret_name, cache_ttl)
        return secret_data.get(key)
    
    def clear_cache(self, secret_name: Optional[str] = None) -> None:
        """
        Clear cached secrets.
        
        Args:
            secret_name: Specific secret to clear from cache. If None, clears all cached secrets.
        """
        with self._lock:
            if secret_name:
                cache_key = f"{secret_name}_data"
                time_key = f"{secret_name}_time"
                self._cache.pop(cache_key, None)
                self._cache.pop(time_key, None)
                logger.info(f"Cleared cache for secret: {secret_name}")
            else:
                self._cache.clear()
                logger.info("Cleared all cached secrets")
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics for monitoring.
        
        Returns:
            Dictionary with cache statistics
        """
        with self._lock:
            # Count cached secrets (each secret has _data and _time keys)
            secret_count = len([k for k in self._cache.keys() if k.endswith('_data')])
            
            # Get cache ages
            cache_ages = []
            current_time = time.time()
            for key, timestamp in self._cache.items():
                if key.endswith('_time'):
                    cache_ages.append(current_time - timestamp)
            
            return {
                "cached_secrets_count": secret_count,
                "total_cache_entries": len(self._cache),
                "oldest_cache_age_seconds": max(cache_ages) if cache_ages else 0,
                "newest_cache_age_seconds": min(cache_ages) if cache_ages else 0,
                "region": self._region
            }

# Global instance for application-wide use
secrets_manager = SecretsManager()

# Convenience functions for backward compatibility and ease of use
def get_secret(secret_name: str, cache_ttl: int = 3600) -> Dict[str, Any]:
    """
    Get complete secret data using the global secrets manager instance.
    
    Args:
        secret_name: Name or ARN of the secret in AWS Secrets Manager
        cache_ttl: Cache time-to-live in seconds (default: 1 hour)
        
    Returns:
        Dictionary containing the secret data
    """
    return secrets_manager.get_secret(secret_name, cache_ttl)

def get_secret_value(secret_name: str, key: str, cache_ttl: int = 3600) -> Optional[str]:
    """
    Get a specific key from a secret using the global secrets manager instance.
    
    Args:
        secret_name: Name or ARN of the secret in AWS Secrets Manager
        key: Key within the secret to retrieve
        cache_ttl: Cache time-to-live in seconds (default: 1 hour)
        
    Returns:
        The secret value for the specified key, or None if not found
    """
    return secrets_manager.get_secret_value(secret_name, key, cache_ttl)

def clear_secrets_cache(secret_name: Optional[str] = None) -> None:
    """
    Clear cached secrets using the global secrets manager instance.
    
    Args:
        secret_name: Specific secret to clear from cache. If None, clears all cached secrets.
    """
    return secrets_manager.clear_cache(secret_name)

def get_secrets_cache_stats() -> Dict[str, Any]:
    """
    Get cache statistics using the global secrets manager instance.
    
    Returns:
        Dictionary with cache statistics
    """
    return secrets_manager.get_cache_stats()
