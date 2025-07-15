# SurgiCase Monitoring Stack

This directory contains the complete monitoring infrastructure for the SurgiCase application, including Prometheus for metrics collection and Grafana for visualization.

## 🏗️ Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   SurgiCase     │    │   Prometheus    │    │     Grafana     │
│     API         │───▶│   (Metrics      │───▶│   (Dashboard    │
│  (Port 8000)    │    │   Collector)    │    │   & Alerts)     │
│                 │    │  (Port 9090)    │    │  (Port 3000)    │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

## 📋 Prerequisites

- Docker and Docker Compose installed
- SurgiCase API running on port 8000
- At least 2GB of available RAM

## 🚀 Quick Start

### 1. Start the Monitoring Stack

```bash
# From the project root
cd monitoring
./scripts/start-monitoring.sh
```

### 2. Start Your SurgiCase API

```bash
# From the project root
python main.py
```

### 3. Access the Monitoring Tools

- **Prometheus**: http://localhost:9090
- **Grafana**: http://localhost:3000 (admin/admin)
- **SurgiCase API**: http://localhost:8000
- **SurgiCase Metrics**: http://localhost:8000/metrics

## 📊 Available Dashboards

### SurgiCase Overview Dashboard
- **Request Rate**: HTTP requests per second
- **Error Rate**: Error rate with thresholds
- **Response Time**: 95th percentile response time
- **Active Cases**: Current number of active cases
- **Case Operations**: Business operation metrics
- **System Resources**: CPU, memory, and disk usage
- **Database Connections**: Active database connections
- **User Operations**: User-related metrics

## 🔔 Alerting Rules

The monitoring stack includes pre-configured alerts for:

- **High Error Rate**: >10% error rate for 2 minutes
- **High Response Time**: >2 seconds 95th percentile for 2 minutes
- **Database Issues**: Any database connection errors
- **High CPU Usage**: >80% CPU for 5 minutes
- **High Memory Usage**: >85% memory for 5 minutes
- **Service Down**: API unavailable for 1 minute

## 🛠️ Configuration Files

### Prometheus Configuration
- `prometheus/prometheus.yml`: Main Prometheus configuration
- `prometheus/alerts.yml`: Alerting rules

### Grafana Configuration
- `grafana/provisioning/dashboards/dashboard.yml`: Dashboard provisioning
- `grafana/provisioning/datasources/datasource.yml`: Data source configuration
- `grafana/dashboards/surgicase-overview.json`: Main dashboard

## 📈 Metrics Available

### Business Metrics
- `case_operations_total`: Case creation, updates, deletions
- `user_operations_total`: User management operations
- `facility_operations_total`: Facility management operations
- `surgeon_operations_total`: Surgeon management operations
- `active_cases_total`: Current active cases count
- `active_users_total`: Current active users count

### System Metrics
- `http_requests_total`: HTTP request counts
- `http_request_duration_seconds`: Request duration histograms
- `system_cpu_usage_percent`: CPU usage
- `system_memory_usage_percent`: Memory usage
- `system_disk_usage_percent`: Disk usage

### Database Metrics
- `database_connections_active`: Active database connections
- `database_connection_errors_total`: Connection errors
- `database_query_duration_seconds`: Query performance

## 🔧 Customization

### Adding New Metrics

1. **Add metrics to your API endpoints**:
   ```python
   from utils.monitoring import business_metrics
   business_metrics.record_custom_operation("operation", "status")
   ```

2. **Update Prometheus configuration** if needed
3. **Add panels to Grafana dashboard**

### Adding New Alerts

1. **Edit `prometheus/alerts.yml`**:
   ```yaml
   - alert: NewAlert
     expr: your_metric > threshold
     for: 5m
     labels:
       severity: warning
   ```

2. **Restart Prometheus**:
   ```bash
   docker-compose restart prometheus
   ```

## 🐛 Troubleshooting

### Common Issues

1. **Prometheus can't scrape metrics**:
   - Check if SurgiCase API is running on port 8000
   - Verify `host.docker.internal` resolves correctly
   - Check firewall settings

2. **Grafana can't connect to Prometheus**:
   - Verify Prometheus is running: `docker-compose ps`
   - Check Prometheus logs: `docker-compose logs prometheus`
   - Ensure data source URL is correct: `http://prometheus:9090`

3. **No data in dashboards**:
   - Check if metrics are being generated: http://localhost:8000/metrics
   - Verify Prometheus is scraping: http://localhost:9090/targets
   - Check for time range issues in Grafana

### Debug Commands

```bash
# Check service status
docker-compose ps

# View logs
docker-compose logs prometheus
docker-compose logs grafana

# Test metrics endpoint
curl http://localhost:8000/metrics

# Test Prometheus
curl http://localhost:9090/api/v1/status/config
```

## 📚 Advanced Configuration

### Persistent Storage

Data is stored in Docker volumes:
- `prometheus_data`: Prometheus time-series data
- `grafana_data`: Grafana dashboards and settings

To backup data:
```bash
docker run --rm -v surgicase_prometheus_data:/data -v $(pwd):/backup alpine tar czf /backup/prometheus-backup.tar.gz -C /data .
```

### Scaling

For production deployment:
1. **Use external Prometheus** for better scalability
2. **Set up Grafana with external database** (PostgreSQL/MySQL)
3. **Configure alerting** with AlertManager
4. **Set up log aggregation** with Loki

## 🛑 Stopping the Stack

```bash
cd monitoring
./scripts/stop-monitoring.sh
```

## 📞 Support

For issues with the monitoring stack:
1. Check the troubleshooting section above
2. Review Docker logs: `docker-compose logs`
3. Verify all prerequisites are met
4. Check the main SurgiCase documentation

## 🔄 Updates

To update the monitoring stack:
```bash
cd monitoring
docker-compose pull
docker-compose up -d
``` 