# Created: 2025-08-14 17:37:31
# Last Modified: 2025-08-22 06:26:51
# Author: Scott Cadreau

"""
Dashboard Database Utilities

This module provides database functions specifically for the monitoring dashboard.
It handles querying EC2 monitoring data for visualization and analysis.
"""

import sys
import os
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
import logging

# Add parent directory to path to import core modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from core.database import get_db_connection, close_db_connection

# Configure logging
logger = logging.getLogger(__name__)

# Constants
EC2_INSTANCE_ID = "i-089794865fce8cb91"

def get_latest_monitoring_data() -> Optional[Dict]:
    """
    Get the most recent monitoring data for the EC2 instance.
    
    Returns:
        dict: Latest monitoring record or None if no data available
        
    Example:
        {
            'timestamp': datetime,
            'cpu_utilization_percent': 1.3,
            'memory_utilization_percent': 8.7,
            'network_in_bytes': 951000,
            'network_out_bytes': 955000,
            'disk_read_bytes': 2283516928,
            'disk_write_bytes': 27526662144,
            'notes': ''
        }
    """
    try:
        connection = get_db_connection()
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT timestamp, cpu_utilization_percent, memory_utilization_percent,
                       network_in_bytes, network_out_bytes, disk_read_bytes, disk_write_bytes,
                       status_check_failed, status_check_failed_instance, status_check_failed_system,
                       notes
                FROM ec2_monitoring 
                WHERE instance_id = %s
                ORDER BY timestamp DESC 
                LIMIT 1
            """, (EC2_INSTANCE_ID,))
            
            result = cursor.fetchone()
            return result if result else None
            
    except Exception as e:
        logger.error(f"Failed to get latest monitoring data: {str(e)}")
        return None
    finally:
        if 'connection' in locals():
            close_db_connection(connection)

def get_monitoring_data_by_hours(hours: int = 24) -> List[Dict]:
    """
    Get monitoring data for the specified number of hours.
    
    Args:
        hours: Number of hours to look back (default: 24)
        
    Returns:
        list: List of monitoring records sorted by timestamp
        
    Example:
        [
            {
                'timestamp': datetime,
                'cpu_utilization_percent': 1.3,
                'memory_utilization_percent': 8.7,
                ...
            },
            ...
        ]
    """
    try:
        connection = get_db_connection()
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT timestamp, cpu_utilization_percent, memory_utilization_percent,
                       network_in_bytes, network_out_bytes, disk_read_bytes, disk_write_bytes,
                       status_check_failed, notes
                FROM ec2_monitoring 
                WHERE instance_id = %s
                  AND timestamp >= DATE_SUB(NOW(), INTERVAL %s HOUR)
                ORDER BY timestamp ASC
            """, (EC2_INSTANCE_ID, hours))
            
            results = cursor.fetchall()
            return results if results else []
            
    except Exception as e:
        logger.error(f"Failed to get monitoring data for {hours} hours: {str(e)}")
        return []
    finally:
        if 'connection' in locals():
            close_db_connection(connection)

