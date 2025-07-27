# Created: 2025-01-27
# Last Modified: 2025-07-27 04:02:14

# SurgiCase Management System

A comprehensive FastAPI-based REST API for surgical case management, designed for healthcare providers to manage users, cases, facilities, and surgeons with integrated monitoring, S3 storage, automated scheduling, and QuickBooks export capabilities.

## 🏥 Overview

SurgiCase is a full-featured surgical case management system that provides:

- **User & Case Management**: Complete CRUD operations for users, cases, facilities, and surgeons
- **Healthcare Integration**: NPI validation, CPT codes, and medical document management
- **Automated Workflows**: Scheduled status updates and data synchronization
- **Cloud Storage**: S3 integration for secure document and report storage
- **Financial Integration**: QuickBooks export for accounting and billing
- **Comprehensive Monitoring**: Prometheus metrics, structured logging, and health checks
- **Backoffice Tools**: Administrative functions for case and user management

## 🚀 Features

### Core Management
- **User Management**: Complete user profiles with NPI validation and licensing
- **Case Management**: Surgical case tracking with procedure codes and patient information
- **Facility Management**: Hospital and surgical facility tracking
- **Surgeon Management**: Surgeon profiles with NPI validation
- **Document Management**: File uploads and storage with S3 integration

### Healthcare Integration
- **NPI Validation**: Real-time NPI lookup and validation via CMS registry
- **CPT Codes**: Comprehensive procedure code management
- **Document Types**: Medical document categorization and management
- **Provider Verification**: Automated provider information validation

### Automation & Scheduling
- **Weekly Status Updates**: Automated case status progression
- **NPI Data Synchronization**: Weekly updates from CMS database
- **Payment Processing**: Automated payment status updates
- **Data Archival**: Automatic cleanup and archival processes

### Financial & Reporting
- **Provider Payment Reports**: Comprehensive payment tracking and reporting
- **QuickBooks Integration**: Direct export to QuickBooks for accounting
- **Financial Metrics**: Payment tracking and business intelligence
- **Export Capabilities**: CSV and IIF format exports

### Monitoring & Observability
- **Prometheus Metrics**: Comprehensive operational monitoring
- **Structured Logging**: JSON-formatted logs for analysis
- **Health Checks**: Multi-level health monitoring
- **Performance Tracking**: Request/response timing and error tracking
- **Business Metrics**: Case creation, payment, and user activity tracking

### Cloud Integration
- **AWS S3 Storage**: Secure document and report storage
- **AWS Secrets Manager**: Secure credential management
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
fpdf
Pillow
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
- **Health Check**: http://localhost:8000/health

## 📚 API Endpoints

### Case Management
- `GET /case` - Retrieve case by ID
- `POST /case` - Create new case
- `PATCH /case` - Update case information
- `DELETE /case` - Delete case (soft delete)
- `GET /casefilter` - Filter cases by status
- `PATCH /bulkupdatecasestatus` - Bulk update case status

### User Management
- `GET /user` - Retrieve user by ID
- `POST /user` - Create new user
- `PATCH /user` - Update user information
- `DELETE /user` - Delete user (soft delete)

### Facility Management
- `GET /facilities` - Get facilities for user
- `POST /facility` - Create new facility
- `DELETE /facility` - Delete facility

### Surgeon Management
- `GET /surgeons` - Get surgeons for user
- `POST /surgeon` - Create new surgeon
- `DELETE /surgeon` - Delete surgeon

### Utility Endpoints
- `GET /check_npi` - Validate NPI number
- `GET /doctypes` - Get document types
- `GET /cpt_codes` - Get CPT codes
- `POST /log_request` - Log API request

### Health & Monitoring
- `GET /health` - Comprehensive health check
- `GET /health/ready` - Kubernetes readiness probe
- `GET /health/live` - Kubernetes liveness probe
- `GET /metrics` - Prometheus metrics
- `GET /metrics/summary` - Human-readable metrics

### Backoffice
- `GET /casesbystatus` - Get cases by status (admin only)
- `GET /users` - Get all users (admin only)
- `GET /casedashboarddata` - Dashboard data (admin only)

### Reports & Exports
- `GET /provider_payment_report` - Provider payment report
- `GET /quickbooks-vendors-csv` - QuickBooks vendors export
- `GET /quickbooks-transactions-iif` - QuickBooks transactions export

## 🔧 Configuration

### Environment Variables
- `ENABLE_SCHEDULER` - Enable automated scheduling (true/false)
- `AWS_REGION` - AWS region for services
- `LOG_LEVEL` - Logging level (DEBUG, INFO, WARNING, ERROR)

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
- **Simple health**: Basic service availability
- **Database health**: Database connectivity and performance
- **AWS health**: S3 and Secrets Manager connectivity
- **System health**: Resource utilization and performance

### Logging
- **Structured logging**: JSON format for easy parsing
- **Request logging**: Complete request/response tracking
- **Error logging**: Detailed error information with stack traces
- **Business logging**: Important business events and metrics

## 🔄 Scheduled Tasks

### Weekly Automation
- **Monday 08:00 UTC**: Pending payment updates (status 10 → 15)
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
- Provider payment reports
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
│   ├── utility/            # Utility endpoints (NPI, CPT codes)
│   ├── backoffice/         # Administrative endpoints
│   ├── reports/            # Report generation endpoints
│   └── exports/            # Export endpoints (QuickBooks)
├── utils/                   # Utility modules
│   ├── monitoring.py       # Monitoring and metrics
│   ├── scheduler.py        # Automated scheduling
│   ├── s3_storage.py       # S3 integration
│   ├── pay_amount_calculator.py  # Payment calculations
│   └── logo_manager.py     # Logo management
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

### Data Protection
- AWS Secrets Manager for credential storage
- S3 encryption for document storage
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

### Docker Deployment (Optional)
```bash
# Build image
docker build -t surgicase .

# Run container
docker run -p 8000:8000 surgicase
```

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
- Database connection pooling
- Prometheus metrics for performance monitoring
- Request/response timing tracking
- Efficient query optimization
- Caching for frequently accessed data

### Scalability
- Stateless API design
- Horizontal scaling support
- Database connection management
- Resource monitoring and alerting

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

- **v0.8.0**: Current version with comprehensive monitoring, S3 integration, and QuickBooks export
- **v0.7.0**: Added scheduling and automation features
- **v0.6.0**: Implemented S3 integration and enhanced reporting
- **v0.5.0**: Added monitoring and metrics
- **v0.4.0**: Enhanced case management and backoffice features
- **v0.3.0**: Added facility and surgeon management
- **v0.2.0**: Basic user and case management
- **v0.1.0**: Initial release

---

**SurgiCase Management System** - Comprehensive surgical case management for healthcare providers. 