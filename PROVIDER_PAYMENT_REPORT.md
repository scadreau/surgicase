# Provider Payment Report Endpoint

## Overview

The Provider Payment Report endpoint generates comprehensive PDF reports of surgical cases grouped by provider. This endpoint retrieves cases with `case_status=1` (completed cases) and creates a professional PDF document with detailed payment information for each provider.

## Endpoint Details

- **URL**: `/provider-report`
- **Method**: `GET`
- **Response Type**: `application/pdf` (File Download)
- **Authentication**: Not required (based on current implementation)

## Query Parameters

| Parameter | Type | Required | Description | Example |
|-----------|------|----------|-------------|---------|
| `start_date` | string | No | Filter cases from this date (YYYY-MM-DD) | `2025-01-01` |
| `end_date` | string | No | Filter cases to this date (YYYY-MM-DD) | `2025-01-31` |
| `user_id` | string | No | Filter for specific provider | `provider_123` |

## Request Examples

### Basic Report (All Providers)
```bash
GET /provider-report
```

### Date Range Report
```bash
GET /provider-report?start_date=2025-01-01&end_date=2025-01-31
```

### Specific Provider Report
```bash
GET /provider-report?user_id=provider_123
```

### Combined Filters
```bash
GET /provider-report?user_id=provider_123&start_date=2025-01-01&end_date=2025-01-31
```

## Response

The endpoint returns a PDF file with the following structure:

### PDF Layout
1. **Header Page**
   - Report title: "Provider Payment Report"
   - Generation date
   - Page numbering

2. **Provider Sections** (Each provider gets their own page)
   - Provider name: " {first_name} {last_name}"
   - NPI number (if available)
   - Case details table with:
     - Procedure date
     - Patient name
     - Procedure codes
     - Payment category
     - Payment amount
   - Provider subtotal

3. **Summary Page**
   - Total number of providers
   - Total number of cases
   - Total payment amount

### Table Columns
| Column | Description | Format |
|--------|-------------|--------|
| Date | Case procedure date | YYYY-MM-DD |
| Patient Name | Patient first and last name | "John Smith" |
| Procedure(s) | CPT codes for the case | "58150, 58661" |
| Category | Payment category | "General Surgery" |
| Amount | Payment amount | "$1,234.56" |

## Database Queries

The endpoint performs the following database operations:

### Main Query
```sql
SELECT 
    c.user_id,
    c.case_id,
    c.case_date,
    c.patient_first,
    c.patient_last,
    c.pay_amount,
    c.pay_category,
    up.first_name,
    up.last_name,
    up.user_npi
FROM cases c
INNER JOIN user_profile up ON c.user_id = up.user_id
WHERE c.case_status = 1 
AND c.active = 1 
AND up.active = 1
ORDER BY c.user_id, c.case_date
```

### Procedure Codes Query
```sql
SELECT procedure_code 
FROM case_procedure_codes 
WHERE case_id = %s
```

## File Management

### Storage Location
- **Directory**: `{project_root}/reports/`
- **Filename Format**: `provider_payment_report_YYYYMMDD_HHMMSS.pdf`
- **Example**: `provider_payment_report_20250127_143052.pdf`

### Automatic Cleanup
- Files older than 7 days are automatically deleted
- Cleanup runs before each new report generation
- Prevents disk space issues on the server

## Error Handling

### HTTP Status Codes
- **200 OK**: Report generated successfully
- **404 Not Found**: No cases found matching criteria
- **500 Internal Server Error**: Database or PDF generation error

### Error Responses
```json
{
    "detail": "No cases found matching the criteria"
}
```

## Monitoring

The endpoint includes comprehensive monitoring:

### Business Metrics
- **Success**: `business_metrics.record_utility_operation("provider_report", "success")`
- **Error**: `business_metrics.record_utility_operation("provider_report", "error")`

### Request Tracking
- All requests are tracked via `@track_business_operation("generate", "provider_report")`

## Testing

### Postman Testing
1. Set request method to `GET`
2. Enter URL: `http://your-server:8000/provider-report`
3. Add query parameters as needed
4. Send request
5. Postman will offer to save the PDF file

### cURL Testing
```bash
# Basic report
curl -X GET "http://localhost:8000/provider-report" \
     --output "provider_report.pdf"

# With date filters
curl -X GET "http://localhost:8000/provider-report?start_date=2025-01-01&end_date=2025-01-31" \
     --output "provider_report_january.pdf"
```

### Browser Testing
- Navigate to the endpoint URL
- Browser will automatically trigger download
- File will be saved to your default download directory

## Dependencies

### Required Python Packages
- `fpdf`: PDF generation
- `pymysql`: Database connectivity
- `fastapi`: Web framework
- `tempfile`: Temporary file handling (for cleanup utilities)

### Database Tables
- `cases`: Main case data
- `user_profile`: Provider information
- `case_procedure_codes`: Procedure codes for each case

## Performance Considerations

### Large Datasets
- Reports are generated in memory and streamed to disk
- Each provider section starts on a new page for better readability
- Consider implementing pagination for very large datasets

### File Size
- PDF files are typically 50KB - 2MB depending on number of cases
- Files are automatically cleaned up after 7 days
- Monitor disk space usage in production

## Security Notes

### Current Implementation
- No authentication required (may need to be added based on requirements)
- Files are stored in project directory (consider moving to secure storage in production)
- No input validation on date parameters (should be added)

### Production Recommendations
- Add authentication/authorization
- Implement input validation for date parameters
- Consider moving file storage to cloud storage (S3, etc.)
- Add rate limiting to prevent abuse

## Related Files

- **Endpoint**: `endpoints/reports/provider_payment_report.py`
- **Cleanup Utility**: `utils/report_cleanup.py`
- **Main App**: `main.py` (includes router)
- **Requirements**: `requirements.txt` (includes fpdf dependency)

## Changelog

- **2025-07-23**: Fixed path duplication
  - Fixed path duplication in S3
- **2025-07-17**: Initial implementation
  - Basic PDF generation with provider grouping
  - File storage in reports directory
  - Automatic cleanup of old files
  - Comprehensive error handling and monitoring 