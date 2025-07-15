#!/bin/bash

# SurgiCase Monitoring Stack Server Deployment Script

echo "🚀 Deploying SurgiCase Monitoring Stack to Server..."

# Check if running as root or with sudo
if [ "$EUID" -ne 0 ]; then
    echo "⚠️  This script should be run with sudo for proper setup"
    echo "   Run: sudo ./deploy-to-server.sh"
    exit 1
fi

# Set script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MONITORING_DIR="$(dirname "$SCRIPT_DIR")"

echo "📁 Monitoring directory: $MONITORING_DIR"

# Make scripts executable
echo "🔧 Setting executable permissions..."
chmod +x "$MONITORING_DIR/scripts/"*.sh

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo "❌ Docker is not installed. Installing Docker..."
    
    # Update package list
    apt-get update
    
    # Install Docker
    curl -fsSL https://get.docker.com -o get-docker.sh
    sh get-docker.sh
    
    # Add current user to docker group
    usermod -aG docker $SUDO_USER
    
    echo "✅ Docker installed. Please log out and back in, then run this script again."
    exit 0
fi

# Check if docker-compose is installed
if ! command -v docker-compose &> /dev/null; then
    echo "❌ Docker Compose is not installed. Installing Docker Compose..."
    
    # Install Docker Compose
    curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
    chmod +x /usr/local/bin/docker-compose
    
    echo "✅ Docker Compose installed."
fi

# Create systemd service for auto-start (optional)
echo "🔧 Creating systemd service for auto-start..."
cat > /etc/systemd/system/surgicase-monitoring.service << EOF
[Unit]
Description=SurgiCase Monitoring Stack
Requires=docker.service
After=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=$MONITORING_DIR
ExecStart=$MONITORING_DIR/scripts/start-monitoring.sh
ExecStop=$MONITORING_DIR/scripts/stop-monitoring.sh
TimeoutStartSec=0

[Install]
WantedBy=multi-user.target
EOF

# Enable the service
systemctl daemon-reload
systemctl enable surgicase-monitoring.service

echo "✅ Systemd service created and enabled."

# Create log directory
mkdir -p /var/log/surgicase-monitoring

# Set up log rotation
cat > /etc/logrotate.d/surgicase-monitoring << EOF
/var/log/surgicase-monitoring/*.log {
    daily
    missingok
    rotate 7
    compress
    delaycompress
    notifempty
    create 644 root root
}
EOF

echo "✅ Log rotation configured."

# Create monitoring user (optional)
if ! id "surgicase" &>/dev/null; then
    echo "🔧 Creating surgicase user..."
    useradd -r -s /bin/bash -d $MONITORING_DIR surgicase
    chown -R surgicase:surgicase $MONITORING_DIR
    usermod -aG docker surgicase
fi

# Set up firewall rules (if ufw is active)
if command -v ufw &> /dev/null && ufw status | grep -q "Status: active"; then
    echo "🔧 Configuring firewall rules..."
    ufw allow 9090/tcp  # Prometheus
    ufw allow 3000/tcp  # Grafana
    echo "✅ Firewall rules configured."
fi

# Create monitoring status script
cat > /usr/local/bin/surgicase-monitoring-status << EOF
#!/bin/bash
cd $MONITORING_DIR
docker-compose ps
EOF

chmod +x /usr/local/bin/surgicase-monitoring-status

echo ""
echo "🎉 Deployment completed successfully!"
echo ""
echo "📋 Next steps:"
echo "   1. Start the monitoring stack:"
echo "      cd $MONITORING_DIR && ./scripts/start-monitoring.sh"
echo ""
echo "   2. Or use systemd service:"
echo "      sudo systemctl start surgicase-monitoring"
echo ""
echo "   3. Check status:"
echo "      surgicase-monitoring-status"
echo ""
echo "   4. Access monitoring:"
echo "      Prometheus: http://your-server-ip:9090"
echo "      Grafana:    http://your-server-ip:3000 (admin/admin)"
echo ""
echo "📝 Useful commands:"
echo "   - Start:   sudo systemctl start surgicase-monitoring"
echo "   - Stop:    sudo systemctl stop surgicase-monitoring"
echo "   - Status:  sudo systemctl status surgicase-monitoring"
echo "   - Logs:    sudo journalctl -u surgicase-monitoring -f" 