# Created: 2025-01-27
# Last Modified: 2025-08-20 08:38:53
# Version: 0.9.0

# SurgiCase Management System

A comprehensive FastAPI-based REST API for surgical case management, designed for healthcare providers to manage users, cases, facilities, and surgeons with integrated monitoring, S3 storage, automated scheduling, password-protected individual provider reports, and QuickBooks export capabilities.

## 🏥 Overview

SurgiCase is a full-featured surgical case management system that provides:

- **User & Case Management**: Complete CRUD operations for users, cases, facilities, and surgeons
- **Healthcare Integration**: NPI validation, CPT codes, and medical document management
- **Automated Workflows**: Scheduled status updates and data synchronization
- **Secure Reporting**: Password-protected individual provider reports with data isolation
- **Cloud Storage**: S3 integration for secure document and report storage
- **Financial Integration**: QuickBooks export for accounting and billing
- **Comprehensive Monitoring**: Prometheus metrics, structured logging, and health checks
- **Backoffice Tools**: Administrative functions for case and user management
- **Advanced Search**: Facility and surgeon search capabilities
- **Dashboard Analytics**: Real-time case and user analytics for administrative oversight

## 🚀 Features

### Core Management
- **User Management**: Complete user profiles with NPI validation and licensing
- **Case Management**: Surgical case tracking with procedure codes and patient information
- **Facility Management**: Hospital and surgical facility tracking with search capabilities
- **Surgeon Management**: Surgeon profiles with NPI validation and search functionality
- **Document Management**: File uploads and storage with S3 integration and compression

### Healthcare Integration
- **NPI Validation**: Real-time NPI lookup and validation via CMS registry
- **CPT Codes**: Comprehensive procedure code management
- **Document Types**: Medical document categorization and management
- **Provider Verification**: Automated provider information validation
- **Timezone Support**: Comprehensive timezone handling for multi-location operations

### Automation & Scheduling
- **Weekly Status Updates**: Automated case status progression
- **NPI Data Synchronization**: Weekly updates from CMS database
- **Payment Processing**: Automated payment status updates
- **Data Archival**: Automatic cleanup and archival processes

### Financial & Reporting
- **Provider Payment Reports**: Comprehensive payment tracking and reporting
- **Individual Provider Reports**: Password-protected PDFs sent to each provider with only their cases
- **QuickBooks Integration**: Direct export to QuickBooks for accounting
- **Financial Metrics**: Payment tracking and business intelligence
- **Export Capabilities**: CSV and IIF format exports

### Administrative Tools
- **Dashboard Analytics**: Real-time case and user distribution analytics
- **Bulk Operations**: Bulk case status updates with validation
- **User Environment Management**: Comprehensive user data retrieval
- **Case Image Management**: Bulk download and compression of case files
- **Administrative Reporting**: Comprehensive business intelligence dashboards

### Monitoring & Observability
- **Prometheus Metrics**: Comprehensive operational monitoring
- **Structured Logging**: JSON-formatted logs for analysis
- **Health Checks**: Multi-level health monitoring
- **Performance Tracking**: Request/response timing and error tracking
- **Business Metrics**: Case creation, payment, and user activity tracking

### Cloud Integration
- **AWS S3 Storage**: Secure document and report storage
- **AWS Secrets Manager**: Centralized secrets management with intelligent caching
- **Cloud Monitoring**: Integration with AWS monitoring services

## 📋 Requirements

### System Requirements
- Python 3.7+
- MySQL 5.7+ or MySQL 8.0+
- AWS Account (for S3, Secrets Manager, and monitoring)

### Python Dependencies
```
boto3
pymysql
fastapi
uvicorn
fpdf2
Pillow
pypdf
prometheus-fastapi-instrumentator
schedule
pydantic
email-validator
```

## 🛠️ Installation

### 1. Clone the Repository
```bash
git clone <your-repo-url>
cd surgicase
```

