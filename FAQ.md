# SurgiCase Management System - Frequently Asked Questions (FAQ)

## Table of Contents
1. [General Questions](#general-questions)
2. [Getting Started](#getting-started)
3. [User Management & Authentication](#user-management--authentication)
4. [Case Management](#case-management)
5. [User Types & Permissions](#user-types--permissions)
6. [Technical Issues & Troubleshooting](#technical-issues--troubleshooting)
7. [API Usage](#api-usage)
8. [Data Management](#data-management)
9. [Reporting & Analytics](#reporting--analytics)
10. [Integration & Deployment](#integration--deployment)

---

## General Questions

### What is SurgiCase?
SurgiCase is a comprehensive FastAPI-based REST API for surgical case management, designed for healthcare providers to manage users, cases, facilities, and surgeons with integrated monitoring, S3 storage, automated scheduling, password-protected individual provider reports, and QuickBooks export capabilities.

### What are the main features of SurgiCase?
- **User & Case Management**: Complete CRUD operations for users, cases, facilities, and surgeons
- **Healthcare Integration**: NPI validation, CPT codes, and medical document management
- **Automated Workflows**: Scheduled status updates and data synchronization
- **Secure Reporting**: Password-protected individual provider reports with data isolation
- **Cloud Storage**: S3 integration for secure document and report storage
- **Financial Integration**: QuickBooks export for accounting and billing
- **Comprehensive Monitoring**: Prometheus metrics, structured logging, and health checks
- **Backoffice Tools**: Administrative functions for case and user management

### Who can use SurgiCase?
SurgiCase is designed for healthcare providers including:
- Healthcare providers and doctors
- Group administrators
- Case administrators
- User administrators
- Global administrators
- System administrators

Each user type has different permission levels and access to different features.

---

## Getting Started

### What are the system requirements?
- **Operating System**: Linux (Ubuntu 24.04+ recommended)
- **Python**: Python 3.8+
- **Database**: MySQL 5.7+ or MySQL 8.0+
- **Cloud Services**: AWS Account (for S3, Secrets Manager, and monitoring)
- **Hardware**: Minimum 4GB RAM, 256GB storage for production deployments

### How do I install SurgiCase?

1. **Clone the Repository**:
   ```bash
   git clone <your-repo-url>
   cd surgicase
   ```

2. **Create Virtual Environment**:
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure AWS**: Set up AWS Secrets Manager with database and S3 credentials

5. **Set Up Database**: Create MySQL database and run migrations

### How do I start the application?

**Development Mode**:
```bash
python main.py
```

**Production Mode**:
```bash
export ENABLE_SCHEDULER=true
python main.py
```

The application will be available at:
- **API**: http://localhost:8000
- **Documentation**: http://localhost:8000/docs
- **Health Check**: http://localhost:8000/health

---

## User Management & Authentication

### How does authentication work in SurgiCase?
SurgiCase uses user-based authentication via `user_id` parameter. There are no traditional login sessions - instead, each API request requires a valid `user_id` that exists in the `user_profile` table with `active = 1`.

### What happens if I can't access my account?
If you can't access your account:
1. Verify your `user_id` is correct
2. Ensure your account is active (not deactivated)
3. Contact your system administrator to check your user profile status
4. Check if your user type has sufficient permissions for the action you're trying to perform

### How do I update my user profile?
Use the `PATCH /user` endpoint with your user information. You can update:
- Personal information (name, address, phone)
- Professional information (NPI, licensed states)
- Communication preferences
- Documents

### What is an NPI and why do I need it?
NPI (National Provider Identifier) is a unique identifier for healthcare providers in the US. SurgiCase validates NPIs against the CMS registry and uses them for:
- Provider verification
- Healthcare compliance
- Reporting and billing processes

---

## Case Management

### How do I create a new surgical case?
Use the `POST /case` endpoint with case information including:
- Patient information (first name, last name)
- Case date
- Insurance provider
- Surgeon and facility IDs
- Procedure codes

### What are case statuses and how do they work?
Case statuses represent the lifecycle of a surgical case:
- **0**: Draft/Initial
- **1**: Submitted
- **10**: Ready for billing
- **15**: Pending payment
- **20**: Paid/Completed
- And higher values for various billing and settlement stages

Case statuses automatically progress based on business rules. For example, a case moves from status 0 to 1 when it has both demo_file and note_file uploaded plus at least one procedure code.

### Why can't I see certain case statuses?
Your user profile has a `max_case_status` setting that limits which case statuses you can view. This is for security and workflow control. Contact your administrator if you need access to higher case statuses.

### How do I upload files to a case?
Files are typically uploaded via the case update endpoint (`PATCH /case`) by providing file paths in the `demo_file`, `note_file`, or `misc_file` fields. The actual file upload to S3 storage is handled separately.

### What happens when I update procedure codes?
When you update procedure codes on a case:
1. All existing procedure codes are replaced with the new list
2. The case's pay amount is automatically recalculated
3. Case status may be automatically updated based on business rules
4. Duplicate procedure codes are automatically removed

---

## User Types & Permissions

### What are the different user types?
User types are hierarchical with different permission levels:
- **1**: Basic Provider
- **7**: Group Admin
- **10**: Case Admin
- **20**: User Admin
- **100**: Global Admin
- **999**: System Admin

Higher numbers generally indicate more permissions.

### What can each user type do?
- **Providers (1-9)**: Manage their own cases, surgeons, and facilities
- **Case Admins (10+)**: Access administrative case management functions
- **User Admins (20+)**: Manage user accounts and view user lists
- **Global Admins (100+)**: Access system-wide administrative functions
- **System Admins (999)**: Full system access

### Why am I getting "permission denied" errors?
Permission denied errors occur when:
- Your user type is insufficient for the requested operation
- Administrative functions require user_type >= 10
- You're trying to access data above your permission level
- Your account is not active

### How do I request higher permissions?
Contact your system administrator to:
- Upgrade your user type
- Adjust your max_case_status setting
- Activate administrative privileges

---

## Technical Issues & Troubleshooting

### The application won't start. What should I check?

1. **Database Connection**: Ensure MySQL is running and credentials are correct
2. **AWS Configuration**: Verify AWS credentials and Secrets Manager access
3. **Dependencies**: Run `pip install -r requirements.txt`
4. **Port Conflicts**: Ensure port 8000 is available
5. **Environment Variables**: Check if any required environment variables are missing

### I'm getting database connection errors. How do I fix this?
Database connection errors usually indicate:
- **Incorrect credentials**: Check your AWS Secrets Manager configuration
- **Network issues**: Ensure the database server is reachable
- **Database server down**: Verify MySQL is running
- **Connection limits**: Check if database connection limits are exceeded

### How do I report a bug?
Use the built-in bug reporting system:
1. Call `POST /bugs` endpoint with comprehensive bug information
2. Include environment data, user context, and reproduction steps
3. The system automatically creates a ClickUp task for tracking
4. View open bugs with `GET /bugs`

### Why is the system slow?
Performance issues can be caused by:
- **Database queries**: Check for inefficient queries or missing indexes
- **AWS API calls**: Monitor Secrets Manager and S3 usage
- **Large datasets**: Consider pagination for large result sets
- **Resource constraints**: Monitor CPU, memory, and disk usage

### How do I check system health?
Use the health check endpoints:
- `/health`: Comprehensive health check with all AWS services
- `/health/system`: Simplified system status (perfect for user login)
- `/metrics`: Prometheus metrics endpoint
- `/metrics/summary`: Human-readable metrics summary

---

## API Usage

### How do I use the SurgiCase API?
1. **Documentation**: Visit http://localhost:8000/docs for interactive API documentation
2. **Authentication**: Include a valid `user_id` parameter in your requests
3. **Content Type**: Use `application/json` for POST/PATCH requests
4. **Error Handling**: Check response status codes and error messages

### What are the main API endpoints?

**Case Management**:
- `GET /case` - Retrieve case by ID
- `POST /case` - Create new case
- `PATCH /case` - Update case
- `DELETE /case` - Delete case
- `GET /case_filter` - Filter cases by status

**User Management**:
- `GET /user` - Get user profile
- `POST /user` - Create user
- `PATCH /user` - Update user
- `DELETE /user` - Delete user

**Administrative**:
- `GET /users` - List all users (admin only)
- `GET /user_dashboard_data` - User analytics
- `PATCH /bulk_update_case_status` - Bulk case updates

### How do I handle API errors?
The API returns standardized error responses:
- **400**: Bad Request - Invalid parameters
- **404**: Not Found - Resource doesn't exist
- **403**: Forbidden - Insufficient permissions
- **422**: Validation Error - Invalid data format
- **500**: Internal Server Error - System error

### What's the difference between user_id parameter and request body user_id?
- **Parameter `user_id`**: Used for authentication and authorization
- **Body `user_id`**: Used as data (e.g., when creating cases for specific users)

Always ensure the parameter `user_id` represents the authenticated user making the request.

---

## Data Management

### How do I backup my data?
SurgiCase uses MySQL for data storage. Regular database backups should include:
- All user data from `user_profile` table
- Case data from `cases` and `case_procedure_codes` tables
- Surgeon and facility data
- Document metadata (actual files are in S3)

### Where are files stored?
Files are stored in AWS S3 with:
- Encryption at rest (AES256)
- Organized folder structure
- Automatic retention policies
- Secure access controls

### How do I migrate data to a new environment?
1. **Database**: Export/import MySQL database
2. **AWS Configuration**: Set up Secrets Manager and S3 in new environment
3. **File Migration**: Copy S3 bucket contents if needed
4. **Configuration**: Update connection strings and AWS settings

### What about data privacy and HIPAA compliance?
SurgiCase implements healthcare data protection standards:
- Encrypted data storage and transmission
- Access controls and audit logging
- Provider data isolation
- Secure document handling
- NPI compliance for provider verification

---

## Reporting & Analytics

### How do I generate provider payment reports?
Provider payment reports are generated automatically with:
- Password-protected PDFs
- Provider-specific data isolation
- Automated S3 storage
- Email delivery capabilities
- QuickBooks export format

### What analytics are available?
SurgiCase provides:
- **User Dashboard**: User type distribution and analytics
- **Case Analytics**: Case status tracking and metrics
- **Business Metrics**: System usage and performance
- **Prometheus Metrics**: Technical monitoring data

### How do I export data for accounting?
Use the QuickBooks export functionality:
- Exports case and payment data
- Formatted for QuickBooks import
- Includes procedure codes and amounts
- Provider-specific exports available

---

## Integration & Deployment

### How do I deploy SurgiCase to production?

1. **Server Setup**: Use Ubuntu 24.04+ on EC2 or similar
2. **Database**: Configure MySQL RDS instance
3. **AWS Services**: Set up S3 bucket and Secrets Manager
4. **Application**: Deploy code and configure systemd service
5. **Monitoring**: Set up Prometheus, Grafana, and Loki
6. **SSL/TLS**: Configure HTTPS with proper certificates

### How do I set up monitoring?
SurgiCase includes comprehensive monitoring:
- **Prometheus**: Metrics collection and alerting
- **Grafana**: Dashboard visualization
- **Loki**: Log aggregation
- **Health Checks**: Kubernetes-ready probes
- **Business Metrics**: Application-specific tracking

### Can I run multiple instances for high availability?
Yes, SurgiCase supports horizontal scaling:
- Stateless application design
- Shared database and S3 storage
- Load balancer compatibility
- Session-independent authentication

### How do I update to a new version?
1. **Backup**: Create database and configuration backups
2. **Test**: Deploy to staging environment first
3. **Dependencies**: Update Python packages if needed
4. **Database**: Run any required migrations
5. **Deploy**: Update application code
6. **Verify**: Test critical functionality

### What external services does SurgiCase integrate with?
- **AWS S3**: File storage and document management
- **AWS Secrets Manager**: Secure credential storage
- **CMS NPI Registry**: Provider validation
- **ClickUp**: Bug tracking and project management
- **QuickBooks**: Accounting and billing export
- **Prometheus/Grafana**: Monitoring and analytics

---

## Additional Support

### Where can I find more documentation?
- **API Documentation**: http://localhost:8000/docs (interactive)
- **README.md**: Comprehensive setup and feature guide
- **MONITORING_README.md**: Monitoring setup instructions
- **SCHEDULER_README.md**: Automated task information
- **S3_INTEGRATION_README.md**: File storage details

### How do I get help with specific issues?
1. **Check logs**: Review application and system logs
2. **Use bug reporting**: Submit detailed bug reports via the API
3. **Monitor metrics**: Check system health and performance metrics
4. **Contact support**: Reach out to your system administrator

### What if I need a new feature?
Feature requests should be:
1. Documented with clear requirements
2. Submitted through your organization's process
3. Evaluated for impact on existing functionality
4. Tested thoroughly before production deployment

---

*Last Updated: January 2025*
*SurgiCase Version: 0.9.0*
