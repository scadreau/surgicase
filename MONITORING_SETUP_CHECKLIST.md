# Created: 2025-07-28 16:25:46
# Last Modified: 2025-07-28 18:41:32

# SurgiCase Monitoring Setup Checklist
## Dedicated Server Implementation with Horizontal Scaling Support

This checklist guides you through setting up Prometheus, Grafana, and Loki monitoring stack on a **dedicated m8g.xlarge server** with future horizontal scaling capabilities.

## 🖥️ **Server Configuration**
- **Monitoring Server**: `172.31.86.18` (private) / `3.83.225.230` (public)
- **Main SurgiCase Server**: `172.31.38.136` (private)
- **Instance Type**: m8g.xlarge (4 vCPU, 16GB RAM, 256GB storage)
- **OS**: Ubuntu 24.04.2 LTS
- **User**: scadreau (sudo enabled)
- **SSH Key**: Metoray1
- **VPC**: vpc-0d0a4d7473692be39
- **Security Group**: sg-06718ecd804840607

---

## ✅ Phase 1: Server Prerequisites & Package Installation

### System Requirements ✅
- [x] **Operating System**: Ubuntu 24.04.2 LTS ✅
- [x] **RAM**: 16GB ✅ 
- [x] **Disk Space**: 256GB ✅
- [x] **Network**: Ports 3000, 9090, 3100 ✅

### Connect to Your Monitoring Server
```bash
# SSH into your monitoring server
ssh -i ~/.ssh/Metoray1.pem scadreau@3.83.225.230

# Verify you can reach the main SurgiCase server
ping 172.31.38.136
curl http://172.31.38.136:8000/health
```

### Essential Packages Installation
```bash
# Update system packages
sudo apt update && sudo apt upgrade -y

# Install required system packages
sudo apt install -y wget curl unzip tar systemd

# Install process monitoring tools
sudo apt install -y htop iotop net-tools

# Create monitoring user accounts
sudo useradd --no-create-home --shell /bin/false prometheus
sudo useradd --no-create-home --shell /bin/false loki
sudo useradd --no-create-home --shell /bin/false promtail
```

### Security Group Configuration
**On AWS Console - Update Security Group: `sg-06718ecd804840607`**

**Inbound Rules to Add:**
```
Type: Custom TCP, Port: 3000, Source: 0.0.0.0/0, Description: Grafana UI
Type: Custom TCP, Port: 9090, Source: 0.0.0.0/0, Description: Prometheus UI  
Type: Custom TCP, Port: 3100, Source: 172.31.38.136/32, Description: Loki from SurgiCase
Type: SSH, Port: 22, Source: Your IP, Description: SSH Access
```

**Main SurgiCase Server Security Group** - Add this rule:
```
Type: Custom TCP, Port: 8000, Source: 172.31.86.18/32, Description: Monitoring scrape
```

---

## ✅ Phase 2: Prometheus Installation & Configuration

### Download & Install Prometheus
```bash
# Create directories
sudo mkdir -p /opt/prometheus /etc/prometheus /var/lib/prometheus

# Download latest Prometheus
cd /tmp
wget https://github.com/prometheus/prometheus/releases/download/v2.48.0/prometheus-2.48.0.linux-amd64.tar.gz
tar xvf prometheus-2.48.0.linux-amd64.tar.gz

# Install Prometheus
sudo cp prometheus-2.48.0.linux-amd64/prometheus /opt/prometheus/
sudo cp prometheus-2.48.0.linux-amd64/promtool /opt/prometheus/
sudo cp -r prometheus-2.48.0.linux-amd64/consoles /opt/prometheus/
sudo cp -r prometheus-2.48.0.linux-amd64/console_libraries /opt/prometheus/

# Set permissions
sudo chown -R prometheus:prometheus /opt/prometheus /var/lib/prometheus
sudo chmod +x /opt/prometheus/prometheus /opt/prometheus/promtool
```

