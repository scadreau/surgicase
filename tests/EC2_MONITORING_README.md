# EC2 Instance Monitoring System

This monitoring system tracks CPU and memory usage of your primary API server (EC2 instance `i-099fb57644b0c33ba`) to ensure optimal performance during user onboarding.

## Overview

- **Instance**: i-099fb57644b0c33ba (m8g.2xlarge - 8 vCPUs, 32GB RAM)
- **Frequency**: Every minute
- **Storage**: MySQL database table `ec2_monitoring`
- **Purpose**: Monitor server performance for ~100 new users onboarding next week

## Quick Start

1. **Install Dependencies**:
   ```bash
   cd /home/scadreau/surgicase/tests
   pip install -r monitoring_requirements.txt --break-system-packages
   ```

2. **Configure AWS Credentials** (if not already done):
   ```bash
   aws configure
   ```

3. **Test the System**:
   ```bash
   python test_ec2_monitoring.py
   ```

4. **Set Up Automated Monitoring**:
   ```bash
   chmod +x setup_monitoring_cron.sh
   ./setup_monitoring_cron.sh
   ```

5. **Monitor the Logs**:
   ```bash
   tail -f ec2_monitoring_cron.log
   ```

## Files Created

- `ec2_monitoring_script.py` - Main monitoring script
- `test_ec2_monitoring.py` - Test suite to verify functionality
- `setup_monitoring_cron.sh` - Script to configure cron job
- `monitoring_requirements.txt` - Python dependencies
- `EC2_MONITORING_README.md` - This documentation

## Database Schema

The monitoring data is stored in the `ec2_monitoring` table:

```sql
CREATE TABLE `ec2_monitoring` (
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
);
```

## Monitored Metrics

### Core Metrics
- **CPU Utilization** - Percentage of CPU usage
- **Memory Utilization** - Percentage of memory usage (requires CloudWatch agent)
- **Network I/O** - Bytes in/out
- **Disk I/O** - Read/write bytes
- **Status Checks** - EC2 instance and system health

### Alerting Thresholds
The script automatically adds notes when:
- CPU utilization > 80%
- Memory utilization > 80%
- Status checks fail

## Manual Monitoring

To manually run the monitoring script:
```bash
cd /home/scadreau/surgicase
python tests/ec2_monitoring_script.py
```

To view recent monitoring data:
```sql
SELECT instance_id, timestamp, cpu_utilization_percent, memory_utilization_percent, notes
FROM ec2_monitoring 
WHERE instance_id = 'i-099fb57644b0c33ba'
ORDER BY timestamp DESC 
LIMIT 10;
```

## CloudWatch Agent Setup

For memory metrics, ensure the CloudWatch agent is installed on your EC2 instance:

1. **Install CloudWatch Agent**:
   ```bash
   sudo yum install amazon-cloudwatch-agent
   ```

2. **Configure the Agent**:
   ```bash
   sudo /opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-config-wizard
   ```

3. **Start the Agent**:
   ```bash
   sudo systemctl start amazon-cloudwatch-agent
   sudo systemctl enable amazon-cloudwatch-agent
   ```

## Expected Performance

Your m8g.2xlarge instance should easily handle 100+ concurrent users:
- **8 vCPUs** - AWS Graviton3 processors
- **32GB RAM** - Ample memory for your application
- **Up to 15 Gbps network** - High bandwidth capacity

Typical healthy metrics for your workload:
- CPU: < 50% under normal load
- Memory: < 60% utilization
- Network: Varies based on user activity

## Troubleshooting

### Common Issues

1. **No Memory Metrics**:
   - Install CloudWatch agent on the EC2 instance
   - Ensure proper IAM permissions for CloudWatch

2. **AWS Credentials Error**:
   ```bash
   aws configure
   # Enter your access key, secret key, and region (us-east-1)
   ```

3. **Database Connection Failed**:
   - Check that the application can connect to the database
   - Verify database credentials in your configuration

4. **Permission Denied**:
   ```bash
   chmod +x tests/setup_monitoring_cron.sh
   chmod +x tests/ec2_monitoring_script.py
   ```

### Viewing Logs

- **Application Logs**: `tests/ec2_monitoring.log`
- **Cron Logs**: `tests/ec2_monitoring_cron.log`
- **System Logs**: `/var/log/cron` (for cron job execution)

### Checking Cron Job

```bash
# View current cron jobs
crontab -l

# Edit cron jobs
crontab -e

# View cron service status
sudo systemctl status crond
```

## Performance Impact

This monitoring system is designed to be lightweight:
- Runs once per minute (minimal frequency)
- Uses efficient AWS API calls
- Stores only essential metrics
- Minimal CPU/memory overhead

## Stopping Monitoring

To stop the automated monitoring:
```bash
crontab -e
# Remove or comment out the line containing ec2_monitoring_script.py
```

## Data Retention

Consider setting up data retention policies:
```sql
-- Delete monitoring data older than 30 days
DELETE FROM ec2_monitoring 
WHERE timestamp < DATE_SUB(NOW(), INTERVAL 30 DAY);
```

## Contact

For issues with this monitoring system, check:
1. Test script output: `python tests/test_ec2_monitoring.py`
2. Application logs: `tail -f tests/ec2_monitoring.log`
3. Cron logs: `tail -f tests/ec2_monitoring_cron.log`

---

**Important**: This monitoring system is crucial for ensuring server stability during the upcoming user onboarding. Monitor the logs regularly and watch for any alerts about high resource usage.