### 2. Create Virtual Environment
```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. AWS Configuration
Configure AWS credentials and create necessary secrets in AWS Secrets Manager:

#### Database Secret (`surgicase/database`)
```json
{
  "host": "your-rds-endpoint",
  "port": 3306,
  "database": "surgicase",
  "user": "your-db-user",
  "password": "your-db-password"
}
```

#### S3 Secret (`surgicase/s3-user-reports`)
```json
{
  "bucket_name": "your-s3-bucket",
  "region": "us-east-1",
  "folder_prefix": "reports/provider-payments/",
  "encryption": "AES256",
  "retention_days": 90
}
```

### 5. Database Setup
Create the MySQL database and run the necessary migrations. The system uses the following main tables:
- `user_profile` - User information and credentials
- `cases` - Surgical case data
- `case_procedure_codes` - Procedure codes for cases
- `facilities` - Surgical facilities
- `surgeons` - Surgeon information
- `npi_data` - NPI registry data

## 🚀 Running the Application

### Development Mode
```bash
python main.py
```

### Production Mode
```bash
# Enable scheduler for automated tasks
export ENABLE_SCHEDULER=true
python main.py
```

### Standalone Scheduler (Optional)
```bash
python scheduler_service.py
```

The application will be available at:
- **API**: http://localhost:8000
- **Documentation**: http://localhost:8000/docs
- **Metrics**: http://localhost:8000/metrics
- **Health Check**: http://localhost:8000/health (comprehensive)
- **System Status**: http://localhost:8000/health/system (simplified)

## 📚 API Endpoints

### Case Management
- `GET /case` - Retrieve case by ID
  - Parameters: `case_id` (string, required)
- `POST /case` - Create new case
  - Body: CaseCreate object
- `PATCH /case` - Update case information
  - Body: CaseUpdate object
- `DELETE /case` - Delete case (soft delete)
  - Parameters: `case_id` (string, required)
- `GET /casefilter` - Filter cases by status
  - Parameters: `user_id` (string, required), `filter` (string, optional)

### User Management
- `GET /user` - Retrieve user by ID
  - Parameters: `user_id` (string, required)
- `POST /user` - Create new user
  - Body: UserCreate object
- `PATCH /user` - Update user information
  - Body: UserUpdate object
- `DELETE /user` - Delete user (soft delete)
  - Parameters: `user_id` (string, required)

### Facility Management
- `GET /facilities` - Get facilities for user
  - Parameters: `user_id` (string, required)
- `POST /facility` - Create new facility
  - Body: FacilityCreate object
- `DELETE /facility` - Delete facility
  - Parameters: `facility_id` (integer, required)
- `GET /search_facility` - Search facilities by name
  - Parameters: `user_id` (string, required), `search_term` (string, required)

### Surgeon Management
- `GET /surgeons` - Get surgeons for user
  - Parameters: `user_id` (string, required)
- `POST /surgeon` - Create new surgeon
  - Body: SurgeonCreate object
- `DELETE /surgeon` - Delete surgeon
  - Parameters: `surgeon_id` (integer, required)
- `GET /search_surgeon` - Search surgeons by name
  - Parameters: `user_id` (string, required), `search_term` (string, required)

### Utility Endpoints
- `GET /check_npi` - Validate NPI number
  - Parameters: `npi` (string, required)
- `GET /doctypes` - Get document types
- `GET /cpt_codes` - Get CPT codes
- `POST /log_request` - Log API request
- `GET /bugs` - Retrieve open bug reports
  - Parameters: `user_id` (string, required)
- `POST /bugs` - Submit bug reports with environment data
  - Parameters: `user_id` (string, required)
  - Body: Bug report object with environment data
- `GET /user_environment` - Get comprehensive user environment data
  - Parameters: `user_id` (string, required)
- `GET /timezones` - Get all available timezones with UTC offsets
- `GET /lists` - Get various system lists (admin only)
  - Parameters: `user_id` (string, required), `list_type` (string, required)

#### Bug Reporting Endpoints
The `/bugs` endpoints provide comprehensive bug reporting functionality:

**GET /bugs Features:**
- Returns all bug reports with status not equal to 'Closed'
- Includes bug_id, title, description, calling_page, status, priority, created_ts
- Results ordered by creation date (newest first)
- Provides total count of open bugs
- Requires user_id parameter for authorization

**POST /bugs Features:**
- Validates user_id exists in user_profile table
- Captures comprehensive environment data including user profile, case statuses, surgeons, facilities
- Stores bug reports in dedicated `bugs` table
- Includes Prometheus metrics and request logging

### Health & Monitoring
- `GET /health` - Comprehensive health check with all AWS services
- `GET /health/system` - Simplified system status (perfect for user login)
- `GET /health/ready` - Kubernetes readiness probe
- `GET /health/live` - Kubernetes liveness probe
- `GET /metrics` - Prometheus metrics endpoint
- `GET /metrics/summary` - Human-readable metrics summary
- `GET /metrics/health` - Metrics system health check
- `GET /system_metrics` - System resource metrics
- `GET /database_metrics` - Database performance metrics
- `GET /business_metrics` - Business operation metrics
- `GET /endpoint_metrics` - API endpoint performance metrics
- `GET /metrics_self_monitoring` - Metrics system self-monitoring

### Backoffice (Administrative)
- `GET /casesbystatus` - Get cases by status (admin only)
  - Parameters: `user_id` (string, required), `status` (integer, optional)
- `GET /users` - Get all users (admin only)
  - Parameters: `user_id` (string, required)
- `PATCH /bulkupdatecasestatus` - Bulk update case status
  - Body: BulkCaseStatusUpdate object with case_ids, new_status, force flag
- `GET /case_dashboard_data` - Comprehensive case analytics dashboard
  - Parameters: `user_id` (string, required), `start_date` (optional), `end_date` (optional)
- `GET /user_dashboard_data` - User analytics dashboard
  - Parameters: `user_id` (string, required)
- `GET /case_images` - Bulk download and compress case files
  - Parameters: `user_id` (string, required), `case_ids` (array, required)
- `GET /build_dashboard` - Build comprehensive dashboard data
  - Parameters: `user_id` (string, required)

### Reports & Exports
- `GET /provider_payment_report` - Consolidated provider payment report
  - Parameters: Various date and filtering options
- `GET /provider_payment_summary_report` - Summary provider payment report
  - Parameters: Various date and filtering options
- `GET /quickbooks-vendors-csv` - QuickBooks vendors export
- `GET /quickbooks-transactions-iif` - QuickBooks transactions export
- `GET /case_export` - Export case data in various formats
  - Parameters: Export format and filtering options

## 🔧 Configuration

### Environment Variables

#### Required
- `AWS_REGION` - AWS region for services (default: us-east-1)

#### Optional
- `ENABLE_SCHEDULER` - Enable automated scheduling (true/false, default: false)
- `LOG_LEVEL` - Logging level (DEBUG, INFO, WARNING, ERROR)

#### Database Connection Pooling
- `DB_POOL_SIZE` - Base connection pool size (default: 15)
- `DB_POOL_MAX_OVERFLOW` - Additional connections when pool full (default: 10)
- `DB_POOL_TIMEOUT` - Timeout waiting for connection in seconds (default: 10)

**Connection Pool Benefits:**
- **5-minute credential caching** eliminates repeated AWS Secrets Manager calls (saves 200-500ms per request)
- **Connection reuse** reduces database connection overhead (~50-100ms per request)
- **Automatic validation** ensures connection health with auto-reconnection
- **Configurable sizing** for different load patterns and concurrent users

### AWS Services
- **Secrets Manager**: Secure credential storage
- **S3**: Document and report storage
- **CloudWatch**: Logging and monitoring (optional)

## 📊 Monitoring

### Prometheus Metrics
The application exposes comprehensive metrics at `/metrics`:
- **Request metrics**: Response times, error rates, throughput
- **Business metrics**: Case creation, payment processing, user activity
- **System metrics**: CPU, memory, disk usage
- **Database metrics**: Connection pools, query performance

### Health Checks
The system provides comprehensive health monitoring with 5-minute caching for optimal performance:

#### Critical Services (failure = system unhealthy)
- **Database health**: RDS connectivity and query performance
- **AWS Secrets Manager**: Credential access and authentication
- **API Gateway**: Gateway status and accessibility  
- **EC2 Instances**: Instance status and system health

#### Non-Critical Services (failure = system degraded)
- **S3 Storage**: Bucket accessibility and read operations
- **Amplify**: Application deployment status
- **System Resources**: CPU, memory, and disk utilization

#### Endpoints
- **`/health`**: Full detailed health check with all components
- **`/health/system`**: Simplified status for user login (cached, fast)
- **`/health/ready`**: Kubernetes readiness (critical services only)
- **`/health/live`**: Kubernetes liveness (basic availability)

#### Caching Strategy
- **5-minute cache** reduces AWS API calls and improves response time
- Perfect for **user login checks** - fast and comprehensive
- Automatic cache refresh when health status changes
- Per-instance caching for horizontal scaling

### Logging
- **Structured logging**: JSON format for easy parsing
- **Request logging**: Complete request/response tracking
- **Error logging**: Detailed error information with stack traces
- **Business logging**: Important business events and metrics

## 🖥️ Monitoring Infrastructure

### Dedicated Monitoring Server
The SurgiCase system utilizes a dedicated monitoring server for comprehensive observability and scalability:

**Server Configuration:**
- **Monitoring Server**: `172.31.86.18` (private) / `3.83.225.230` (public)
- **Main SurgiCase Server**: `172.31.38.136` (private)
- **Instance Type**: m8g.xlarge (4 vCPU, 16GB RAM, 256GB storage)
- **OS**: Ubuntu 24.04.2 LTS
- **VPC**: vpc-0d0a4d7473692be39
- **Security Group**: sg-06718ecd804840607

### Monitoring Services Access
- **Prometheus**: http://3.83.225.230:9090
  - Metrics collection and alerting
  - Targets monitoring and service discovery
  - Remote data collection from main SurgiCase server
- **Grafana**: http://3.83.225.230:3000
  - Interactive dashboards and visualization
  - Login: admin / SurgiCase2025!
  - Pre-configured SurgiCase overview dashboard
- **Loki**: http://3.83.225.230:3100
  - Centralized log aggregation
  - Remote log collection from applications
  - Integration with Grafana for log exploration

### Monitoring Features
- **Remote Monitoring**: Dedicated server monitors main application server
- **Horizontal Scaling Ready**: Service discovery framework for multiple instances
- **High Availability**: Separate monitoring infrastructure ensures uptime visibility
- **Comprehensive Coverage**: Application metrics, system metrics, and logs
- **Historical Data**: 90-day metric retention and log storage
- **Alerting**: Prometheus alerts with Grafana notification channels

### Service Discovery
The monitoring infrastructure includes a service discovery framework for horizontal scaling:
```bash
# Register new SurgiCase instances
sudo /opt/register-instance.sh <private_ip> 8000 production
```

This allows automatic monitoring of additional SurgiCase instances as the system scales.

## 🔄 Scheduled Tasks

### Weekly Automation
- **Monday 08:00 UTC**: Pending payment updates (status 10 → 15)
- **Monday 09:00 UTC**: Consolidated provider payment report generation and email
- **Monday 10:00 UTC**: Individual password-protected provider reports sent to each provider
- **Tuesday 08:00 UTC**: NPI data synchronization from CMS
- **Thursday 08:00 UTC**: Payment completion updates (status 15 → 20)

### NPI Data Management
- Automatic download from CMS National Provider Identifier database
- Duplicate prevention and data validation
- Automatic archival of old data
- Search index updates

## 💾 S3 Integration

### Document Storage
- Automatic upload of generated reports to S3
- Metadata tagging for easy retrieval
- Configurable retention policies
- Secure encryption (AES256)

### Report Storage
- Consolidated provider payment reports
- Individual password-protected provider reports
- QuickBooks export files
- System logs and metrics
- Backup and archival data

## 💰 QuickBooks Integration

### Export Formats
- **Vendors CSV**: Provider information for QuickBooks vendor setup
- **Transactions IIF**: Payment transactions in QuickBooks native format

### Features
- Automatic account creation (Medical Expenses, Accounts Payable)
- Vendor setup with NPI as Tax ID
- Transaction details with procedure codes
- 1099 reporting compliance

## 🔐 Password-Protected Reports

### Individual Provider Reports
- Each provider receives a password-protected PDF containing only their cases
- Password format: `lastname_npi` (e.g., "smith_1234567890")
- Passwords are communicated securely via email [[memory:5531137]]
- Reports are generated weekly and stored in S3 with metadata

### Security Features
- AES encryption for PDF protection
- Provider data isolation ensures no cross-provider data exposure
- Temporary file cleanup prevents unprotected PDF persistence
- Unique passwords per provider for enhanced security

## 🧪 Testing

### Running Tests
```bash
# Install test dependencies
pip install -r test_requirements.txt

