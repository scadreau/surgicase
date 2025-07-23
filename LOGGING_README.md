# SurgiCase API Request Logging System

## Overview

The SurgiCase API implements a comprehensive request logging system that provides detailed monitoring, analytics, and audit capabilities across **22 critical endpoints** covering complete CRUD operations for cases, users, facilities, and surgeons, plus administrative, search, and utility functions. This system captures request details, performance metrics, error information, and business intelligence data for operational insights and compliance requirements.

### Coverage Summary
- **Complete Case Management**: All CRUD operations (Create, Read, Update, Delete, Filter)
- **Complete User Management**: All CRUD operations (Create, Read, Update, Delete)
- **Complete Facility Management**: Create, Read, Delete operations with user context
- **Complete Surgeon Management**: Create, Read, Delete operations with user context
- **Administrative Functions**: Backoffice operations with permission tracking
- **Search Operations**: Facility and surgeon search with pattern analysis
- **Utility Functions**: Reference data, validation, and external API integration
- **22 Total Endpoints**: Enterprise-level monitoring across all API functions

## Architecture

### Core Components

1. **Log Request Utility (`endpoints/utility/log_request.py`)**
   - Primary logging endpoint (`/log_request`)
   - Utility function for automated endpoint logging
   - Database storage integration
   - Business metrics recording

2. **Request Logging Model (`core/models.py`)**
   - `LogRequestModel` - Structured data model for request logs
   - Comprehensive field coverage for all logging scenarios

3. **Monitoring Integration (`utils/monitoring.py`)**
   - Business metrics tracking
   - Prometheus metrics integration
   - Performance monitoring decorators

## Features

### 📊 Comprehensive Data Capture

- **Request Details**: Method, endpoint, query parameters, request payload
- **Response Information**: Status codes, response payload, execution time
- **Client Information**: IP address, user agent, authentication details
- **Error Tracking**: Detailed error messages, stack traces, failure scenarios
- **Performance Metrics**: Precise execution timing in milliseconds

### 🔍 Business Intelligence

- **User Activity**: Track user actions and behavior patterns
- **API Usage**: Monitor endpoint usage frequency and patterns
- **Performance Analytics**: Identify slow operations and optimization opportunities
- **Error Analysis**: Understand failure modes and system reliability

### 🛡️ Security & Compliance

- **Audit Trail**: Complete record of all API interactions
- **Access Monitoring**: Track who accesses what data and when
- **Permission Tracking**: Log permission denied scenarios
- **Data Governance**: Monitor sensitive data access patterns

## Log Request Model

```python
class LogRequestModel(BaseModel):
    timestamp: datetime = Field(default_factory=datetime.now)
    user_id: str | None = None
    endpoint: str
    method: str
    request_payload: str | None = None
    query_params: str | None = None
    response_status: int
    response_payload: str | None = None
    execution_time_ms: int
    error_message: str | None = None
    client_ip: str | None = None
```

## Implementation

### Core Logging Functions

#### 1. Direct Log Request Endpoint
```python
@router.post("/log_request")
@track_business_operation("log", "request")
def log_request(log: LogRequestModel):
    # Stores log data directly to database
    # Used for external logging requests
```

#### 2. Utility Function for Endpoints
```python
def log_request_from_endpoint(
    request: Request, 
    execution_time_ms: int, 
    response_status: int, 
    user_id: str = None, 
    response_data: dict = None, 
    error_message: str = None
):
    # Automated logging for any endpoint
    # Extracts data from FastAPI Request object
    # Handles client IP detection from multiple sources
```

### Integration Pattern

All monitored endpoints follow this pattern:

```python
@router.method("/endpoint")
@track_business_operation("operation", "entity")
def endpoint_function(request: Request, ...):
    conn = None
    start_time = time.time()
    response_status = 200
    response_data = None
    error_message = None
    
    try:
        # Main endpoint logic
        response_data = {"result": "success"}
        return response_data
        
    except HTTPException as http_error:
        response_status = http_error.status_code
        error_message = str(http_error.detail)
        raise
    except Exception as e:
        response_status = 500
        error_message = str(e)
        raise HTTPException(status_code=500, detail={"error": str(e)})
        
    finally:
        execution_time_ms = int((time.time() - start_time) * 1000)
        
        from endpoints.utility.log_request import log_request_from_endpoint
        log_request_from_endpoint(
            request=request,
            execution_time_ms=execution_time_ms,
            response_status=response_status,
            user_id=user_id,
            response_data=response_data,
            error_message=error_message
        )
```

## Monitored Endpoints

