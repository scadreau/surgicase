# Created: 2025-01-27 10:25:15
# Last Modified: 2025-07-28 18:46:08

# SurgiCase Horizontal Scaling Guide
## Comprehensive Guide for Scaling the SurgiCase Management System

This guide provides step-by-step instructions for horizontally scaling the SurgiCase system across multiple servers while maintaining performance, reliability, and monitoring coverage.

## 🏗️ Architecture Overview

### Current Infrastructure
- **Main SurgiCase Server**: `172.31.38.136` (private) - Primary application instance
- **Monitoring Server**: `172.31.86.18` (private) / `3.83.225.230` (public) - Dedicated monitoring
- **VPC**: `vpc-0d0a4d7473692be39`
- **Security Group**: `sg-06718ecd804840607`

### Scaling Architecture
```
                    ┌─────────────────┐
                    │   Load Balancer │
                    │   (ALB/NLB)     │
                    └─────────┬───────┘
                              │
            ┌─────────────────┼─────────────────┐
            │                 │                 │
    ┌───────▼──────┐ ┌───────▼──────┐ ┌───────▼──────┐
    │ SurgiCase-1  │ │ SurgiCase-2  │ │ SurgiCase-N  │
    │ 172.31.38.136│ │ 172.31.x.x   │ │ 172.31.y.y   │
    │    :8000     │ │    :8000     │ │    :8000     │
    └──────────────┘ └──────────────┘ └──────────────┘
            │                 │                 │
            └─────────────────┼─────────────────┘
                              │
                    ┌─────────▼───────┐
                    │   Monitoring    │
                    │  172.31.86.18   │
                    │ Prometheus/Graf │
                    └─────────────────┘
```

---

## 🚀 Phase 1: Prerequisites & Planning

### Infrastructure Requirements

#### New Server Specifications
**Minimum Requirements per Instance:**
- **Instance Type**: t3.large or larger (2 vCPU, 8GB RAM)
- **Storage**: 100GB+ SSD
- **OS**: Ubuntu 24.04.2 LTS
- **Network**: Same VPC (`vpc-0d0a4d7473692be39`)
- **Security Groups**: Same as main server (`sg-06718ecd804840607`)

#### Database Considerations
- **Current**: Single MySQL instance
- **Scaling Options**:
  - **Read Replicas**: For read-heavy workloads
  - **Connection Pooling**: Increase max_connections
  - **Database Proxy**: RDS Proxy for connection management
  - **Sharding**: For extreme scale (future consideration)

#### Shared Services
- **S3 Storage**: Shared across all instances
- **AWS Secrets Manager**: Shared configuration
- **Monitoring**: Single monitoring server scales to ~50 instances

### Capacity Planning
```bash
# Calculate required instances based on load
# Current capacity: ~100 concurrent users per instance
# Target load: X users → X/100 instances (rounded up)

# Example: 500 concurrent users
# Required instances: ceil(500/100) = 5 instances
```

---

## 🖥️ Phase 2: Server Deployment

### 1. Launch New EC2 Instance

```bash
# AWS CLI command for new instance
aws ec2 run-instances \
    --image-id ami-0e86e20dae90b7e23 \
    --instance-type t3.large \
    --key-name Metoray1 \
    --security-group-ids sg-06718ecd804840607 \
    --subnet-id subnet-xxxxxxxx \
    --user-data file://user-data.sh \
    --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=SurgiCase-Instance-2},{Key=Environment,Value=production},{Key=Role,Value=api-server}]'
```

### 2. Server Setup Automation

Create `user-data.sh` for automated setup:
```bash
#!/bin/bash
# SurgiCase Instance Setup Script

# Update system
apt update && apt upgrade -y

# Install Python and dependencies
apt install -y python3 python3-pip python3-venv git mysql-client

# Create application user
useradd --create-home --shell /bin/bash surgicase
usermod -aG sudo surgicase

# Create application directory
mkdir -p /opt/surgicase
chown surgicase:surgicase /opt/surgicase

# Install AWS CLI
curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
unzip awscliv2.zip
./aws/install

# Clone repository (replace with your method)
sudo -u surgicase git clone <your-repo-url> /opt/surgicase/app
cd /opt/surgicase/app

# Create virtual environment
sudo -u surgicase python3 -m venv /opt/surgicase/venv
sudo -u surgicase /opt/surgicase/venv/bin/pip install -r requirements.txt

# Create systemd service
cp deployment/surgicase.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable surgicase
```

