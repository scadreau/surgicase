# Created: 2025-07-30 17:18:16
# Last Modified: 2025-07-30 17:18:45
# Author: Scott Cadreau

# SurgiCase Health Check System

A comprehensive health monitoring system for the SurgiCase API that monitors all critical AWS services and infrastructure components with intelligent caching and configurable thresholds.

## 🔍 Overview

The SurgiCase health check system provides multi-level health monitoring with:

- **Comprehensive AWS Service Monitoring**: RDS, S3, Amplify, API Gateway, EC2, and Secrets Manager
- **Intelligent Caching**: 5-minute cache reduces AWS API calls and improves response times
- **Configurable Service Classification**: Critical vs non-critical service categorization
- **Multiple Endpoint Types**: Full detailed checks, simplified system status, and Kubernetes probes
- **Performance Monitoring**: Response time tracking with configurable thresholds
- **Easy Scaling**: JSON configuration for adding/removing resources as infrastructure grows

## 🏗️ Architecture

### Service Classification

**Critical Services** (failure = system "unhealthy"):
- **RDS Database**: Primary data storage
- **AWS Secrets Manager**: Credential management
- **API Gateway**: External API access
- **EC2 Instances**: Compute infrastructure

**Non-Critical Services** (failure = system "degraded"):
- **S3 Storage**: Document storage
- **Amplify**: Frontend application
- **System Resources**: CPU/Memory/Disk monitoring

### Health Status Levels

- **healthy**: All services operational within performance thresholds
- **degraded**: Non-critical services down OR services slow but functional
- **unhealthy**: Any critical service down or unresponsive

## 📊 Endpoints

### `/health` - Comprehensive Health Check
**Purpose**: Full system health with detailed component breakdown
**Use Case**: Administrative monitoring, debugging, detailed system status
**Caching**: 5-minute cache shared with other endpoints
**Response Time**: ~2-5 seconds (first call), ~50ms (cached)

```json
{
  "status": "healthy",
  "timestamp": "2024-01-15T10:30:00Z",
  "response_time_ms": 1250,
  "summary": {
    "total_services": 7,
    "healthy": 7,
    "degraded": 0,
    "unhealthy": 0
  },
  "components": {
    "database": {
      "status": "healthy",
      "response_time_ms": 45,
      "details": "Database connection and query test successful"
    },
    "api_gateway": {
      "status": "healthy", 
      "response_time_ms": 320,
      "details": "API Gateway 'SurgiCase API' is accessible",
      "api_name": "SurgiCase API",
      "region": "us-east-1"
    },
    "ec2_instances": {
      "status": "healthy",
      "response_time_ms": 890,
      "total_instances": 1,
      "healthy_instances": 1,
      "instances": [
        {
          "instance_id": "i-099fb57644b0c33ba",
          "state": "running",
          "system_status": "ok",
          "instance_status": "ok",
          "healthy": true
        }
      ]
    },
    "s3_storage": {
      "status": "healthy",
      "response_time_ms": 190,
      "bucket_name": "amplify-surgicalcasemanag-surgicaldocsbucket5a7ebd-8usdadqv6nnp",
      "has_objects": true
    }
  },
  "version": "2.0.0",
  "service": "surgicase-api"
}
```

### `/health/system` - Simplified System Status
**Purpose**: Fast system status check for user interfaces
**Use Case**: User login validation, external monitoring, status pages
**Caching**: 5-minute cache shared with comprehensive check
**Response Time**: ~50ms (cached), ~2-5 seconds (fresh)

```json
{
  "status": "healthy",
  "timestamp": "2024-01-15T10:30:00Z",
  "response_time_ms": 1250,
  "summary": {
    "total_services": 7,
    "healthy": 7,
    "degraded": 0,
    "unhealthy": 0
  },
  "version": "2.0.0",
  "service": "surgicase-api"
}
```

### `/health/ready` - Kubernetes Readiness
**Purpose**: Kubernetes readiness probe - service ready to receive traffic
**Use Case**: Load balancer decisions, pod readiness
**Logic**: Only critical services must be healthy

### `/health/live` - Kubernetes Liveness  
**Purpose**: Kubernetes liveness probe - service is alive
**Use Case**: Pod restart decisions
**Logic**: Basic service availability only

## ⚙️ Configuration

### Configuration File: `utils/health_config.json`