### Case Management (Complete CRUD Coverage)
- **`POST /case`** - Case creation with comprehensive transaction logging
- **`GET /case`** - Individual case retrieval with access pattern tracking
- **`PATCH /case`** - Case updates with field-level change tracking
- **`DELETE /case`** - Case deletion with S3 archive operation monitoring
- **`GET /casefilter`** - Case filtering with query parameter tracking

### User Management (Complete CRUD Coverage)
- **`POST /user`** - User creation with profile and document logging
- **`GET /user`** - Individual user retrieval with access pattern tracking
- **`PATCH /user`** - User updates with field-level change tracking
- **`DELETE /user`** - User deletion with archive and S3 document tracking

### Administrative Functions
- **`GET /casesbystatus`** - Administrative case retrieval with permission tracking
- **`GET /users`** - User list access with authorization monitoring

### Facility Management (Complete CRD Coverage)
- **`POST /facility`** - Facility creation with transaction logging and user context
- **`GET /facilities`** - Facility retrieval with user-specific data access
- **`DELETE /facility`** - Facility deletion with error tracking and validation

### Surgeon Management (Complete CRD Coverage)
- **`POST /surgeon`** - Surgeon creation with transaction logging and user context
- **`GET /surgeons`** - Surgeon retrieval with user-specific data access
- **`DELETE /surgeon`** - Surgeon deletion with error tracking and validation

### Search Operations
- **`GET /search-facility`** - Facility search with query pattern analysis
- **`GET /search-surgeon`** - Surgeon search with multi-parameter tracking

### Utility Functions
- **`GET /doctypes`** - Document types retrieval with reference data monitoring
- **`GET /cpt_codes`** - CPT codes retrieval with database performance tracking
- **`GET /check_npi`** - NPI validation with external API integration monitoring

## Complete Monitoring Coverage

| Category | Endpoint | Method | Operation | Key Tracking Features |
|----------|----------|--------|-----------|----------------------|
| **Case Management** | `/case` | POST | Create | Transaction logging, validation, procedure codes |
| | `/case` | GET | Read | Access patterns, user context, status filtering |
| | `/case` | PATCH | Update | Field-level changes, pay calculations, status updates |
| | `/case` | DELETE | Delete | S3 archival, rollback tracking, file management |
| | `/casefilter` | GET | Filter | Query parameters, result sets, permission checks |
| **User Management** | `/user` | POST | Create | Profile creation, document uploads, validation |
| | `/user` | GET | Read | Profile access, document retrieval, activity tracking |
| | `/user` | PATCH | Update | Field updates, document management, change tracking |
| | `/user` | DELETE | Delete | Archive operations, S3 document handling, rollbacks |
| **Facility Management** | `/facility` | POST | Create | Facility creation, user context, transaction logging |
| | `/facilities` | GET | Read | User-specific facility retrieval, access patterns |
| | `/facility` | DELETE | Delete | Facility deletion, error tracking, validation |
| **Surgeon Management** | `/surgeon` | POST | Create | Surgeon creation, user context, transaction logging |
| | `/surgeons` | GET | Read | User-specific surgeon retrieval, access patterns |
| | `/surgeon` | DELETE | Delete | Surgeon deletion, error tracking, validation |
| **Administrative** | `/casesbystatus` | GET | Admin Read | Permission validation, bulk data access, filtering |
| | `/users` | GET | Admin Read | User list access, authorization levels, bulk operations |
| **Search** | `/search-facility` | GET | Search | Search patterns, result analysis, query optimization |
| | `/search-surgeon` | GET | Search | Multi-parameter search, result tracking, performance |
| **Utility** | `/doctypes` | GET | Reference | Document types access, reference data monitoring |
| | `/cpt_codes` | GET | Reference | CPT codes access, database performance tracking |
| | `/check_npi` | GET | Validation | NPI validation, external API integration, error handling |

**Total: 22 Endpoints** with comprehensive logging coverage across all API operations.

## Data Storage

### Database Schema
Logs are stored in the `request_logs` table:

```sql
CREATE TABLE request_logs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    timestamp DATETIME,
    user_id VARCHAR(255),
    endpoint VARCHAR(255),
    method VARCHAR(10),
    request_payload TEXT,
    query_params TEXT,
    response_status INT,
    response_payload TEXT,
    execution_time_ms INT,
    error_message TEXT,
    client_ip VARCHAR(45),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### Data Retention
- **Production**: Logs retained for compliance requirements
- **Development**: Configurable retention periods
- **Archive**: Automated cleanup processes available

## Client IP Detection

The system automatically detects client IP addresses from multiple sources:

1. **Direct Connection**: `request.client.host`
2. **Load Balancer**: `X-Forwarded-For` header
3. **Proxy**: `X-Real-IP` header
4. **Fallback**: Connection metadata

## Performance Monitoring

### Metrics Tracked
- **Execution Time**: Precise millisecond timing
- **Response Sizes**: Payload size monitoring
- **Error Rates**: Success/failure ratios
- **Usage Patterns**: Endpoint frequency analysis

### Integration with Monitoring Stack
- **Prometheus**: Metrics collection and alerting
- **Business Metrics**: Custom business operation tracking
- **Structured Logging**: JSON-formatted log entries

## Error Handling

### Fault Tolerance
- **Non-Blocking**: Logging failures don't affect main operations
- **Graceful Degradation**: Operations continue if logging fails
- **Error Isolation**: Logging errors are captured separately

### Error Categories
- **Validation Errors**: Input parameter validation failures
- **Permission Errors**: Authorization and access control violations
- **Database Errors**: Connection and query failures
- **Business Logic Errors**: Application-specific error conditions

## Security Considerations

### Data Privacy
- **Sensitive Data**: Automatic sanitization of sensitive information
- **PII Protection**: Configurable masking of personal data
- **Payload Filtering**: Optional request/response payload redaction

### Access Control
- **Admin Access**: Restricted access to log data
- **Audit Logs**: Tracking of log access and modifications
- **Encryption**: Database-level encryption for sensitive logs

## Configuration

### Environment Variables
```bash
# Database logging
LOG_DATABASE_ENABLED=true
LOG_RETENTION_DAYS=90

# Payload logging
LOG_REQUEST_PAYLOADS=true
LOG_RESPONSE_PAYLOADS=true
LOG_SENSITIVE_DATA=false

# Performance
LOG_ASYNC_ENABLED=true
LOG_BATCH_SIZE=100
```

### Feature Flags
- **Endpoint Logging**: Enable/disable per endpoint
- **Payload Logging**: Control request/response capture
- **Performance Mode**: Optimize for high-throughput scenarios

## Analytics & Reporting

### Available Metrics
- **API Usage**: Request volume by endpoint and time across all 22 monitored endpoints
- **Performance**: Response time percentiles and trends for all CRUD operations
- **Error Analysis**: Error rate trends and failure patterns by operation type
- **User Activity**: Complete user behavior and access patterns across all functions
- **CRUD Analytics**: Create, Read, Update, Delete operation tracking for all entities
- **Business Intelligence**: Complete lifecycle tracking from creation to deletion
- **Search Analytics**: Facility and surgeon search pattern analysis
- **Administrative Monitoring**: Backoffice operation tracking and permission analysis
- **Resource Management**: Facility and surgeon utilization patterns
- **Reference Data Usage**: Document types and CPT codes access patterns
- **External API Monitoring**: NPI validation service performance and reliability

### Query Examples

#### Most Used Endpoints
```sql
SELECT endpoint, COUNT(*) as request_count 
FROM request_logs 
WHERE timestamp >= DATE_SUB(NOW(), INTERVAL 7 DAY)
GROUP BY endpoint 
ORDER BY request_count DESC;
```

#### Average Response Times
```sql
SELECT endpoint, AVG(execution_time_ms) as avg_response_time
FROM request_logs 
WHERE timestamp >= DATE_SUB(NOW(), INTERVAL 24 HOUR)
GROUP BY endpoint;
```

#### Error Rate Analysis
```sql
SELECT 
    endpoint,
    COUNT(*) as total_requests,
    SUM(CASE WHEN response_status >= 400 THEN 1 ELSE 0 END) as error_count,
    (SUM(CASE WHEN response_status >= 400 THEN 1 ELSE 0 END) * 100.0 / COUNT(*)) as error_rate
FROM request_logs 
WHERE timestamp >= DATE_SUB(NOW(), INTERVAL 7 DAY)
GROUP BY endpoint;
```

#### CRUD Operation Analysis
```sql
SELECT 
    CASE 
        WHEN method = 'POST' THEN 'CREATE'
        WHEN method = 'GET' THEN 'READ'
        WHEN method = 'PATCH' THEN 'UPDATE'
        WHEN method = 'DELETE' THEN 'DELETE'
    END as operation_type,
    COUNT(*) as request_count,
    AVG(execution_time_ms) as avg_response_time,
    SUM(CASE WHEN response_status >= 400 THEN 1 ELSE 0 END) as error_count