def get_monitoring_summary_stats(hours: int = 24) -> Dict:
    """
    Get summary statistics for the specified time period.
    
    Args:
        hours: Number of hours to analyze (default: 24)
        
    Returns:
        dict: Summary statistics including averages, peaks, etc.
        
    Example:
        {
            'avg_cpu': 1.5,
            'max_cpu': 3.2,
            'avg_memory': 8.5,
            'max_memory': 9.1,
            'total_records': 1440,
            'alert_count': 0
        }
    """
    try:
        connection = get_db_connection()
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT 
                    AVG(cpu_utilization_percent) as avg_cpu,
                    MAX(cpu_utilization_percent) as max_cpu,
                    MIN(cpu_utilization_percent) as min_cpu,
                    AVG(memory_utilization_percent) as avg_memory,
                    MAX(memory_utilization_percent) as max_memory,
                    MIN(memory_utilization_percent) as min_memory,
                    COUNT(*) as total_records,
                    COALESCE(SUM(CASE WHEN notes IS NOT NULL AND notes != '' THEN 1 ELSE 0 END), 0) as alert_count
                FROM ec2_monitoring 
                WHERE instance_id = %s
                  AND timestamp >= DATE_SUB(NOW(), INTERVAL %s HOUR)
            """, (EC2_INSTANCE_ID, hours))
            
            result = cursor.fetchone()
            
            if result:
                return {
                    'avg_cpu': round(float(result['avg_cpu']), 2) if result['avg_cpu'] is not None else 0,
                    'max_cpu': round(float(result['max_cpu']), 2) if result['max_cpu'] is not None else 0,
                    'min_cpu': round(float(result['min_cpu']), 2) if result['min_cpu'] is not None else 0,
                    'avg_memory': round(float(result['avg_memory']), 2) if result['avg_memory'] is not None else 0,
                    'max_memory': round(float(result['max_memory']), 2) if result['max_memory'] is not None else 0,
                    'min_memory': round(float(result['min_memory']), 2) if result['min_memory'] is not None else 0,
                    'total_records': int(result['total_records'] or 0),
                    'alert_count': int(result['alert_count'] or 0)
                }
            else:
                return {}
                
    except Exception as e:
        logger.error(f"Failed to get summary stats for {hours} hours: {str(e)}")
        return {}
    finally:
        if 'connection' in locals():
            close_db_connection(connection)

def get_recent_alerts(limit: int = 10) -> List[Dict]:
    """
    Get recent alerts and warnings from monitoring data.
    
    Args:
        limit: Maximum number of alerts to return (default: 10)
        
    Returns:
        list: List of alert records with timestamps and messages
        
    Example:
        [
            {
                'timestamp': datetime,
                'message': 'High CPU utilization: 85.2%',
                'severity': 'warning'
            },
            ...
        ]
    """
    try:
        connection = get_db_connection()
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT timestamp, notes, cpu_utilization_percent, memory_utilization_percent
                FROM ec2_monitoring 
                WHERE instance_id = %s
                  AND (notes IS NOT NULL AND notes != '')
                ORDER BY timestamp DESC 
                LIMIT %s
            """, (EC2_INSTANCE_ID, limit))
            
            results = cursor.fetchall()
            alerts = []
            
            for row in results:
                severity = 'info'
                if row['cpu_utilization_percent'] and row['cpu_utilization_percent'] > 80:
                    severity = 'warning'
                if row['memory_utilization_percent'] and row['memory_utilization_percent'] > 80:
                    severity = 'warning'
                if 'failed' in row['notes'].lower():
                    severity = 'error'
                
                alerts.append({
                    'timestamp': row['timestamp'],
                    'message': row['notes'],
                    'severity': severity
                })
            
            return alerts
            
    except Exception as e:
        logger.error(f"Failed to get recent alerts: {str(e)}")
        return []
    finally:
        if 'connection' in locals():
            close_db_connection(connection)

