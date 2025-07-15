#!/bin/bash

# SurgiCase Monitoring Stack Startup Script

echo "🚀 Starting SurgiCase Monitoring Stack..."

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo "❌ Docker is not running. Please start Docker and try again."
    exit 1
fi

# Check if docker-compose is available
if ! command -v docker-compose &> /dev/null; then
    echo "❌ docker-compose is not installed. Please install docker-compose and try again."
    exit 1
fi

# Navigate to monitoring directory
cd "$(dirname "$0")/.."

# Pull latest images
echo "📥 Pulling latest Docker images..."
docker-compose pull

# Start services
echo "🔧 Starting monitoring services..."
docker-compose up -d

# Wait for services to be ready
echo "⏳ Waiting for services to be ready..."
sleep 10

# Check service status
echo "📊 Checking service status..."
docker-compose ps

# Test Prometheus
echo "🔍 Testing Prometheus..."
if curl -s http://localhost:9090/api/v1/status/config > /dev/null; then
    echo "✅ Prometheus is running at http://localhost:9090"
else
    echo "⚠️  Prometheus might still be starting up..."
fi

# Test Grafana
echo "🔍 Testing Grafana..."
if curl -s http://localhost:3000/api/health > /dev/null; then
    echo "✅ Grafana is running at http://localhost:3000"
    echo "   Default credentials: admin/admin"
else
    echo "⚠️  Grafana might still be starting up..."
fi

echo ""
echo "🎉 Monitoring stack started successfully!"
echo ""
echo "📋 Access URLs:"
echo "   Prometheus: http://localhost:9090"
echo "   Grafana:    http://localhost:3000 (admin/admin)"
echo "   SurgiCase:  http://localhost:8000"
echo "   Metrics:    http://localhost:8000/metrics"
echo ""
echo "📝 Next steps:"
echo "   1. Start your SurgiCase API: python main.py"
echo "   2. Open Grafana and add Prometheus as a data source"
echo "   3. Import the SurgiCase dashboard"
echo ""
echo "🛑 To stop monitoring: ./scripts/stop-monitoring.sh" 