### 3. Manual Setup Steps

```bash
# SSH into new instance
ssh -i ~/.ssh/Metoray1.pem ubuntu@<NEW_INSTANCE_IP>

# Switch to application user
sudo su - surgicase

# Navigate to application
cd /opt/surgicase/app

# Test application
python main.py

# Verify health endpoint
curl http://localhost:8000/health

# Test database connectivity
curl http://localhost:8000/health | jq '.database'
```

---

## 📊 Phase 3: Monitoring Integration

### 1. Register Instance with Monitoring

```bash
# SSH into monitoring server
ssh -i ~/.ssh/Metoray1.pem scadreau@3.83.225.230

# Register new instance (replace with actual private IP)
sudo /opt/register-instance.sh 172.31.50.100 8000 production

# Verify registration
curl -s http://localhost:9090/api/v1/targets | jq '.data.activeTargets[] | select(.labels.job=="surgicase-api-cluster")'
```

### 2. Verify Monitoring Data

```bash
# Check metrics collection
curl 'http://localhost:9090/api/v1/query?query=up{job="surgicase-api-cluster"}'

# Verify all instances are being scraped
curl 'http://localhost:9090/api/v1/query?query=http_requests_total'

# Check instance health across all servers
curl 'http://localhost:9090/api/v1/query?query=fastapi_app_info'
```

### 3. Update Grafana Dashboards

```bash
# Access Grafana at http://3.83.225.230:3000
# Login: admin / SurgiCase2025!

# Update dashboard queries to include new instances:
# OLD: {job="surgicase-api"}
# NEW: {job=~"surgicase-api.*"}
```

---

## ⚖️ Phase 4: Load Balancer Configuration

### Application Load Balancer (ALB) Setup

#### 1. Create Target Group
```bash
# Create target group
aws elbv2 create-target-group \
    --name surgicase-api-targets \
    --protocol HTTP \
    --port 8000 \
    --vpc-id vpc-0d0a4d7473692be39 \
    --health-check-path /health/ready \
    --health-check-interval-seconds 30 \
    --healthy-threshold-count 2 \
    --unhealthy-threshold-count 3
```

#### 2. Register Targets
```bash
# Register all SurgiCase instances
aws elbv2 register-targets \
    --target-group-arn arn:aws:elasticloadbalancing:region:account:targetgroup/surgicase-api-targets/xyz \
    --targets Id=i-1234567890abcdef0 Id=i-0987654321fedcba0
```

#### 3. Create Load Balancer
```bash
# Create ALB
aws elbv2 create-load-balancer \
    --name surgicase-api-alb \
    --subnets subnet-xxxxxxxx subnet-yyyyyyyy \
    --security-groups sg-06718ecd804840607 \
    --scheme internet-facing \
    --type application \
    --ip-address-type ipv4
```

#### 4. Create Listener
```bash
# Create HTTP listener
aws elbv2 create-listener \
    --load-balancer-arn arn:aws:elasticloadbalancing:region:account:loadbalancer/app/surgicase-api-alb/xyz \
    --protocol HTTP \
    --port 80 \
    --default-actions Type=forward,TargetGroupArn=arn:aws:elasticloadbalancing:region:account:targetgroup/surgicase-api-targets/xyz
```

### Health Check Configuration
```json
{
  "Protocol": "HTTP",
  "Port": "8000",
  "Path": "/health/ready",
  "IntervalSeconds": 30,
  "TimeoutSeconds": 5,
  "HealthyThresholdCount": 2,
  "UnhealthyThresholdCount": 3,
  "Matcher": {
    "HttpCode": "200"
  }
}
```

---

## 🔧 Phase 5: Session Management & State

