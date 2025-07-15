# Server Deployment Guide

This guide explains how to deploy the SurgiCase monitoring stack on a Linux server.

## 🚀 Quick Deployment

### 1. Clone/Push to Server

```bash
# Option A: Clone from git repository
git clone <your-repo-url>
cd surgicase

# Option B: Copy files to server
scp -r monitoring/ user@your-server:/path/to/surgicase/
```

### 2. Run Deployment Script

```bash
cd monitoring/scripts
chmod +x deploy-to-server.sh
sudo ./deploy-to-server.sh
```

### 3. Start Monitoring Stack

```bash
cd monitoring
./scripts/start-monitoring.sh
```

## 📋 Manual Setup (Alternative)

If you prefer manual setup or the deployment script doesn't work:

### 1. Install Docker

```bash
# Update package list
sudo apt-get update

# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Add user to docker group
sudo usermod -aG docker $USER

# Log out and back in, or run:
newgrp docker
```

### 2. Install Docker Compose

```bash
# Download Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose

# Make executable
sudo chmod +x /usr/local/bin/docker-compose
```

### 3. Set Up Monitoring

```bash
# Navigate to monitoring directory
cd monitoring

# Make scripts executable
chmod +x scripts/*.sh

# Start monitoring stack
./scripts/start-monitoring.sh
```

## 🔧 Configuration

### Firewall Setup

If you have a firewall enabled:

```bash
# UFW (Ubuntu)
sudo ufw allow 9090/tcp  # Prometheus
sudo ufw allow 3000/tcp  # Grafana
sudo ufw allow 8000/tcp  # SurgiCase API

# iptables
sudo iptables -A INPUT -p tcp --dport 9090 -j ACCEPT
sudo iptables -A INPUT -p tcp --dport 3000 -j ACCEPT
sudo iptables -A INPUT -p tcp --dport 8000 -j ACCEPT
```

### Systemd Service (Auto-start)

Create a systemd service for auto-start:

```bash
sudo tee /etc/systemd/system/surgicase-monitoring.service << EOF
[Unit]
Description=SurgiCase Monitoring Stack
Requires=docker.service
After=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=$(pwd)/monitoring
ExecStart=$(pwd)/monitoring/scripts/start-monitoring.sh
ExecStop=$(pwd)/monitoring/scripts/stop-monitoring.sh
TimeoutStartSec=0

[Install]
WantedBy=multi-user.target
EOF

# Enable and start
sudo systemctl daemon-reload
sudo systemctl enable surgicase-monitoring
sudo systemctl start surgicase-monitoring
```

## 📊 Access URLs

After deployment, access your monitoring tools at:

- **Prometheus**: http://your-server-ip:9090
- **Grafana**: http://your-server-ip:3000 (admin/admin)
- **SurgiCase API**: http://your-server-ip:8000
- **Metrics**: http://your-server-ip:8000/metrics

## 🛠️ Management Commands

### Using Scripts

```bash
# Start monitoring
./monitoring/scripts/start-monitoring.sh

# Stop monitoring
./monitoring/scripts/stop-monitoring.sh

# Check status
cd monitoring && docker-compose ps
```

### Using Systemd (if configured)

```bash
# Start service
sudo systemctl start surgicase-monitoring

# Stop service
sudo systemctl stop surgicase-monitoring

# Check status
sudo systemctl status surgicase-monitoring

# View logs
sudo journalctl -u surgicase-monitoring -f
```

### Using Docker Compose Directly

```bash
cd monitoring

# Start services
docker-compose up -d

# Stop services
docker-compose down

# View logs
docker-compose logs -f

# Restart specific service
docker-compose restart prometheus
```

## 🔍 Troubleshooting

### Common Issues

1. **Port already in use**:
   ```bash
   # Check what's using the port
   sudo netstat -tulpn | grep :9090
   
   # Kill the process or change ports in docker-compose.yml
   ```

2. **Permission denied**:
   ```bash
   # Make scripts executable
   chmod +x monitoring/scripts/*.sh
   
   # Add user to docker group
   sudo usermod -aG docker $USER
   ```

3. **Docker not running**:
   ```bash
   # Start Docker
   sudo systemctl start docker
   sudo systemctl enable docker
   ```

4. **Can't access from outside**:
   ```bash
   # Check firewall
   sudo ufw status
   
   # Check if services are bound to localhost
   # Edit docker-compose.yml to use "0.0.0.0" instead of "localhost"
   ```

### Logs and Debugging

```bash
# View all logs
cd monitoring
docker-compose logs

# View specific service logs
docker-compose logs prometheus
docker-compose logs grafana

# Follow logs in real-time
docker-compose logs -f

# Check container status
docker-compose ps

# Check resource usage
docker stats
```

## 🔄 Updates

To update the monitoring stack:

```bash
cd monitoring

# Pull latest images
docker-compose pull

# Restart services
docker-compose down
docker-compose up -d

# Or restart with new images
docker-compose up -d --force-recreate
```

## 📈 Production Considerations

For production deployment:

1. **Use external database** for Grafana persistence
2. **Set up SSL/TLS** with reverse proxy (nginx)
3. **Configure backup** for Prometheus data
4. **Set up alerting** with AlertManager
5. **Use secrets management** for sensitive data
6. **Monitor the monitoring** (meta-monitoring)

## 📞 Support

If you encounter issues:

1. Check the troubleshooting section above
2. Review Docker logs: `docker-compose logs`
3. Verify all prerequisites are met
4. Check the main monitoring README.md 