### Configure Prometheus for Remote Monitoring
```bash
# Create Prometheus configuration
sudo tee /etc/prometheus/prometheus.yml << EOF
global:
  scrape_interval: 15s
  evaluation_interval: 15s
  external_labels:
    cluster: 'surgicase-main'
    environment: 'production'
    monitoring_server: '172.31.86.18'

rule_files:
  - "/etc/prometheus/alerts.yml"

# Scrape configurations
scrape_configs:
  # Main SurgiCase API server
  - job_name: 'surgicase-api'
    static_configs:
      - targets: ['172.31.38.136:8000']
    metrics_path: '/metrics'
    scrape_interval: 15s
    scrape_timeout: 10s
    
  # Future: Service discovery for multiple instances
  - job_name: 'surgicase-api-cluster'
    file_sd_configs:
      - files:
          - '/etc/prometheus/targets/*.yml'
        refresh_interval: 30s
    metrics_path: '/metrics'
    scrape_interval: 15s

  # Prometheus monitoring itself
  - job_name: 'prometheus'
    static_configs:
      - targets: ['localhost:9090']

  # Future: Federation for multi-cluster setup
  # - job_name: 'federate'
  #   scrape_interval: 15s
  #   honor_labels: true
  #   metrics_path: '/federate'
  #   params:
  #     'match[]':
  #       - '{job=~"surgicase.*"}'
  #   static_configs:
  #     - targets:
  #       - 'prometheus-secondary:9090'
EOF

# Set permissions
sudo chown prometheus:prometheus /etc/prometheus/prometheus.yml
```

### Create Systemd Service
```bash
# Create service file
sudo tee /etc/systemd/system/prometheus.service << EOF
[Unit]
Description=Prometheus Server
Documentation=https://prometheus.io/docs/
After=network-online.target

[Service]
User=prometheus
Group=prometheus
Type=simple
Restart=on-failure
ExecStart=/opt/prometheus/prometheus \\
  --config.file=/etc/prometheus/prometheus.yml \\
  --storage.tsdb.path=/var/lib/prometheus/ \\
  --storage.tsdb.retention.time=90d \\
  --storage.tsdb.retention.size=10GB \\
  --web.console.templates=/opt/prometheus/consoles \\
  --web.console.libraries=/opt/prometheus/console_libraries \\
  --web.listen-address=0.0.0.0:9090 \\
  --web.max-connections=512 \\
  --web.enable-lifecycle

[Install]
WantedBy=multi-user.target
EOF
```

### Create Target Discovery Directory for Scaling
```bash
# Create directory for dynamic service discovery
sudo mkdir -p /etc/prometheus/targets
sudo chown prometheus:prometheus /etc/prometheus/targets

# Create initial target file for future scaling
sudo tee /etc/prometheus/targets/surgicase-instances.yml << EOF
# Dynamic targets for horizontal scaling
# Format: - targets: ['172.31.x.x:8000', '172.31.y.y:8000']
#         labels:
#           cluster: 'surgicase'
#           environment: 'production'
[]
EOF
```

---

## ✅ Phase 3: Grafana Installation & Configuration

### Install Grafana from Official Repository
```bash
# Add Grafana APT repository
sudo apt-get install -y software-properties-common
wget -q -O - https://packages.grafana.com/gpg.key | sudo apt-key add -
echo "deb https://packages.grafana.com/oss/deb stable main" | sudo tee -a /etc/apt/sources.list.d/grafana.list

# Install Grafana
sudo apt-get update
sudo apt-get install grafana

# Create configuration directories
sudo mkdir -p /etc/grafana/provisioning/dashboards
sudo mkdir -p /etc/grafana/provisioning/datasources
```

### Configure Grafana for Production & Remote Access
```bash
# Backup original config
sudo cp /etc/grafana/grafana.ini /etc/grafana/grafana.ini.backup

# Configure for production access
sudo tee -a /etc/grafana/grafana.ini << EOF

[server]
http_port = 3000
domain = 3.83.225.230
root_url = http://3.83.225.230:3000/

[database]
type = sqlite3
path = grafana.db

# For future scaling with external database:
# type = mysql
# host = 127.0.0.1:3306
# name = grafana
# user = grafana
# password = your_password

[security]
admin_user = admin
admin_password = SurgiCase2025!

[users]
allow_sign_up = false

[auth.anonymous]
enabled = false

[alerting]
enabled = true

[unified_alerting]
enabled = true
EOF
```

### Copy SurgiCase Dashboard Configurations
```bash
# Transfer configurations from your local project to server
# On your local machine (Windows):
scp -i ~/.ssh/Metoray1.pem monitoring/grafana/provisioning/datasources/datasource.yml scadreau@3.83.225.230:/tmp/
scp -i ~/.ssh/Metoray1.pem monitoring/grafana/provisioning/dashboards/dashboard.yml scadreau@3.83.225.230:/tmp/
scp -i ~/.ssh/Metoray1.pem monitoring/grafana/dashboards/surgicase-overview.json scadreau@3.83.225.230:/tmp/

# On the monitoring server:
sudo cp /tmp/datasource.yml /etc/grafana/provisioning/datasources/
sudo cp /tmp/dashboard.yml /etc/grafana/provisioning/dashboards/
sudo cp /tmp/surgicase-overview.json /etc/grafana/provisioning/dashboards/
sudo chown -R grafana:grafana /etc/grafana/provisioning/
```