### Stateless Design Verification

#### Current Stateless Features ✅
- No server-side sessions
- Database-backed user state
- S3-based file storage
- Stateless authentication (user_id parameter)

#### Ensure Stateless Operation
```python
# Verify no in-memory state dependencies
# Check main.py and endpoints for:
# ❌ Global variables storing user data
# ❌ In-memory caches without expiration
# ❌ File system dependencies
# ✅ Database-backed operations
# ✅ S3-based file storage
```

### Sticky Sessions (if needed)
```bash
# If sticky sessions become necessary, configure ALB:
aws elbv2 modify-target-group-attributes \
    --target-group-arn arn:aws:elasticloadbalancing:region:account:targetgroup/surgicase-api-targets/xyz \
    --attributes Key=stickiness.enabled,Value=true Key=stickiness.type,Value=lb_cookie Key=stickiness.lb_cookie.duration_seconds,Value=86400
```

---

## 💾 Phase 6: Database Scaling

### Read Replica Setup (Optional)
```bash
# Create read replica for read-heavy workloads
aws rds create-db-instance-read-replica \
    --db-instance-identifier surgicase-read-replica \
    --source-db-instance-identifier surgicase-main \
    --db-instance-class db.t3.medium
```

### Connection Pool Tuning
```python
# Update database.py connection settings
SQLALCHEMY_DATABASE_URL = "mysql+pymysql://user:pass@host:3306/db?charset=utf8mb4"

# Connection pool settings for multiple instances
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    pool_size=10,          # Connections per instance
    max_overflow=20,       # Additional connections
    pool_timeout=30,       # Connection timeout
    pool_recycle=3600,     # Recycle connections hourly
    pool_pre_ping=True     # Validate connections
)
```

### Database Configuration Updates
```sql
-- Increase max_connections for multiple instances
-- Current: ~100 connections per instance
-- 5 instances × 30 connections = 150 + buffer = 200
SET GLOBAL max_connections = 200;

-- Optimize for multiple connections
SET GLOBAL innodb_buffer_pool_size = '70%';  -- Adjust based on RDS instance
SET GLOBAL query_cache_size = 256MB;
```

---

## 🚨 Phase 7: Monitoring & Alerting

### Instance Health Monitoring

#### Prometheus Alerts
Create `/etc/prometheus/alerts.yml` on monitoring server:
```yaml
groups:
  - name: surgicase-scaling
    rules:
      - alert: InstanceDown
        expr: up{job=~"surgicase-api.*"} == 0
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "SurgiCase instance {{ $labels.instance }} is down"
          description: "Instance {{ $labels.instance }} has been down for more than 1 minute"

      - alert: HighCPUUsage
        expr: (100 - (avg(irate(node_cpu_seconds_total{mode="idle"}[5m])) * 100)) > 80
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High CPU usage on {{ $labels.instance }}"

      - alert: HighMemoryUsage
        expr: (1 - (node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)) * 100 > 85
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High memory usage on {{ $labels.instance }}"

      - alert: DatabaseConnectionsHigh
        expr: mysql_global_status_threads_connected > 80
        for: 2m
        labels:
          severity: warning
        annotations:
          summary: "High database connections"
          description: "Database has {{ $value }} active connections"
```

#### Load Balancer Monitoring
```bash
# Monitor ALB target health
aws elbv2 describe-target-health \
    --target-group-arn arn:aws:elasticloadbalancing:region:account:targetgroup/surgicase-api-targets/xyz

# Monitor ALB metrics via CloudWatch
aws logs create-log-group --log-group-name /aws/loadbalancer/surgicase-api-alb
```

---

## 🔄 Phase 8: Deployment & Rolling Updates

### Blue-Green Deployment Strategy

#### 1. Prepare New Version
```bash
# On each instance, prepare new version
cd /opt/surgicase/app
git fetch origin
git checkout v0.9.0  # New version tag

# Install dependencies
/opt/surgicase/venv/bin/pip install -r requirements.txt
```

