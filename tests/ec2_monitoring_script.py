# Created: 2025-08-14 15:55:28
# Last Modified: 2025-08-14 16:35:37
# Author: Scott Cadreau

"""
EC2 Instance Monitoring Script

This script monitors CPU and memory usage of an EC2 instance and logs the data to a database table.
Designed to run every minute to track server performance, especially useful when onboarding new users.

Usage:
    python ec2_monitoring_script.py

The script will:
1. Connect to AWS CloudWatch to fetch EC2 metrics
2. Retrieve CPU and memory utilization for the specified instance
3. Log the data to the ec2_monitoring table in the database
4. Handle errors gracefully and log them for troubleshooting

EC2 Instance Details:
- Instance ID: i-099fb57644b0c33ba
- Instance Type: m8g.2xlarge (8 vCPUs, 32 GB RAM)
- Expected to handle ~100 new users next week
"""

import boto3
import pymysql
import json
import logging
import psutil
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple
import sys
import os

# Add the parent directory to the path to import project modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.database import get_db_connection, close_db_connection

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/home/scadreau/surgicase/tests/ec2_monitoring.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Configuration
EC2_INSTANCE_ID = "i-099fb57644b0c33ba"
AWS_REGION = "us-east-1"  # Update if your instance is in a different region
METRICS_PERIOD = 300  # 5 minutes (CloudWatch minimum for detailed monitoring)
DB_NAME = "allstars"