FROM request_logs 
WHERE timestamp >= DATE_SUB(NOW(), INTERVAL 24 HOUR)
    AND endpoint IN ('/case', '/user')
GROUP BY operation_type;
```

#### User Activity Patterns
```sql
SELECT 
    user_id,
    COUNT(*) as total_requests,
    COUNT(DISTINCT endpoint) as endpoints_used,
    MIN(timestamp) as first_activity,
    MAX(timestamp) as last_activity,
    AVG(execution_time_ms) as avg_response_time
FROM request_logs 
WHERE user_id IS NOT NULL 
    AND timestamp >= DATE_SUB(NOW(), INTERVAL 7 DAY)
GROUP BY user_id
ORDER BY total_requests DESC
LIMIT 20;
```

#### Search Pattern Analysis
```sql
SELECT 
    endpoint,
    JSON_EXTRACT(query_params, '$.facility_name') as search_term,
    COUNT(*) as search_count,
    AVG(execution_time_ms) as avg_search_time,
    AVG(JSON_LENGTH(JSON_EXTRACT(response_payload, '$.body.facilities'))) as avg_results
FROM request_logs 
WHERE endpoint = '/search-facility' 
    AND timestamp >= DATE_SUB(NOW(), INTERVAL 7 DAY)
GROUP BY endpoint, search_term
ORDER BY search_count DESC;
```

#### Resource Management Analysis
```sql
SELECT 
    CASE 
        WHEN endpoint LIKE '%facility%' THEN 'facility'
        WHEN endpoint LIKE '%surgeon%' THEN 'surgeon'
    END as resource_type,
    method,
    COUNT(*) as operation_count,
    AVG(execution_time_ms) as avg_response_time,
    COUNT(DISTINCT user_id) as unique_users
FROM request_logs 
WHERE endpoint IN ('/facility', '/facilities', '/surgeon', '/surgeons')
    AND timestamp >= DATE_SUB(NOW(), INTERVAL 7 DAY)
GROUP BY resource_type, method;
```

#### External API Performance
```sql
SELECT 
    DATE(timestamp) as date,
    COUNT(*) as total_validations,
    SUM(CASE WHEN response_status = 200 THEN 1 ELSE 0 END) as successful_validations,
    SUM(CASE WHEN response_status = 502 THEN 1 ELSE 0 END) as api_errors,
    AVG(execution_time_ms) as avg_response_time,
    MAX(execution_time_ms) as max_response_time
FROM request_logs 
WHERE endpoint = '/check_npi'
    AND timestamp >= DATE_SUB(NOW(), INTERVAL 30 DAY)
GROUP BY DATE(timestamp)
ORDER BY date DESC;
```

## Best Practices

### Development
1. **Always add logging to new endpoints** using the standard pattern
2. **Test logging functionality** in development environments
3. **Monitor log volume** to prevent storage issues
4. **Use appropriate log levels** for different environments

### Production
1. **Monitor log storage usage** and implement retention policies
2. **Set up alerting** on error rates and performance degradation
3. **Regular backup** of critical log data
4. **Performance tuning** based on log analytics

### Security
1. **Sanitize sensitive data** before logging
2. **Control access** to log data and analytics
3. **Encrypt log storage** for sensitive environments
4. **Regular audit** of logging system access

## Troubleshooting

### Common Issues

#### Logging Not Working
- Check database connectivity
- Verify log table exists and has correct schema
- Check for import errors in utility functions

#### Performance Impact
- Monitor database connection pool usage
- Consider async logging for high-volume endpoints
- Implement log batching for better performance

#### Storage Issues
- Implement log rotation and archival
- Monitor disk space usage
- Set up automated cleanup processes

### Debugging
- Enable debug logging for the logging system itself
- Check application logs for logging-related errors
- Verify network connectivity to log storage

## Future Enhancements

### Planned Features
- **Real-time Analytics**: Live dashboards for API monitoring
- **Machine Learning**: Anomaly detection in usage patterns
- **Advanced Filtering**: Complex log query capabilities
- **Export Functions**: Data export for external analysis

### Integration Opportunities
- **ELK Stack**: Elasticsearch, Logstash, Kibana integration
- **Grafana**: Advanced visualization and alerting
- **APM Tools**: Application Performance Monitoring integration
- **SIEM Systems**: Security Information and Event Management

## Support

For questions about the logging system:
1. Review this documentation
2. Check the monitoring utilities in `utils/monitoring.py`
3. Examine existing endpoint implementations for patterns
4. Test logging functionality in development environment

The logging system is designed to be comprehensive yet unobtrusive, providing valuable insights while maintaining system performance and reliability. 