#### 2. Rolling Update Process
```bash
# Update instances one at a time
for instance in instance-1 instance-2 instance-3; do
    echo "Updating $instance"
    
    # Remove from load balancer
    aws elbv2 deregister-targets \
        --target-group-arn $TARGET_GROUP_ARN \
        --targets Id=$instance
    
    # Wait for connections to drain
    sleep 60
    
    # Update application
    ssh $instance "sudo systemctl restart surgicase"
    
    # Verify health
    while ! curl -s http://$instance:8000/health | grep -q "healthy"; do
        sleep 10
    done
    
    # Re-register with load balancer
    aws elbv2 register-targets \
        --target-group-arn $TARGET_GROUP_ARN \
        --targets Id=$instance
    
    # Wait for health check
    sleep 60
    
    echo "$instance updated successfully"
done
```

### Canary Deployment (Advanced)
```bash
# Deploy to subset of instances first
# Monitor metrics and error rates
# Proceed with full deployment if successful

# Example: Deploy to 1 instance, monitor for 15 minutes
# If error_rate < 1% and response_time < 500ms, continue
```

---

## 📊 Phase 9: Performance Optimization

### Instance Performance Tuning

#### Application-Level Optimizations
```python
# Optimize FastAPI settings in main.py
from fastapi import FastAPI
from uvicorn import run

app = FastAPI(
    title="SurgiCase API",
    docs_url="/docs" if ENV != "production" else None,  # Disable docs in prod
    redoc_url=None if ENV == "production" else "/redoc"
)

# Production server settings
if __name__ == "__main__":
    run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        workers=4,                    # CPU cores × 2
        worker_class="uvicorn.workers.UvicornWorker",
        worker_connections=1000,      # Connections per worker
        max_requests=1000,           # Restart workers after N requests
        max_requests_jitter=100,     # Add randomness to restart
        timeout_keep_alive=2,        # Keep-alive timeout
        access_log=False            # Disable access logs for performance
    )
```

#### System-Level Optimizations
```bash
# Optimize system settings for high load
echo "net.core.somaxconn = 65535" >> /etc/sysctl.conf
echo "net.core.netdev_max_backlog = 5000" >> /etc/sysctl.conf
echo "net.ipv4.tcp_max_syn_backlog = 65535" >> /etc/sysctl.conf
sysctl -p

# Optimize file descriptors
echo "* soft nofile 65535" >> /etc/security/limits.conf
echo "* hard nofile 65535" >> /etc/security/limits.conf

# Optimize systemd service
cat > /etc/systemd/system/surgicase.service << EOF
[Unit]
Description=SurgiCase API Service
After=network.target

[Service]
Type=simple
User=surgicase
Group=surgicase
WorkingDirectory=/opt/surgicase/app
Environment=ENABLE_SCHEDULER=false
Environment=PYTHONPATH=/opt/surgicase/app
ExecStart=/opt/surgicase/venv/bin/python main.py
Restart=always
RestartSec=3
LimitNOFILE=65535
KillMode=mixed
KillSignal=SIGTERM
TimeoutStopSec=30

[Install]
WantedBy=multi-user.target
EOF
```

### Database Optimization
```sql
-- Optimize queries for multiple instances
-- Add indexes for common queries
CREATE INDEX idx_cases_user_status ON cases(user_id, case_status);
CREATE INDEX idx_cases_created_date ON cases(created_date);
CREATE INDEX idx_user_profile_npi ON user_profile(npi_number);

-- Analyze table statistics
ANALYZE TABLE cases, user_profile, facilities, surgeons;
```

---

## 🛡️ Phase 10: Security & Compliance

### Network Security
```bash
# Update security group for new instances
aws ec2 authorize-security-group-ingress \
    --group-id sg-06718ecd804840607 \
    --protocol tcp \
    --port 8000 \
    --source-group sg-ALB_SECURITY_GROUP

# Restrict direct access to instances
aws ec2 revoke-security-group-ingress \
    --group-id sg-06718ecd804840607 \
    --protocol tcp \
    --port 8000 \
    --cidr 0.0.0.0/0
```