# Run all tests
python -m pytest tests/

# Run specific test modules
python test_monitoring.py
python test_s3_integration.py
python test_pay_amount_calculator.py
```

### Test Coverage
- Monitoring functionality
- S3 integration
- Payment calculations
- Logo functionality
- Request logging

## 📁 Project Structure

```
surgicase/
├── core/                    # Core database and models
├── endpoints/               # API endpoints by category
│   ├── case/               # Case management endpoints
│   ├── user/               # User management endpoints
│   ├── facility/           # Facility management endpoints
│   ├── surgeon/            # Surgeon management endpoints
│   ├── utility/            # Utility endpoints (NPI, CPT codes, timezones, lists)
│   ├── backoffice/         # Administrative endpoints
│   ├── reports/            # Report generation endpoints
│   ├── exports/            # Export endpoints (QuickBooks, cases)
│   ├── health.py           # Health check endpoints
│   └── metrics.py          # Monitoring metrics endpoints
├── utils/                   # Utility modules
│   ├── monitoring.py       # Monitoring and metrics
│   ├── scheduler.py        # Automated scheduling
│   ├── s3_storage.py       # S3 integration
│   ├── pay_amount_calculator.py  # Payment calculations
│   ├── logo_manager.py     # Logo management
│   ├── compress_pic.py     # Image compression
│   └── compress_pdf.py     # PDF compression
├── monitoring/             # Monitoring configuration
│   ├── grafana/           # Grafana dashboards
│   ├── prometheus/        # Prometheus configuration
│   └── loki/              # Log aggregation
├── tests/                  # Test files
├── assets/                 # Static assets (logos)
├── main.py                 # Main FastAPI application
├── scheduler_service.py    # Standalone scheduler service
└── requirements.txt        # Python dependencies
```

## 🔒 Security

### Authentication & Authorization
- User-based authentication via `user_id` parameter
- Role-based access control for administrative functions
- NPI validation for healthcare provider verification
- User type-based access restrictions (admin functions require user_type >= 10)

### Data Protection
- AWS Secrets Manager for credential storage
- S3 encryption for document storage
- Password-protected PDF reports with provider-specific passwords
- Provider data isolation (each provider sees only their own cases)
- Database connection security
- Input validation and sanitization

### Compliance
- Healthcare data protection standards
- Audit logging for all operations
- Secure document handling
- NPI compliance for provider verification

## 🚀 Deployment

### Production Deployment
1. **Database Setup**: Configure MySQL RDS instance
2. **AWS Configuration**: Set up S3 bucket and Secrets Manager
3. **Application Deployment**: Deploy to EC2, ECS, or similar
4. **Monitoring Setup**: Configure Prometheus, Grafana, and Loki
5. **SSL/TLS**: Configure HTTPS with proper certificates

### Systemd Service
```ini
[Unit]
Description=SurgiCase API Service
After=network.target