---

## ✅ Phase 4: Loki Installation & Configuration

### Install Loki
```bash
# Download and install Loki
cd /tmp
wget https://github.com/grafana/loki/releases/download/v2.9.0/loki-linux-amd64.zip
unzip loki-linux-amd64.zip

# Install Loki
sudo cp loki-linux-amd64 /opt/loki
sudo chmod +x /opt/loki

# Create directories
sudo mkdir -p /etc/loki /var/lib/loki
sudo chown -R loki:loki /var/lib/loki
```

### Configure Loki for Remote Log Collection
```bash
# Create production Loki config
sudo tee /etc/loki/loki.yml << EOF
auth_enabled: false

server:
  http_listen_port: 3100
  grpc_listen_port: 9095

common:
  path_prefix: /var/lib/loki
  storage:
    filesystem:
      chunks_directory: /var/lib/loki/chunks
      rules_directory: /var/lib/loki/rules
  replication_factor: 1
  ring:
    instance_addr: 172.31.86.18
    kvstore:
      store: inmemory

query_range:
  results_cache:
    cache:
      embedded_cache:
        enabled: true
        max_size_mb: 100

schema_config:
  configs:
    - from: 2020-10-24
      store: boltdb-shipper
      object_store: filesystem
      schema: v11
      index:
        prefix: index_
        period: 24h

ruler:
  alertmanager_url: http://localhost:9093

limits_config:
  reject_old_samples: true
  reject_old_samples_max_age: 168h
  ingestion_rate_mb: 16
  ingestion_burst_size_mb: 32

chunk_store_config:
  max_look_back_period: 0s

table_manager:
  retention_deletes_enabled: true
  retention_period: 168h
EOF
```

### Create Loki Systemd Service
```bash
sudo tee /etc/systemd/system/loki.service << EOF
[Unit]
Description=Loki log aggregation system
After=network.target

[Service]
User=loki
Group=loki
Type=simple
ExecStart=/opt/loki -config.file=/etc/loki/loki.yml
Restart=on-failure

[Install]
WantedBy=multi-user.target
EOF
```

---

## ✅ Phase 5: Promtail Installation & Configuration

### Install Promtail
```bash
# Download Promtail
cd /tmp
wget https://github.com/grafana/loki/releases/download/v2.9.0/promtail-linux-amd64.zip
unzip promtail-linux-amd64.zip

# Install Promtail
sudo cp promtail-linux-amd64 /opt/promtail
sudo chmod +x /opt/promtail

# Create config directory
sudo mkdir -p /etc/promtail
```

### Configure Promtail for Local and Remote Logs
```bash
sudo tee /etc/promtail/promtail.yml << EOF
server:
  http_listen_port: 9080
  grpc_listen_port: 0

positions:
  filename: /var/lib/promtail/positions.yaml

clients:
  - url: http://localhost:3100/loki/api/v1/push

scrape_configs:
  # Local system logs
  - job_name: system
    static_configs:
      - targets:
          - localhost
        labels:
          job: syslog
          server: monitoring
          __path__: /var/log/syslog

  # Future: SurgiCase application logs (when centralized)
  # - job_name: surgicase
  #   static_configs:
  #     - targets:
  #         - localhost
  #       labels:
  #         job: surgicase
  #         server: main
  #         __path__: /var/log/surgicase/*.log
EOF

# Create promtail user and directories
sudo useradd --no-create-home --shell /bin/false promtail
sudo mkdir -p /var/lib/promtail
sudo chown -R promtail:promtail /var/lib/promtail
```

### Create Promtail Systemd Service
```bash
sudo tee /etc/systemd/system/promtail.service << EOF
[Unit]
Description=Promtail log collector
After=network.target

[Service]
User=promtail
Group=promtail
Type=simple
ExecStart=/opt/promtail -config.file=/etc/promtail/promtail.yml
Restart=on-failure

[Install]
WantedBy=multi-user.target
EOF
```

---

## ✅ Phase 6: Scaling Preparation & Service Discovery