### SSL/TLS Configuration
```bash
# Configure SSL termination at ALB
aws elbv2 create-listener \
    --load-balancer-arn $ALB_ARN \
    --protocol HTTPS \
    --port 443 \
    --certificates CertificateArn=$SSL_CERT_ARN \
    --default-actions Type=forward,TargetGroupArn=$TARGET_GROUP_ARN

# Force HTTPS redirect
aws elbv2 create-listener \
    --load-balancer-arn $ALB_ARN \
    --protocol HTTP \
    --port 80 \
    --default-actions Type=redirect,RedirectConfig='{Protocol=HTTPS,Port=443,StatusCode=HTTP_301}'
```

---

## 📈 Phase 11: Capacity Planning & Auto Scaling

### Auto Scaling Group (Optional)
```bash
# Create launch template
aws ec2 create-launch-template \
    --launch-template-name surgicase-template \
    --launch-template-data file://launch-template.json

# Create auto scaling group
aws autoscaling create-auto-scaling-group \
    --auto-scaling-group-name surgicase-asg \
    --launch-template LaunchTemplateName=surgicase-template,Version=1 \
    --min-size 2 \
    --max-size 10 \
    --desired-capacity 3 \
    --target-group-arns $TARGET_GROUP_ARN \
    --vpc-zone-identifier "subnet-xxxxxxxx,subnet-yyyyyyyy"
```

### Scaling Policies
```bash
# Scale up policy
aws autoscaling put-scaling-policy \
    --auto-scaling-group-name surgicase-asg \
    --policy-name scale-up \
    --scaling-adjustment 1 \
    --adjustment-type ChangeInCapacity \
    --cooldown 300

# Scale down policy
aws autoscaling put-scaling-policy \
    --auto-scaling-group-name surgicase-asg \
    --policy-name scale-down \
    --scaling-adjustment -1 \
    --adjustment-type ChangeInCapacity \
    --cooldown 300
```

### CloudWatch Alarms
```bash
# CPU-based scaling
aws cloudwatch put-metric-alarm \
    --alarm-name surgicase-cpu-high \
    --alarm-description "Scale up on high CPU" \
    --metric-name CPUUtilization \
    --namespace AWS/EC2 \
    --statistic Average \
    --period 300 \
    --threshold 70 \
    --comparison-operator GreaterThanThreshold \
    --evaluation-periods 2 \
    --alarm-actions $SCALE_UP_POLICY_ARN
```

---

## 🔍 Phase 12: Testing & Validation

### Load Testing
```bash
# Install load testing tools
pip install locust

# Create load test script
cat > locustfile.py << EOF
from locust import HttpUser, task, between

class SurgiCaseUser(HttpUser):
    wait_time = between(1, 3)
    
    def on_start(self):
        self.user_id = 1  # Test user ID
    
    @task(3)
    def health_check(self):
        self.client.get("/health")
    
    @task(2)
    def get_cases(self):
        self.client.get(f"/casefilter?user_id={self.user_id}&status=10")
    
    @task(1)
    def get_facilities(self):
        self.client.get(f"/facilities?user_id={self.user_id}")

    @task(1)
    def metrics_check(self):
        self.client.get("/metrics")
EOF

# Run load test
locust --host=http://your-alb-url.amazonaws.com -u 100 -r 10 --headless -t 300s
```

### Integration Testing
```bash
# Test all instances through load balancer
for i in {1..10}; do
    response=$(curl -s -w "%{http_code}" http://your-alb-url.amazonaws.com/health)
    echo "Request $i: $response"
done

# Test monitoring coverage
curl 'http://3.83.225.230:9090/api/v1/query?query=up{job=~"surgicase-api.*"}' | jq '.data.result[].value[1]'

# Test database connectivity from all instances
for instance in $INSTANCE_LIST; do
    ssh $instance "curl -s http://localhost:8000/health | jq '.database.status'"
done
```

---

## 📚 Phase 13: Operations & Maintenance