```json
{
  "aws_resources": {
    "critical_services": [
      {
        "name": "rds_database",
        "type": "rds",
        "config": {
          "description": "Primary RDS database connection"
        }
      },
      {
        "name": "api_gateway",
        "type": "api_gateway",
        "config": {
          "api_id": "5gt34rnqxc",
          "region": "us-east-1"
        }
      },
      {
        "name": "ec2_instances",
        "type": "ec2",
        "config": {
          "instance_ids": ["i-099fb57644b0c33ba"],
          "region": "us-east-1"
        }
      }
    ],
    "non_critical_services": [
      {
        "name": "s3_storage",
        "type": "s3",
        "config": {
          "bucket_name": "amplify-surgicalcasemanag-surgicaldocsbucket5a7ebd-8usdadqv6nnp",
          "region": "us-east-1"
        }
      },
      {
        "name": "amplify_app",
        "type": "amplify",
        "config": {
          "app_id": "d2ghhkk9htiisb",
          "region": "us-east-1"
        }
      }
    ]
  },
  "health_thresholds": {
    "database": {
      "healthy_ms": 500,
      "degraded_ms": 2000
    },
    "aws_apis": {
      "healthy_ms": 1000,
      "degraded_ms": 3000
    }
  },
  "cache_settings": {
    "cache_duration_seconds": 300,
    "enable_caching": true
  }
}
```

### Adding New Services

To add a new service to monitoring:

1. **Add to configuration** in `utils/health_config.json`:
```json
{
  "name": "new_service",
  "type": "service_type",
  "config": {
    "resource_id": "resource-identifier",
    "region": "us-east-1"
  }
}
```

2. **Implement health check function** in `endpoints/health.py`:
```python
def check_new_service_health() -> Dict[str, Any]:
    """Check new service health"""
    # Implementation here
```

3. **Add to main health check** in `perform_comprehensive_health_check()`:
```python
new_service_health = check_new_service_health()
```

4. **Classify service** as critical or non-critical in the components dictionary.

### Scaling EC2 Instances

To add additional EC2 instances:

```json
{
  "name": "ec2_instances",
  "type": "ec2", 
  "config": {
    "instance_ids": [
      "i-099fb57644b0c33ba",
      "i-new-instance-id-here",
      "i-another-instance-id"
    ],
    "region": "us-east-1"
  }
}
```

## 🔧 Implementation Details

### Caching Mechanism

**Cache Duration**: 5 minutes (300 seconds)
**Cache Scope**: Per-instance (each server maintains its own cache)
**Cache Strategy**: 
- First request performs full health check
- Subsequent requests return cached results
- Cache automatically expires after 5 minutes
- Cache shared between `/health` and `/health/system` endpoints

**Benefits**:
- Reduces AWS API calls by ~95% for frequent checks
- Improves response time from ~2-5 seconds to ~50ms
- Prevents AWS API rate limiting
- Optimizes cost (fewer AWS API calls)

### Service-Specific Health Checks

#### RDS Database
- **Test**: Connection + simple query (`SELECT 1`)
- **Threshold**: <500ms healthy, 500-2000ms degraded, >2000ms unhealthy
- **Critical**: Yes (system unhealthy if down)

#### API Gateway
- **Test**: `get_rest_api()` call to verify gateway accessibility
- **Threshold**: <1000ms healthy, 1000-3000ms degraded, >3000ms unhealthy
- **Critical**: Yes (external API access required)

#### EC2 Instances
- **Test**: `describe_instance_status()` for all configured instances
- **Logic**: All instances must be "running" with "ok" system/instance status
- **Critical**: Yes (compute infrastructure required)

#### S3 Storage
- **Test**: `head_bucket()` + `list_objects_v2()` for read verification
- **Threshold**: <1000ms healthy, 1000-3000ms degraded, >3000ms unhealthy
- **Critical**: No (document storage, non-critical for core operations)

#### Amplify
- **Test**: `get_app()` to verify deployment status
- **Threshold**: <1000ms healthy, 1000-3000ms degraded, >3000ms unhealthy
- **Critical**: No (frontend, API can function independently)

#### AWS Secrets Manager
- **Test**: `list_secrets()` call (limited to 1 result)
- **Threshold**: <1000ms healthy, 1000-3000ms degraded, >3000ms unhealthy
- **Critical**: Yes (credential access required)

### Error Handling

**Service Unavailable**: Returns `status: "unhealthy"` with error details
**Configuration Missing**: Returns `status: "unknown"` with helpful message
**AWS API Errors**: Logged with full error details, returns unhealthy status
**Timeout Handling**: Each service check has built-in timeout handling

## 📈 Monitoring Integration

### Prometheus Metrics
The health check system automatically exposes metrics via the existing monitoring framework:
- `health_check_duration_seconds` - Time taken for health checks
- `health_check_status` - Current health status (0=unhealthy, 1=degraded, 2=healthy)
- `service_health_status` - Individual service status by service name

### Logging
- **INFO**: Successful health checks with timing
- **WARNING**: Degraded services with details
- **ERROR**: Failed health checks with full error information
- **Cache Events**: Cache hits and refreshes logged at DEBUG level

## 🚀 Usage Patterns

### User Login Validation
**Recommended**: Use `/health/system` endpoint
```javascript
// Check system status on user login
const response = await fetch('/health/system');
const health = await response.json();

if (health.status === 'unhealthy') {
  showMaintenanceMessage();
} else if (health.status === 'degraded') {
  showDegradedServiceWarning();
} else {
  proceedWithLogin();
}
```