def get_hourly_aggregated_data(hours: int = 24) -> List[Dict]:
    """
    Get monitoring data aggregated by hour for better performance with large datasets.
    
    Args:
        hours: Number of hours to look back (default: 24)
        
    Returns:
        list: List of hourly aggregated records
        
    Example:
        [
            {
                'hour': datetime,
                'avg_cpu': 1.5,
                'max_cpu': 2.1,
                'avg_memory': 8.5,
                'max_memory': 9.0,
                'record_count': 60
            },
            ...
        ]
    """
    try:
        connection = get_db_connection()
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT 
                    DATE_FORMAT(timestamp, '%Y-%m-%d %H:00:00') as hour,
                    AVG(cpu_utilization_percent) as avg_cpu,
                    MAX(cpu_utilization_percent) as max_cpu,
                    AVG(memory_utilization_percent) as avg_memory,
                    MAX(memory_utilization_percent) as max_memory,
                    AVG(network_in_bytes) as avg_network_in,
                    AVG(network_out_bytes) as avg_network_out,
                    COUNT(*) as record_count
                FROM ec2_monitoring 
                WHERE instance_id = %s
                  AND timestamp >= DATE_SUB(NOW(), INTERVAL %s HOUR)
                GROUP BY DATE_FORMAT(timestamp, '%Y-%m-%d %H:00:00')
                ORDER BY hour ASC
            """, (EC2_INSTANCE_ID, hours))
            
            results = cursor.fetchall()
            aggregated_data = []
            
            for row in results:
                aggregated_data.append({
                    'hour': datetime.strptime(row['hour'], '%Y-%m-%d %H:%M:%S'),
                    'avg_cpu': round(float(row['avg_cpu']), 2) if row['avg_cpu'] else 0,
                    'max_cpu': round(float(row['max_cpu']), 2) if row['max_cpu'] else 0,
                    'avg_memory': round(float(row['avg_memory']), 2) if row['avg_memory'] else 0,
                    'max_memory': round(float(row['max_memory']), 2) if row['max_memory'] else 0,
                    'avg_network_in': int(float(row['avg_network_in'])) if row['avg_network_in'] else 0,
                    'avg_network_out': int(float(row['avg_network_out'])) if row['avg_network_out'] else 0,
                    'record_count': int(row['record_count'])
                })
            
            return aggregated_data
            
    except Exception as e:
        logger.error(f"Failed to get hourly aggregated data: {str(e)}")
        return []
    finally:
        if 'connection' in locals():
            close_db_connection(connection)

def get_system_health_score() -> Tuple[int, str]:
    """
    Calculate a simple health score based on recent metrics.
    
    Returns:
        tuple: (score, status) where score is 0-100 and status is descriptive
        
    Example:
        (95, "Excellent")
        (75, "Good")
        (45, "Warning")
        (15, "Critical")
    """
    try:
        # Get recent data for health assessment
        recent_data = get_monitoring_data_by_hours(1)  # Last hour
        
        if not recent_data:
            # Try getting the latest single record
            latest_data = get_latest_monitoring_data()
            if not latest_data:
                return (0, "No Data")
            recent_data = [latest_data]
        
        # Calculate average metrics - convert Decimal to float
        cpu_values = [float(r['cpu_utilization_percent']) for r in recent_data if r['cpu_utilization_percent'] is not None]
        memory_values = [float(r['memory_utilization_percent']) for r in recent_data if r['memory_utilization_percent'] is not None]
        
        # Default to reasonable values if no data
        avg_cpu = sum(cpu_values) / len(cpu_values) if cpu_values else 1.0  # Default to 1% CPU
        avg_memory = sum(memory_values) / len(memory_values) if memory_values else 8.0  # Default to 8% memory
        
        # If we have no recent data but have CPU/memory from latest, that's still good
        if not cpu_values and not memory_values:
            return (85, "Limited Data")
        
        # Check for recent alerts
        try:
            alerts = get_recent_alerts(5)
            alert_penalty = len(alerts) * 5  # Reduced penalty
        except Exception:
            alert_penalty = 0
        
        # Calculate score (higher usage = lower score)
        # Ensure we don't get negative scores from very low usage
        cpu_score = max(50, 100 - (avg_cpu * 1.2))  # Minimum 50 points for CPU
        memory_score = max(50, 100 - avg_memory)    # Minimum 50 points for memory
        
        # If both CPU and memory are very low (healthy), give bonus points
        if avg_cpu < 5 and avg_memory < 15:
            cpu_score = min(100, cpu_score + 10)
            memory_score = min(100, memory_score + 10)
        
        # Overall score
        base_score = (cpu_score + memory_score) / 2
        final_score = max(25, int(base_score - alert_penalty))  # Minimum score of 25
        
        # Determine status
        if final_score >= 90:
            status = "Excellent"
        elif final_score >= 75:
            status = "Good"
        elif final_score >= 50:
            status = "Warning"
        elif final_score >= 25:
            status = "Poor"
        else:
            status = "Critical"
        
        return (final_score, status)
        
    except Exception as e:
        logger.error(f"Failed to calculate health score: {str(e)}")
        # Return a reasonable default based on current system state
        try:
            latest = get_latest_monitoring_data()
            if latest and latest['cpu_utilization_percent'] and latest['cpu_utilization_percent'] < 10:
                return (85, "Good")
        except Exception:
            pass
        return (50, "Unknown")