### Create Service Discovery Framework
```bash
# Create script for dynamic target registration
sudo tee /opt/register-instance.sh << EOF
#!/bin/bash
# Script to register new SurgiCase instances for monitoring

INSTANCE_HOST=\$1
INSTANCE_PORT=\$2
ENVIRONMENT=\${3:-production}

if [ -z "\$INSTANCE_HOST" ] || [ -z "\$INSTANCE_PORT" ]; then
    echo "Usage: \$0 <host> <port> [environment]"
    echo "Example: \$0 172.31.50.100 8000 production"
    exit 1
fi

# Add to Prometheus targets
TARGET_FILE="/etc/prometheus/targets/surgicase-instances.yml"
echo "  - targets: ['\${INSTANCE_HOST}:\${INSTANCE_PORT}']" >> \$TARGET_FILE
echo "    labels:" >> \$TARGET_FILE
echo "      cluster: 'surgicase'" >> \$TARGET_FILE
echo "      environment: '\$ENVIRONMENT'" >> \$TARGET_FILE

# Reload Prometheus configuration
curl -X POST http://localhost:9090/-/reload

echo "Instance \${INSTANCE_HOST}:\${INSTANCE_PORT} registered for monitoring"
echo "Check targets at: http://3.83.225.230:9090/targets"
EOF

sudo chmod +x /opt/register-instance.sh
```

---

## ✅ Phase 7: Service Startup & Testing

### Start All Services
```bash
# Enable and start services
sudo systemctl daemon-reload
sudo systemctl enable prometheus grafana-server loki promtail
sudo systemctl start prometheus grafana-server loki promtail

# Check service status
sudo systemctl status prometheus
sudo systemctl status grafana-server  
sudo systemctl status loki
sudo systemctl status promtail
```

### Verify Installation
- [x] **Prometheus**: `curl http://localhost:9090/api/v1/status/config` ✅
- [x] **Grafana**: `curl http://localhost:3000/api/health` ✅
- [x] **Loki**: `curl http://localhost:3100/ready` ✅
- [x] **Remote SurgiCase metrics**: `curl http://172.31.38.136:8000/metrics` ✅

### Test Data Flow
```bash
# Test connectivity to main server
curl http://172.31.38.136:8000/health

# Check Prometheus targets
curl http://localhost:9090/api/v1/targets

# Verify metrics are being collected
curl 'http://localhost:9090/api/v1/query?query=http_requests_total'
```

### Access Monitoring Services
- **Prometheus**: http://3.83.225.230:9090
- **Grafana**: http://3.83.225.230:3000 (admin/SurgiCase2025!)
- **Main SurgiCase**: http://172.31.38.136:8000

---

## ✅ Phase 8: Documentation & Future Scaling Setup

### Update Project Documentation
- [x] **Update main README**: Add monitoring server details ✅
- [x] **Create scaling guide**: Document horizontal scaling procedures ✅ 
- [x] **Update ENDPOINTS.md**: Add monitoring endpoints and server info ✅

### Create Scaling Runbooks
```bash
# Create operations directory
mkdir -p /home/scadreau/docs/operations

# Create scaling runbooks
cat > /home/scadreau/docs/operations/horizontal-scaling.md << EOF
# Horizontal Scaling Guide

## Adding New SurgiCase Instance
1. Deploy new instance on target server
2. Run: sudo /opt/register-instance.sh <private_ip> 8000
3. Verify in Prometheus targets: http://3.83.225.230:9090/targets
4. Update load balancer configuration
5. Test monitoring data collection

## Current Architecture
- Main SurgiCase: 172.31.38.136:8000
- Monitoring Server: 172.31.86.18 (172.31.86.18:9090, :3000, :3100)
- Security Group: sg-06718ecd804840607
- VPC: vpc-0d0a4d7473692be39

## Federation Setup (Multi-Region)
1. Install secondary Prometheus instance
2. Configure federation in prometheus.yml
3. Update Grafana to query federated metrics
4. Set up cross-region alerting
EOF
```

---

## 🎯 Success Criteria

- [x] All services running and healthy on monitoring server ✅
- [x] SurgiCase metrics visible in Prometheus from remote server ✅
- [x] Grafana dashboards displaying data from main server ✅
- [x] Logs flowing through Loki/Promtail ✅
- [x] Service discovery framework functional ✅
- [x] Documentation updated with server details ✅
- [x] Scaling procedures documented ✅

## 🚀 Quick Verification Commands

```bash
# Service health check
sudo systemctl status prometheus grafana-server loki promtail

# Network connectivity test  
curl http://172.31.38.136:8000/metrics | head -10

# Prometheus targets check
curl -s http://localhost:9090/api/v1/targets | jq '.data.activeTargets[] | {job: .labels.job, health: .health, lastScrape: .lastScrape}'

# Access URLs
echo "Prometheus: http://3.83.225.230:9090"
echo "Grafana: http://3.83.225.230:3000"
echo "Main API: http://172.31.38.136:8000"
```

---

**Estimated Completion Time**: 3-4 hours  
**Server**: m8g.xlarge (172.31.86.18)  
**Prerequisites**: SSH access, security groups configured, basic command line knowledge 