[Service]
Type=simple
User=surgicase
WorkingDirectory=/opt/surgicase
Environment=ENABLE_SCHEDULER=true
ExecStart=/opt/surgicase/venv/bin/python main.py
Restart=always

[Install]
WantedBy=multi-user.target
```

## 📈 Performance

### Optimization Features
- **Database connection pooling** with credential caching (4-hour AWS Secrets Manager cache for DB secrets, 1-hour for others)
- **Centralized secrets management** with 60-80% reduction in AWS API calls
- **Connection reuse** eliminates ~200-500ms overhead per request
- **Intelligent secrets caching** improves multi-secret request performance by 200-500ms
- Prometheus metrics for performance monitoring
- Request/response timing tracking
- Efficient query optimization
- Caching for frequently accessed data
- Image and PDF compression for reduced storage and transfer costs

### Scalability
- Stateless API design
- Horizontal scaling support
- Database connection management
- Resource monitoring and alerting
- Service discovery framework for multi-instance deployments

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests for new functionality
5. Submit a pull request

## 📄 License

This project is proprietary software. All rights reserved.

## 🆘 Support

For support and questions:
- Check the documentation in the `/docs` directory
- Review the monitoring dashboards for system status
- Contact the development team

## 🔄 Version History

- **v0.9.0**: Enhanced administrative tools, search capabilities, comprehensive dashboard analytics, image management, and timezone support
- **v0.8.1**: Individual password-protected provider reports and enhanced security
- **v0.8.0**: Comprehensive monitoring, S3 integration, and QuickBooks export
- **v0.7.0**: Added scheduling and automation features
- **v0.6.0**: Implemented S3 integration and enhanced reporting
- **v0.5.0**: Added monitoring and metrics
- **v0.4.0**: Enhanced case management and backoffice features
- **v0.3.0**: Added facility and surgeon management
- **v0.2.0**: Basic user and case management
- **v0.1.0**: Initial release

---

**SurgiCase Management System v0.9.0** - Comprehensive surgical case management for healthcare providers.