class EC2Monitor:
    """
    Monitor EC2 instance CPU and memory usage using AWS CloudWatch metrics.
    """
    
    def __init__(self, instance_id: str, region: str = "us-east-1"):
        """
        Initialize the EC2 monitor.
        
        Args:
            instance_id: The EC2 instance ID to monitor
            region: AWS region where the instance is located
        """
        self.instance_id = instance_id
        self.region = region
        self.cloudwatch = boto3.client('cloudwatch', region_name=region)
        self.ec2 = boto3.client('ec2', region_name=region)
        
        logger.info(f"Initialized EC2 monitor for instance {instance_id} in region {region}")
    
    def create_monitoring_table(self) -> bool:
        """
        Create the ec2_monitoring table if it doesn't exist.
        
        Returns:
            bool: True if table was created successfully or already exists
        """
        create_table_sql = """
        CREATE TABLE IF NOT EXISTS `ec2_monitoring` (
            `id` int unsigned NOT NULL AUTO_INCREMENT,
            `instance_id` varchar(50) NOT NULL,
            `timestamp` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
            `cpu_utilization_percent` decimal(5,2) DEFAULT NULL,
            `memory_utilization_percent` decimal(5,2) DEFAULT NULL,
            `network_in_bytes` bigint DEFAULT NULL,
            `network_out_bytes` bigint DEFAULT NULL,
            `disk_read_bytes` bigint DEFAULT NULL,
            `disk_write_bytes` bigint DEFAULT NULL,
            `status_check_failed` tinyint DEFAULT 0,
            `status_check_failed_instance` tinyint DEFAULT 0,
            `status_check_failed_system` tinyint DEFAULT 0,
            `notes` text DEFAULT NULL,
            `created_at` timestamp DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (`id`),
            KEY `idx_instance_timestamp` (`instance_id`, `timestamp`),
            KEY `idx_timestamp` (`timestamp`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
        """
        
        try:
            connection = get_db_connection()
            with connection.cursor() as cursor:
                cursor.execute(create_table_sql)
                connection.commit()
                logger.info("EC2 monitoring table created successfully or already exists")
                return True
        except Exception as e:
            logger.error(f"Failed to create monitoring table: {str(e)}")
            return False
        finally:
            if 'connection' in locals():
                close_db_connection(connection)
    
    def get_instance_info(self) -> Dict:
        """
        Get basic information about the EC2 instance.
        
        Returns:
            dict: Instance information including type, state, etc.
        """
        try:
            response = self.ec2.describe_instances(InstanceIds=[self.instance_id])
            if response['Reservations']:
                instance = response['Reservations'][0]['Instances'][0]
                return {
                    'instance_type': instance.get('InstanceType', 'Unknown'),
                    'state': instance.get('State', {}).get('Name', 'Unknown'),
                    'launch_time': instance.get('LaunchTime'),
                    'availability_zone': instance.get('Placement', {}).get('AvailabilityZone', 'Unknown')
                }
        except Exception as e:
            logger.error(f"Failed to get instance info: {str(e)}")
            return {}
    
    def get_cloudwatch_metric(self, metric_name: str, namespace: str = "AWS/EC2", 
                             statistic: str = "Average", unit: str = None) -> Optional[float]:
        """
        Get a CloudWatch metric value for the EC2 instance.
        
        Args:
            metric_name: The CloudWatch metric name
            namespace: The metric namespace (default: AWS/EC2)
            statistic: The statistic to retrieve (default: Average)
            unit: The metric unit filter
            
        Returns:
            float: The metric value or None if not available
        """
        try:
            end_time = datetime.utcnow()
            start_time = end_time - timedelta(minutes=10)  # Look back 10 minutes
            
            dimensions = [
                {
                    'Name': 'InstanceId',
                    'Value': self.instance_id
                }
            ]
            
            params = {
                'Namespace': namespace,
                'MetricName': metric_name,
                'Dimensions': dimensions,
                'StartTime': start_time,
                'EndTime': end_time,
                'Period': METRICS_PERIOD,
                'Statistics': [statistic]
            }
            
            if unit:
                params['Unit'] = unit
            
            response = self.cloudwatch.get_metric_statistics(**params)
            
            if response['Datapoints']:
                # Sort by timestamp and get the most recent value
                datapoints = sorted(response['Datapoints'], key=lambda x: x['Timestamp'], reverse=True)
                return round(datapoints[0][statistic], 2)
            else:
                logger.warning(f"No datapoints found for metric {metric_name}")
                return None
                
        except Exception as e:
            logger.error(f"Failed to get CloudWatch metric {metric_name}: {str(e)}")
            return None
    
    def get_memory_utilization(self) -> Optional[float]:
        """
        Get memory utilization from CloudWatch agent or fall back to system metrics.
        
        Returns:
            float: Memory utilization percentage or None if not available
        """
        # Try CloudWatch agent first
        cloudwatch_memory = self.get_cloudwatch_metric(
            metric_name="MemoryUtilization",
            namespace="CWAgent",
            statistic="Average"
        )
        
        if cloudwatch_memory is not None:
            return cloudwatch_memory
        
        # Fallback to system memory if CloudWatch agent isn't working
        try:
            import psutil
            memory = psutil.virtual_memory()
            memory_percent = memory.percent
            logger.info(f"Using system memory metrics: {memory_percent}%")
            return round(memory_percent, 2)
        except Exception as e:
            logger.warning(f"Failed to get system memory metrics: {str(e)}")
            return None
    
    def get_cpu_utilization(self) -> Optional[float]:
        """
        Get CPU utilization from CloudWatch.
        
        Returns:
            float: CPU utilization percentage or None if not available
        """
        return self.get_cloudwatch_metric(
            metric_name="CPUUtilization",
            namespace="AWS/EC2",
            statistic="Average"
        )
    
    def get_network_metrics(self) -> Tuple[Optional[float], Optional[float]]:
        """
        Get network in and out metrics.
        
        Returns:
            tuple: (network_in_bytes, network_out_bytes)
        """
        network_in = self.get_cloudwatch_metric(
            metric_name="NetworkIn",
            namespace="AWS/EC2",
            statistic="Sum",
            unit="Bytes"
        )
        
        network_out = self.get_cloudwatch_metric(
            metric_name="NetworkOut",
            namespace="AWS/EC2",
            statistic="Sum",
            unit="Bytes"
        )
        
        return network_in, network_out
    
    def get_disk_metrics(self) -> Tuple[Optional[float], Optional[float]]:
        """
        Get disk read and write metrics from CloudWatch or system metrics.
        
        Returns:
            tuple: (disk_read_bytes, disk_write_bytes)
        """
        # Try CloudWatch first
        disk_read = self.get_cloudwatch_metric(
            metric_name="DiskReadBytes",
            namespace="AWS/EC2",
            statistic="Sum",
            unit="Bytes"
        )
        
        disk_write = self.get_cloudwatch_metric(
            metric_name="DiskWriteBytes",
            namespace="AWS/EC2",
            statistic="Sum",
            unit="Bytes"
        )
        
        # If CloudWatch metrics are available, return them
        if disk_read is not None and disk_write is not None:
            return disk_read, disk_write
        
        # Fallback to system disk I/O metrics
        try:
            import psutil
            
            # Get current disk I/O counters
            disk_io = psutil.disk_io_counters()
            if disk_io:
                # Note: These are cumulative values since boot, not per-period
                # For monitoring trends, this is still useful
                disk_read_bytes = disk_io.read_bytes
                disk_write_bytes = disk_io.write_bytes
                
                logger.info(f"Using system disk I/O metrics: Read={disk_read_bytes:,} bytes, Write={disk_write_bytes:,} bytes")
                return disk_read_bytes, disk_write_bytes
            else:
                logger.warning("System disk I/O counters not available")
                return None, None
                
        except Exception as e:
            logger.warning(f"Failed to get system disk I/O metrics: {str(e)}")
            return None, None
    
    def get_status_checks(self) -> Tuple[bool, bool, bool]:
        """
        Get EC2 status check results.
        
        Returns:
            tuple: (status_check_failed, instance_check_failed, system_check_failed)
        """
        try:
            # Get status check failed metric
            status_check_failed = self.get_cloudwatch_metric(
                metric_name="StatusCheckFailed",
                namespace="AWS/EC2",
                statistic="Maximum"
            )
            
            instance_check_failed = self.get_cloudwatch_metric(
                metric_name="StatusCheckFailed_Instance",
                namespace="AWS/EC2",
                statistic="Maximum"
            )
            
            system_check_failed = self.get_cloudwatch_metric(
                metric_name="StatusCheckFailed_System",
                namespace="AWS/EC2",
                statistic="Maximum"
            )
            
            return (
                bool(status_check_failed) if status_check_failed is not None else False,
                bool(instance_check_failed) if instance_check_failed is not None else False,
                bool(system_check_failed) if system_check_failed is not None else False
            )
            
        except Exception as e:
            logger.error(f"Failed to get status checks: {str(e)}")
            return False, False, False
    
    def collect_metrics(self) -> Dict:
        """
        Collect all relevant metrics for the EC2 instance.
        
        Returns:
            dict: Dictionary containing all collected metrics
        """
        logger.info(f"Collecting metrics for instance {self.instance_id}")
        
        # Get basic metrics
        cpu_utilization = self.get_cpu_utilization()
        memory_utilization = self.get_memory_utilization()
        network_in, network_out = self.get_network_metrics()
        disk_read, disk_write = self.get_disk_metrics()
        status_failed, instance_failed, system_failed = self.get_status_checks()
        
        metrics = {
            'instance_id': self.instance_id,
            'timestamp': datetime.utcnow(),
            'cpu_utilization_percent': cpu_utilization,
            'memory_utilization_percent': memory_utilization,
            'network_in_bytes': network_in,
            'network_out_bytes': network_out,
            'disk_read_bytes': disk_read,
            'disk_write_bytes': disk_write,
            'status_check_failed': 1 if status_failed else 0,
            'status_check_failed_instance': 1 if instance_failed else 0,
            'status_check_failed_system': 1 if system_failed else 0
        }
        
        # Add notes for any concerning metrics
        notes = []
        if cpu_utilization and cpu_utilization > 80:
            notes.append(f"High CPU utilization: {cpu_utilization}%")
        if memory_utilization and memory_utilization > 80:
            notes.append(f"High memory utilization: {memory_utilization}%")
        if status_failed:
            notes.append("Status check failed")
        
        # Add disk usage information to notes
        try:
            import psutil
            disk_usage = psutil.disk_usage('/')
            disk_percent = (disk_usage.used / disk_usage.total) * 100
            if disk_percent > 80:
                notes.append(f"High disk usage: {disk_percent:.1f}%")
        except Exception as e:
            logger.debug(f"Could not get disk usage: {str(e)}")
        
        metrics['notes'] = '; '.join(notes) if notes else None
        
        logger.info(f"Metrics collected: CPU={cpu_utilization}%, Memory={memory_utilization}%")
        return metrics
    
    def save_metrics_to_db(self, metrics: Dict) -> bool:
        """
        Save collected metrics to the database.
        
        Args:
            metrics: Dictionary containing metrics to save
            
        Returns:
            bool: True if saved successfully, False otherwise
        """
        insert_sql = """
        INSERT INTO ec2_monitoring (
            instance_id, timestamp, cpu_utilization_percent, memory_utilization_percent,
            network_in_bytes, network_out_bytes, disk_read_bytes, disk_write_bytes,
            status_check_failed, status_check_failed_instance, status_check_failed_system, notes
        ) VALUES (
            %(instance_id)s, %(timestamp)s, %(cpu_utilization_percent)s, %(memory_utilization_percent)s,
            %(network_in_bytes)s, %(network_out_bytes)s, %(disk_read_bytes)s, %(disk_write_bytes)s,
            %(status_check_failed)s, %(status_check_failed_instance)s, %(status_check_failed_system)s, %(notes)s
        )
        """
        
        try:
            connection = get_db_connection()
            with connection.cursor() as cursor:
                cursor.execute(insert_sql, metrics)
                connection.commit()
                logger.info(f"Metrics saved to database for instance {metrics['instance_id']}")
                return True
        except Exception as e:
            logger.error(f"Failed to save metrics to database: {str(e)}")
            return False
        finally:
            if 'connection' in locals():
                close_db_connection(connection)
    
    def run_monitoring_cycle(self) -> bool:
        """
        Run a complete monitoring cycle: collect metrics and save to database.
        
        Returns:
            bool: True if monitoring cycle completed successfully
        """
        try:
            # Create table if it doesn't exist
            if not self.create_monitoring_table():
                return False
            
            # Collect metrics
            metrics = self.collect_metrics()
            
            # Save to database
            if self.save_metrics_to_db(metrics):
                logger.info("Monitoring cycle completed successfully")
                return True
            else:
                logger.error("Failed to save metrics during monitoring cycle")
                return False
                
        except Exception as e:
            logger.error(f"Error during monitoring cycle: {str(e)}")
            return False

