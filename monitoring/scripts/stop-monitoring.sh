#!/bin/bash

# SurgiCase Monitoring Stack Stop Script

echo "🛑 Stopping SurgiCase Monitoring Stack..."

# Navigate to monitoring directory
cd "$(dirname "$0")/.."

# Stop services
echo "🔧 Stopping monitoring services..."
docker-compose down

# Remove volumes (optional - uncomment if you want to clear data)
# echo "🗑️  Removing monitoring data..."
# docker-compose down -v

echo ""
echo "✅ Monitoring stack stopped successfully!"
echo ""
echo "📝 To start again: ./scripts/start-monitoring.sh" 