### External Monitoring
**Recommended**: Use `/health/system` for status pages, `/health` for detailed debugging
```bash
# Simple monitoring check
curl -f http://api.example.com/health/system

# Detailed system analysis  
curl http://api.example.com/health | jq '.components'
```

### Load Balancer Health Checks
**Recommended**: Use `/health/ready` for load balancer target health
```yaml
# ALB Target Group Health Check
HealthCheckPath: /health/ready
HealthCheckIntervalSeconds: 30
HealthyThresholdCount: 2
UnhealthyThresholdCount: 3
```

### Kubernetes Deployment
```yaml
apiVersion: v1
kind: Pod
spec:
  containers:
  - name: surgicase-api
    image: surgicase:latest
    livenessProbe:
      httpGet:
        path: /health/live
        port: 8000
      initialDelaySeconds: 30
      periodSeconds: 10
    readinessProbe:
      httpGet:
        path: /health/ready
        port: 8000
      initialDelaySeconds: 5
      periodSeconds: 5
```

## 🔐 Security Considerations

### AWS Permissions
The health check system requires the following AWS IAM permissions:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "secretsmanager:ListSecrets",
        "apigateway:GET",
        "ec2:DescribeInstanceStatus",
        "s3:HeadBucket",
        "s3:ListBucket",
        "amplify:GetApp"
      ],
      "Resource": "*"
    }
  ]
}
```

### Data Exposure
- Health endpoints do **not** expose sensitive data
- AWS resource names and regions are included for debugging
- No credentials, connection strings, or sensitive configuration exposed
- Error messages are sanitized to prevent information leakage

## 🧪 Testing

### Manual Testing
```bash
# Test full health check
curl -v http://localhost:8000/health

# Test simplified system status
curl -v http://localhost:8000/health/system

# Test readiness (critical services only)
curl -v http://localhost:8000/health/ready

# Test liveness (basic availability)
curl -v http://localhost:8000/health/live
```

### Cache Testing
```bash
# First call (should be slow, ~2-5 seconds)
time curl http://localhost:8000/health/system

# Second call (should be fast, ~50ms)  
time curl http://localhost:8000/health/system

# Wait 6 minutes and test again (cache expired)
sleep 360
time curl http://localhost:8000/health/system
```

### Service Failure Simulation
**Database**: Stop MySQL service temporarily
**S3**: Temporarily revoke S3 permissions
**EC2**: Stop EC2 instance
**API Gateway**: Use invalid API ID in configuration

## 🎯 Best Practices

### When to Use Each Endpoint

| Endpoint | Use Case | Response Time | Detail Level | Caching |
|----------|----------|---------------|--------------|---------|
| `/health` | Debugging, admin monitoring | ~50ms (cached) | Full details | 5 minutes |
| `/health/system` | User login, status pages | ~50ms (cached) | Summary only | 5 minutes |
| `/health/ready` | Load balancer health | ~50ms (cached) | Pass/fail only | 5 minutes |
| `/health/live` | Kubernetes liveness | ~10ms | Basic availability | None |

### Configuration Management

1. **Version Control**: Keep `health_config.json` in version control
2. **Environment-Specific**: Use different configurations for dev/staging/prod
3. **Backup Strategy**: AWS resource IDs should be documented separately
4. **Change Management**: Test configuration changes in staging first

### Performance Optimization

1. **Use Caching**: Don't disable caching unless absolutely necessary
2. **Monitor Thresholds**: Adjust thresholds based on actual AWS performance
3. **Service Prioritization**: Keep critical/non-critical classification accurate
4. **Batch Operations**: Health checks run all services in parallel for speed

## 🔧 Troubleshooting

### Common Issues

**Cache Not Working**
- Check `cache_settings.enable_caching` in configuration
- Verify cache duration is reasonable (>0 seconds)
- Restart application if cache corruption suspected

**Slow Health Checks**
- Check AWS API response times in CloudWatch
- Verify network connectivity to AWS services
- Consider adjusting timeout thresholds
- Ensure caching is enabled

**False Negatives**
- Verify AWS permissions for health check service account
- Check AWS service-specific status pages
- Review error logs for specific failure details
- Test individual service connectivity manually

**Service Not Found**
- Verify resource IDs in configuration file
- Check AWS region settings
- Ensure resources exist and are accessible
- Review AWS service-specific configuration

### Debug Mode
Enable detailed logging for health check debugging:
```python
import logging
logging.getLogger('endpoints.health').setLevel(logging.DEBUG)
```

## 📋 Maintenance

### Regular Tasks

**Weekly**:
- Review health check performance metrics
- Verify all monitored resources are still active
- Check for new AWS services that should be monitored

**Monthly**:
- Review and adjust performance thresholds based on historical data
- Update configuration for any infrastructure changes
- Test failover scenarios and health check responses

**Quarterly**:
- Review service classification (critical vs non-critical)
- Update AWS permissions if new services added
- Performance optimization based on usage patterns

---

**SurgiCase Health Check System** - Comprehensive, cached, and configurable health monitoring for production AWS infrastructure.