def print_instance_info(monitor: EC2Monitor):
    """
    Print basic information about the EC2 instance being monitored.
    """
    info = monitor.get_instance_info()
    if info:
        print("\n" + "="*50)
        print("EC2 INSTANCE INFORMATION")
        print("="*50)
        print(f"Instance ID: {monitor.instance_id}")
        print(f"Instance Type: {info.get('instance_type', 'Unknown')}")
        print(f"Current State: {info.get('state', 'Unknown')}")
        print(f"Availability Zone: {info.get('availability_zone', 'Unknown')}")
        if info.get('launch_time'):
            print(f"Launch Time: {info['launch_time']}")
        print("="*50)
    else:
        print(f"Could not retrieve information for instance {monitor.instance_id}")

def print_latest_metrics():
    """
    Print the latest metrics from the database.
    """
    try:
        connection = get_db_connection()
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT instance_id, timestamp, cpu_utilization_percent, memory_utilization_percent,
                       network_in_bytes, network_out_bytes, disk_read_bytes, disk_write_bytes,
                       status_check_failed, notes
                FROM ec2_monitoring 
                WHERE instance_id = %s
                ORDER BY timestamp DESC 
                LIMIT 5
            """, (EC2_INSTANCE_ID,))
            
            results = cursor.fetchall()
            
            if results:
                print("\n" + "="*100)
                print("LATEST MONITORING RESULTS")
                print("="*100)
                print(f"{'Timestamp':<20} {'CPU %':<8} {'Mem %':<8} {'Net In':<10} {'Net Out':<10} {'Disk Read':<12} {'Disk Write':<12} {'Notes':<15}")
                print("-"*100)
                
                for row in results:
                    # Handle both dict and tuple formats
                    if isinstance(row, dict):
                        timestamp = row['timestamp'].strftime("%Y-%m-%d %H:%M:%S") if row['timestamp'] else "N/A"
                        cpu = f"{row['cpu_utilization_percent']:.1f}" if row['cpu_utilization_percent'] is not None else "N/A"
                        memory = f"{row['memory_utilization_percent']:.1f}" if row['memory_utilization_percent'] is not None else "N/A"
                        net_in = f"{row['network_in_bytes']//1000:,}K" if row['network_in_bytes'] is not None else "N/A"
                        net_out = f"{row['network_out_bytes']//1000:,}K" if row['network_out_bytes'] is not None else "N/A"
                        disk_read = f"{row['disk_read_bytes']//1000000:,}M" if row['disk_read_bytes'] is not None else "N/A"
                        disk_write = f"{row['disk_write_bytes']//1000000:,}M" if row['disk_write_bytes'] is not None else "N/A"
                        notes = row['notes'][:12] + "..." if row['notes'] and len(row['notes']) > 12 else (row['notes'] or "")
                    else:
                        timestamp = row[1].strftime("%Y-%m-%d %H:%M:%S") if row[1] else "N/A"
                        cpu = f"{row[2]:.1f}" if row[2] is not None else "N/A"
                        memory = f"{row[3]:.1f}" if row[3] is not None else "N/A"
                        net_in = f"{row[4]//1000:,}K" if row[4] is not None else "N/A"
                        net_out = f"{row[5]//1000:,}K" if row[5] is not None else "N/A"
                        disk_read = f"{row[6]//1000000:,}M" if row[6] is not None else "N/A"
                        disk_write = f"{row[7]//1000000:,}M" if row[7] is not None else "N/A"
                        notes = row[9][:12] + "..." if row[9] and len(row[9]) > 12 else (row[9] or "")
                    
                    print(f"{timestamp:<20} {cpu:<8} {memory:<8} {net_in:<10} {net_out:<10} {disk_read:<12} {disk_write:<12} {notes:<15}")
                print("="*100)
            else:
                print("No monitoring data found in database")
                
    except Exception as e:
        logger.error(f"Failed to retrieve latest metrics: {str(e)}")
    finally:
        if 'connection' in locals():
            close_db_connection(connection)

def main():
    """
    Main function to run the EC2 monitoring script.
    """
    print(f"Starting EC2 monitoring for instance {EC2_INSTANCE_ID}")
    print(f"Monitoring will run every minute and log to database '{DB_NAME}'")
    
    try:
        # Initialize monitor
        monitor = EC2Monitor(EC2_INSTANCE_ID, AWS_REGION)
        
        # Print instance information
        print_instance_info(monitor)
        
        # Run monitoring cycle
        success = monitor.run_monitoring_cycle()
        
        if success:
            print("\n✅ Monitoring cycle completed successfully!")
            print("📊 Checking latest metrics...")
            print_latest_metrics()
            
            print("\n📝 To run this script every minute, add this to your crontab:")
            print(f"* * * * * cd /home/scadreau/surgicase && python tests/ec2_monitoring_script.py >> tests/ec2_monitoring_cron.log 2>&1")
            
            print("\n📈 Monitor your server at:")
            print("- CPU and Memory usage will be tracked in the 'ec2_monitoring' table")
            print("- Check logs at: /home/scadreau/surgicase/tests/ec2_monitoring.log")
            print("- For m8g.2xlarge: 8 vCPUs, 32GB RAM - should handle 100+ users easily")
            
        else:
            print("\n❌ Monitoring cycle failed. Check logs for details.")
            
    except Exception as e:
        logger.error(f"Failed to run monitoring script: {str(e)}")
        print(f"\n❌ Error: {str(e)}")
        print("Please check your AWS credentials and instance ID")

if __name__ == "__main__":
    main()