### Daily Operations
```bash
#!/bin/bash
# daily-health-check.sh

echo "=== Daily SurgiCase Health Check ==="
echo "Date: $(date)"

# Check all instances
echo "Checking instance health..."
for instance in $(aws ec2 describe-instances --filters "Name=tag:Role,Values=api-server" --query 'Reservations[].Instances[].PrivateIpAddress' --output text); do
    status=$(curl -s http://$instance:8000/health | jq -r '.status')
    echo "Instance $instance: $status"
done

# Check load balancer health
echo "Checking load balancer targets..."
aws elbv2 describe-target-health --target-group-arn $TARGET_GROUP_ARN

# Check monitoring
echo "Checking monitoring coverage..."
up_instances=$(curl -s 'http://3.83.225.230:9090/api/v1/query?query=up{job=~"surgicase-api.*"}' | jq '.data.result | length')
echo "Monitored instances: $up_instances"

# Check database connections
echo "Database connection count:"
curl -s 'http://3.83.225.230:9090/api/v1/query?query=mysql_global_status_threads_connected' | jq '.data.result[0].value[1]'
```

### Backup & Recovery
```bash
# Database backup (existing procedure)
# S3 backup is automatic
# Configuration backup
aws s3 cp /etc/prometheus/prometheus.yml s3://your-backup-bucket/monitoring/
aws s3 cp /etc/grafana/grafana.ini s3://your-backup-bucket/monitoring/
```

### Incident Response
1. **Instance Failure**: Load balancer automatically routes around failed instances
2. **Database Issues**: Check connection pool, consider read replica
3. **High Load**: Monitor metrics, consider manual scaling
4. **Monitoring Alerts**: Check Grafana dashboards, investigate root cause

---

## 🎯 Success Criteria

### Scaling Checklist
- [ ] **New instances deployed** and healthy
- [ ] **Load balancer configured** with health checks
- [ ] **Monitoring integration** complete for all instances
- [ ] **Database optimization** completed
- [ ] **SSL/TLS termination** configured
- [ ] **Load testing** passed (target: <500ms response time, <1% error rate)
- [ ] **Rolling deployment** process tested
- [ ] **Auto-scaling policies** configured (if applicable)
- [ ] **Operational procedures** documented and tested

### Performance Targets
- **Response Time**: <500ms (95th percentile)
- **Availability**: >99.9% uptime
- **Error Rate**: <1% under normal load
- **Throughput**: 1000+ requests/minute per instance
- **Database Connections**: <80% of max_connections

### Monitoring Coverage
- All instances visible in Prometheus targets
- Grafana dashboards updated for multiple instances
- Alerts configured for instance failures
- Load balancer health monitoring active

---

## 🚀 Quick Reference Commands

### Instance Management
```bash
# Add new instance to monitoring
sudo /opt/register-instance.sh <private_ip> 8000 production

# Check all instance health
for ip in 172.31.38.136 172.31.50.100 172.31.60.200; do
    curl -s http://$ip:8000/health | jq '.status'
done

# Restart service on all instances
ansible all -i hosts -m systemd -a "name=surgicase state=restarted" --become
```

### Monitoring Commands
```bash
# Check Prometheus targets
curl -s http://3.83.225.230:9090/api/v1/targets | jq '.data.activeTargets[] | {job: .labels.job, health: .health}'

# Query metrics across all instances
curl 'http://3.83.225.230:9090/api/v1/query?query=http_requests_total' | jq '.data.result'

# Check load balancer targets
aws elbv2 describe-target-health --target-group-arn $TARGET_GROUP_ARN
```

### Load Balancer Management
```bash
# Add instance to load balancer
aws elbv2 register-targets --target-group-arn $TARGET_GROUP_ARN --targets Id=i-1234567890abcdef0

# Remove instance from load balancer
aws elbv2 deregister-targets --target-group-arn $TARGET_GROUP_ARN --targets Id=i-1234567890abcdef0

# Check target health
aws elbv2 describe-target-health --target-group-arn $TARGET_GROUP_ARN
```

---

**Estimated Implementation Time**: 1-2 days for 3-5 instances  
**Prerequisites**: Monitoring infrastructure, database optimization, load balancer setup  
**Complexity**: Intermediate to Advanced 