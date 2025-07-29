# SurgiCase API Endpoints

This document provides a comprehensive list of all available API endpoints in the SurgiCase application.

## Table of Contents
- [Infrastructure Overview](#infrastructure-overview)
- [Case Management](#case-management)
- [User Management](#user-management)
- [Surgeon Management](#surgeon-management)
- [Facility Management](#facility-management)
- [Utility Endpoints](#utility-endpoints)
- [Health & Monitoring](#health--monitoring)
- [Backoffice](#backoffice)
- [Monitoring Infrastructure](#monitoring-infrastructure)
- [Scaling Infrastructure](#scaling-infrastructure)

---

## Infrastructure Overview

### Production Servers
- **Main SurgiCase API Server**: `172.31.38.136` (private)
- **Dedicated Monitoring Server**: `172.31.86.18` (private) / `3.83.225.230` (public)
- **VPC**: `vpc-0d0a4d7473692be39`
- **Security Group**: `sg-06718ecd804840607`

### Application Access
- **API Base URL**: `http://172.31.38.136:8000`
- **API Documentation**: `http://172.31.38.136:8000/docs`
- **Health Check**: `http://172.31.38.136:8000/health`
- **Metrics**: `http://172.31.38.136:8000/metrics`

### Monitoring Access
- **Prometheus**: `http://3.83.225.230:9090`
- **Grafana**: `http://3.83.225.230:3000` (admin / SurgiCase2025!)
- **Loki**: `http://3.83.225.230:3100`

---

## Case Management

### Get Case
- **Method:** `GET`
- **Path:** `/case`
- **Parameters:** `case_id` (string, required) - The case ID to retrieve
- **Description:** Retrieve case information by case_id

### Create Case
- **Method:** `POST`
- **Path:** `/case`
- **Body:** CaseCreate object
- **Description:** Create a new case with associated procedure codes

### Update Case
- **Method:** `PATCH`
- **Path:** `/case`
- **Body:** CaseUpdate object
- **Description:** Update fields in cases and replace procedure codes if provided

### Delete Case
- **Method:** `DELETE`
- **Path:** `/case`
- **Parameters:** `case_id` (string, required) - The case ID to delete
- **Description:** Delete (deactivate) case by case_id

### Bulk Update Case Status
- **Method:** `PATCH`
- **Path:** `/bulkupdatecasestatus`
- **Body:** BulkCaseStatusUpdate object containing:
  - `case_ids` (array of strings, required) - List of case IDs to update
  - `new_status` (integer, required) - The new status value to set
  - `force` (boolean, optional, default: false) - Allow backward status progression
- **Description:** Bulk update case status for multiple cases with validation to prevent backward progression unless forced

### Filter Cases
- **Method:** `GET`
- **Path:** `/casefilter`
- **Parameters:** 
  - `user_id` (string, required) - The user ID to retrieve cases for
  - `filter` (string, optional) - Comma-separated list of case_status values
- **Description:** Retrieve all cases for a user_id, filtered by case_status values

---

## User Management

### Get User
- **Method:** `GET`
- **Path:** `/user`
- **Parameters:** `user_id` (string, required) - The user ID to retrieve
- **Description:** Retrieve user information by user_id

### Create User
- **Method:** `POST`
- **Path:** `/user`
- **Body:** UserCreate object
- **Description:** Add a new user to the user_profile table

### Update User
- **Method:** `PATCH`
- **Path:** `/user`
- **Body:** UserUpdate object
- **Description:** Update user fields in user_profile

### Delete User
- **Method:** `DELETE`
- **Path:** `/user`
- **Parameters:** `user_id` (string, required) - The user ID to delete
- **Description:** Delete (deactivate) user by user_id

---

## Surgeon Management

### Get Surgeons
- **Method:** `GET`
- **Path:** `/surgeons`
- **Parameters:** `user_id` (string, required) - The user ID to retrieve surgeons for
- **Description:** Get all surgeons for a user_id

### Create Surgeon
- **Method:** `POST`
- **Path:** `/surgeon`
- **Body:** SurgeonCreate object
- **Description:** Add a new surgeon for a user

### Delete Surgeon
- **Method:** `DELETE`
- **Path:** `/surgeon`
- **Parameters:** `surgeon_id` (integer, required) - The surgeon ID to delete
- **Description:** Delete a surgeon by surgeon_id

---

## Facility Management

### Get Facilities
- **Method:** `GET`
- **Path:** `/facilities`
- **Parameters:** `user_id` (string, required) - The user ID to retrieve facilities for
- **Description:** Get all facilities for a user_id

### Create Facility
- **Method:** `POST`
- **Path:** `/facility`
- **Body:** FacilityCreate object
- **Description:** Add a new facility for a user

### Delete Facility
- **Method:** `DELETE`
- **Path:** `/facility`
- **Parameters:** `facility_id` (integer, required) - The facility ID to delete
- **Description:** Delete a facility by facility_id

---

## Utility Endpoints

### Check NPI
- **Method:** `GET`
- **Path:** `/check_npi`
- **Parameters:** `npi` (string, required) - 10-digit NPI number
- **Description:** Validate NPI and retrieve corrected provider name from CMS registry

### Get Document Types
- **Method:** `GET`
- **Path:** `/doctypes`
- **Description:** Get all document types

### Get CPT Codes
- **Method:** `GET`
- **Path:** `/cpt_codes`
- **Description:** Get all CPT codes

### Log Request
- **Method:** `POST`
- **Path:** `/log_request`
- **Body:** RequestLog object
- **Description:** Log API request details for monitoring and debugging

---

## Health & Monitoring

### Health Check
- **Method:** `GET`
- **Path:** `/health`
- **Description:** Comprehensive health check including database, AWS services, and system status

### Health Ready
- **Method:** `GET`
- **Path:** `/health/ready`
- **Description:** Kubernetes readiness probe endpoint

### Health Live
- **Method:** `GET`
- **Path:** `/health/live`
- **Description:** Kubernetes liveness probe endpoint

### Health Simple
- **Method:** `GET`
- **Path:** `/health/simple`
- **Description:** Simple health check endpoint

### Metrics
- **Method:** `GET`
- **Path:** `/metrics`
- **Description:** Prometheus metrics endpoint

### Metrics Summary
- **Method:** `GET`
- **Path:** `/metrics/summary`
- **Description:** Summary of key metrics

### Metrics Health
- **Method:** `GET`
- **Path:** `/metrics/health`
- **Description:** Health-related metrics

### Metrics System
- **Method:** `GET`
- **Path:** `/metrics/system`
- **Description:** System performance metrics

### Metrics Database
- **Method:** `GET`
- **Path:** `/metrics/database`
- **Description:** Database performance metrics

### Metrics Business
- **Method:** `GET`
- **Path:** `/metrics/business`
- **Description:** Business operation metrics

### Metrics Endpoints
- **Method:** `GET`
- **Path:** `/metrics/endpoints`
- **Description:** Endpoint usage metrics

### Metrics Self
- **Method:** `GET`
- **Path:** `/metrics/self`
- **Description:** Self-monitoring metrics

---

## Backoffice

### Get Cases by Status
- **Method:** `GET`
- **Path:** `/casesbystatus`
- **Parameters:** 
  - `user_id` (string, required) - The user ID making the request (must be user_type >= 10)
  - `filter` (string, optional) - Comma-separated list of case_status values
- **Description:** Retrieve all cases filtered by case_status values, only if the calling user has user_type >= 10

---

## Data Models

### CaseCreate
```json
{
  "case_id": "string",
  "user_id": "string",
  "case_date": "date",
  "patient": {
    "first": "string",
    "last": "string"
  },
  "ins_provider": "string",
  "surgeon_id": "integer",
  "facility_id": "integer",
  "procedure_codes": ["string"]
}
```

### CaseUpdate
```json
{
  "case_id": "string",
  "case_date": "date",
  "patient_first": "string",
  "patient_last": "string",
  "ins_provider": "string",
  "surgeon_id": "integer",
  "facility_id": "integer",
  "procedure_codes": ["string"]
}
```

### UserCreate
```json
{
  "user_id": "string",
  "user_email": "string",
  "first_name": "string",
  "last_name": "string",
  "addr1": "string",
  "addr2": "string",
  "city": "string",
  "state": "string",
  "zipcode": "string",
  "telephone": "string",
  "user_npi": "string",
  "referred_by_user": "string",
  "message_pref": "string",
  "states_licensed": "string",
  "documents": [
    {
      "document_type": "string",
      "document_name": "string"
    }
  ]
}
```

### UserUpdate
```json
{
  "user_id": "string",
  "user_email": "string",
  "first_name": "string",
  "last_name": "string",
  "addr1": "string",
  "addr2": "string",
  "city": "string",
  "state": "string",
  "zipcode": "string",
  "telephone": "string",
  "user_npi": "string",
  "referred_by_user": "string",
  "message_pref": "string",
  "states_licensed": "string",
  "documents": [
    {
      "document_type": "string",
      "document_name": "string"
    }
  ]
}
```

### SurgeonCreate
```json
{
  "user_id": "string",
  "first_name": "string",
  "last_name": "string"
}
```

### FacilityCreate
```json
{
  "user_id": "string",
  "facility_name": "string"
}
```

### RequestLog
```json
{
  "timestamp": "datetime",
  "user_id": "string",
  "endpoint": "string",
  "method": "string",
  "request_payload": "string",
  "query_params": "string",
  "response_status": "integer",
  "response_payload": "string",
  "execution_time_ms": "integer",
  "error_message": "string",
  "client_ip": "string"
}
```

---

## Authentication & Authorization

Most endpoints require a valid `user_id` parameter for authorization. The backoffice endpoints require `user_type >= 10` for access.

## Error Responses

All endpoints return standardized error responses:

- **400 Bad Request:** Invalid parameters or request format
- **404 Not Found:** Resource not found
- **422 Unprocessable Entity:** Validation errors
- **500 Internal Server Error:** Server-side errors
- **502 Bad Gateway:** External service errors

## Rate Limiting

The API includes comprehensive monitoring and may implement rate limiting based on usage patterns.

## Monitoring

All endpoints are monitored with:
- Request/response logging
- Performance metrics
- Business operation tracking
- Error tracking and alerting

### Dedicated Monitoring Infrastructure

The SurgiCase system utilizes a dedicated monitoring server for comprehensive observability:

**Monitoring Services:**
- **Prometheus** (`http://3.83.225.230:9090`)
  - Metrics collection and storage
  - Real-time alerting and monitoring
  - Service discovery for horizontal scaling
  - 90-day metric retention
  
- **Grafana** (`http://3.83.225.230:3000`)
  - Interactive dashboards and visualization
  - Pre-configured SurgiCase overview dashboard
  - Alert management and notification channels
  - Multi-instance monitoring support
  
- **Loki** (`http://3.83.225.230:3100`)
  - Centralized log aggregation
  - Structured log analysis
  - Integration with Grafana for log exploration
  - Real-time log streaming

**Monitoring Coverage:**
- Application performance metrics (response times, error rates)
- Business metrics (case creation, payment processing, user activity)
- System metrics (CPU, memory, disk usage)
- Database metrics (connection pools, query performance)
- Health checks (database connectivity, AWS services)

---

## Monitoring Infrastructure

### Prometheus Endpoints

**Target Monitoring:**
- **Targets**: `http://3.83.225.230:9090/targets`
  - View all monitored services and their health status
  - Service discovery status for scaled instances
  
- **Configuration**: `http://3.83.225.230:9090/config`
  - Current Prometheus configuration
  - Scrape configurations and intervals

**Query Interface:**
- **Query**: `http://3.83.225.230:9090/graph`
  - Interactive metric queries and visualization
  - PromQL query interface
  
- **API Query**: `http://3.83.225.230:9090/api/v1/query?query=<metric>`
  - Programmatic metric access
  - Example: `up{job="surgicase-api"}`

**Common Metrics Queries:**
```
# Application health across all instances
up{job=~"surgicase-api.*"}

# Request rate per instance
rate(http_requests_total[5m])

# Database connections
mysql_global_status_threads_connected

# Error rate
rate(http_requests_total{status=~"5.."}[5m])
```

### Grafana Dashboards

**Main Dashboard:** `http://3.83.225.230:3000/d/surgicase-overview`
- Application performance overview
- Request rates and response times
- Database performance metrics
- Business operation metrics
- System resource utilization

**Dashboard Features:**
- Real-time metric visualization
- Customizable time ranges
- Alert integration
- Multi-instance support for scaling
- Drill-down capabilities

### Loki Log Aggregation

**Log Query Interface:** `http://3.83.225.230:3000/explore`
- Structured log search and analysis
- Real-time log streaming
- Log correlation with metrics

**Log Sources:**
- SurgiCase application logs
- System logs from monitoring server
- Future: Centralized application logs from all instances

---

## Scaling Infrastructure

### Service Discovery Framework

The monitoring infrastructure includes service discovery for horizontal scaling:

**Instance Registration:**
```bash
# Register new SurgiCase instances for monitoring
sudo /opt/register-instance.sh <private_ip> 8000 production
```

**Scaling Targets:**
- **Target Group**: Prometheus automatically discovers new instances
- **Dynamic Configuration**: `/etc/prometheus/targets/surgicase-instances.yml`
- **Health Monitoring**: Automatic health check integration

### Load Balancer Integration (When Deployed)

**Application Load Balancer:**
- **Health Check Path**: `/health/ready`
- **Health Check Interval**: 30 seconds
- **Healthy Threshold**: 2 consecutive successes
- **Unhealthy Threshold**: 3 consecutive failures

**Target Group Configuration:**
- **Protocol**: HTTP
- **Port**: 8000
- **Health Check Matcher**: HTTP 200

### Multi-Instance Monitoring

**Instance Identification:**
- Instances automatically tagged with cluster and environment labels
- Prometheus scrapes all instances in the target group
- Grafana dashboards aggregate metrics across all instances

**Scaling Metrics:**
```
# Total instances running
count(up{job=~"surgicase-api.*"})

# Instance-specific metrics
up{job=~"surgicase-api.*"} by (instance)

# Aggregate request rate across all instances
sum(rate(http_requests_total[5m]))
```

### Monitoring Server Capacity

**Current Capacity:**
- **Monitoring Server**: m8g.xlarge (4 vCPU, 16GB RAM, 256GB storage)
- **Supported Instances**: Up to ~50 SurgiCase instances
- **Metric Retention**: 90 days
- **Storage**: 10GB allocated for metrics

**Scaling Considerations:**
- Monitoring server can handle significant horizontal scaling
- For extreme scale (100+ instances), consider Prometheus federation
- Grafana performance scales well with current configuration

--- 