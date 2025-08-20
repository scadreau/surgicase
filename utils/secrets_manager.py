# Created: 2025-08-08 15:34:05
# Last Modified: 2025-08-20 08:45:25
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
    
    def warm_cache(self, secret_names: list, custom_ttls: Dict[str, int] = None) -> Dict[str, Any]:
        """
        Pre-load multiple secrets into cache for improved performance.
        
        Args:
            secret_names: List of secret names/ARNs to pre-load
            custom_ttls: Optional dictionary mapping secret names to custom TTL values
            
        Returns:
            Dictionary with warming results including success/failure counts and details
        """
        if custom_ttls is None:
            custom_ttls = {}
            
        results = {
            "total_secrets": len(secret_names),
            "successful": 0,
            "failed": 0,
            "details": [],
            "start_time": time.time()
        }
        
        logger.info(f"Starting cache warming for {len(secret_names)} secrets")
        
        for secret_name in secret_names:
            try:
                # Use custom TTL if provided, otherwise use default
                ttl = custom_ttls.get(secret_name, 3600)  # Default 1 hour
                
                # This will cache the secret
                secret_data = self.get_secret(secret_name, cache_ttl=ttl)
                
                results["successful"] += 1
                results["details"].append({
                    "secret_name": secret_name,
                    "status": "success",
                    "ttl": ttl,
                    "keys_count": len(secret_data) if isinstance(secret_data, dict) else 0
                })
                logger.debug(f"Successfully warmed cache for secret: {secret_name}")
                
            except Exception as e:
                results["failed"] += 1
                results["details"].append({
                    "secret_name": secret_name,
                    "status": "failed",
                    "error": str(e)
                })
                logger.warning(f"Failed to warm cache for secret {secret_name}: {str(e)}")
        
        results["duration_seconds"] = time.time() - results["start_time"]
        
        logger.info(f"Cache warming completed: {results['successful']}/{results['total_secrets']} successful in {results['duration_seconds']:.2f}s")
        return results

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

def warm_secrets_cache(secret_names: list = None, custom_ttls: Dict[str, int] = None) -> Dict[str, Any]:
    """
    Pre-load secrets into cache using the global secrets manager instance.
    
    Args:
        secret_names: List of secret names to warm. If None, warms all known secrets.
        custom_ttls: Optional dictionary mapping secret names to custom TTL values
        
    Returns:
        Dictionary with warming results
    """
    if secret_names is None:
        secret_names = get_all_known_secrets()
        
    return secrets_manager.warm_cache(secret_names, custom_ttls)

def get_all_known_secrets() -> list:
    """
    Get list of all known secrets used by the application.
    
    Returns:
        List of secret names/ARNs used throughout the application
    """
    return [
        # Database credentials (highest priority - 4 hour cache)
        "arn:aws:secretsmanager:us-east-1:002118831669:secret:rds!cluster-9376049b-abee-46d9-9cdb-95b95d6cdda0-fjhTNH",
        
        # Core application secrets (1 hour cache)
        "surgicase/main",
        "surgicase/ses_keys", 
        "surgicase/email_templates",
        "surgicase/sms_templates",
        "surgicase/twilio_keys",
        
        # S3 configuration secrets (1 hour cache)
        "surgicase/s3-user-reports",
        "surgicase/s3-case-documents", 
        "surgicase/s3-user-documents"
    ]

def get_default_secret_ttls() -> Dict[str, int]:
    """
    Get default TTL values for different types of secrets.
    
    Returns:
        Dictionary mapping secret names to their optimal TTL values
    """
    return {
        # Database secret - 4 hours (rotates weekly)
        "arn:aws:secretsmanager:us-east-1:002118831669:secret:rds!cluster-9376049b-abee-46d9-9cdb-95b95d6cdda0-fjhTNH": 14400,
        
        # All other secrets - 1 hour (default)
        # These will use the default 3600 seconds if not specified
    }

def warm_all_secrets() -> Dict[str, Any]:
    """
    Warm cache for all known application secrets with optimal TTL values.
    
    This function is designed to be called during application startup to
    pre-load all secrets and eliminate cold start latency.
    
    Returns:
        Dictionary with detailed warming results
    """
    logger.info("Starting comprehensive cache warming for all application secrets")
    
    secret_names = get_all_known_secrets()
    custom_ttls = get_default_secret_ttls()
    
    results = warm_secrets_cache(secret_names, custom_ttls)
    
    # Log summary
    if results["failed"] == 0:
        logger.info(f"✅ Cache warming successful: All {results['successful']} secrets loaded in {results['duration_seconds']:.2f}s")
    else:
        logger.warning(f"⚠️ Cache warming partial: {results['successful']}/{results['total_secrets']} secrets loaded in {results['duration_seconds']:.2f}s")
        
        # Log failed secrets for debugging
        for detail in results["details"]:
            if detail["status"] == "failed":
                logger.error(f"Failed to warm {detail['secret_name']}: {detail['error']}")
    
    return results
