# Created: 2025-11-14 15:46:34
# Last Modified: 2025-11-14 15:47:23
# Author: Scott Cadreau

# endpoints/reports/provider_bucket_report.py
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse
import pymysql.cursors
from core.database import get_db_connection, close_db_connection
from utils.monitoring import track_business_operation, business_metrics, logger
from utils.s3_storage import upload_file_to_s3, generate_s3_key
from utils.report_cleanup import cleanup_old_reports
from typing import Optional, List, Dict, Any
import csv
import os
import time
from datetime import datetime

router = APIRouter()


def create_provider_bucket_csv(data: List[Dict[str, Any]], filepath: str) -> None:
    """
    Create CSV file for provider bucket report.
    
    Args:
        data: List of dictionaries containing provider bucket data
        filepath: Path where the CSV file should be written
        
    Returns:
        None
    """
    if not data:
        # Create empty CSV with headers only
        with open(filepath, 'w', newline='', encoding='utf-8') as csvfile:
            fieldnames = [
                'first_name', 'last_name', 'pay_category', 'case_status', 
                'bucket_count', 'bucket_total'
            ]
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
        return

    # Define field order
    fieldnames = ['first_name', 'last_name', 'pay_category', 'case_status', 'bucket_count', 'bucket_total']
    
    with open(filepath, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        
        for row in data:
            # Create a copy of the row data for CSV writing
            csv_row = {}
            
            for field in fieldnames:
                value = row.get(field)
                
                # Handle None values
                if value is None:
                    csv_row[field] = ''
                # Handle datetime objects
                elif isinstance(value, datetime):
                    csv_row[field] = value.strftime('%Y-%m-%d %H:%M:%S')
                # Handle date objects
                elif hasattr(value, 'date'):
                    csv_row[field] = value.strftime('%Y-%m-%d')
                # Handle decimal/float values
                elif isinstance(value, (int, float)):
                    csv_row[field] = value
                else:
                    csv_row[field] = str(value) if value is not None else ''
            
            writer.writerow(csv_row)


@router.get("/provider_bucket_report")
@track_business_operation("generate", "provider_bucket_report")
def generate_provider_bucket_report(
    request: Request,
    start_date: Optional[str] = Query(None, description="Start date for filtering (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date for filtering (YYYY-MM-DD)")
):
    """
    Generate provider bucket report showing payment categories and case status breakdowns by provider.
    
    This endpoint generates a CSV report that groups cases by provider, payment category, and case status,
    providing bucket counts and totals. The report is designed to be easily filtered and summarized in Excel
    or other spreadsheet applications.
    
    Key Features:
    - Aggregated data by provider, payment category, and case status
    - CSV format for easy Excel manipulation
    - Optional date range filtering
    - Automatic S3 cloud storage backup
    - Only includes active cases and provider accounts (user_type=1)
    - Sorted by provider name for easy review
    
    Args:
        request (Request): FastAPI request object for logging and monitoring
        start_date (str, optional): Start date for case filtering in YYYY-MM-DD format.
                                   Filters cases where case_date >= start_date.
                                   If omitted, includes all cases from the beginning.
        end_date (str, optional): End date for case filtering in YYYY-MM-DD format.
                                 Filters cases where case_date <= end_date.
                                 If omitted, includes all cases up to the present.
    
    Returns:
        FileResponse: CSV file download with comprehensive metadata headers:
            - Content-Type: text/csv
            - Content-Disposition: attachment with timestamped filename
            - X-S3-Upload-Status: S3 upload success status
            - X-Total-Records: Total number of records in the report
    
    Raises:
        HTTPException:
            - 404 Not Found: No data found matching the specified criteria
            - 500 Internal Server Error: Database query, file generation, or S3 upload errors
    
    Database Operations:
        1. Queries cases table joined with user_profile
        2. Filters by active status (cases.active = 1)
        3. Filters by user type (user_profile.user_type = 1 for providers)
        4. Applies optional date range filters
        5. Groups by provider name, payment category, and case status
        6. Calculates count and sum of payment amounts per group
        7. Orders results by provider last name, first name, pay_category, case_status
    
    Report Content Structure:
        CSV Columns:
        - first_name: Provider's first name
        - last_name: Provider's last name
        - pay_category: Payment category (bucket)
        - case_status: Case status code
        - bucket_count: Number of cases in this bucket
        - bucket_total: Sum of pay_amount for cases in this bucket
    
    Business Rules:
        - Only includes active cases (active = 1)
        - Only includes provider accounts (user_type = 1)
        - Groups data for aggregation by provider, category, and status
        - Allows users to filter and pivot in Excel for custom analysis
        - Date filters are optional for maximum flexibility
    
    AWS S3 Integration:
        - Automatic upload to configured S3 bucket
        - Metadata tagging with report details:
            * Report type and generation timestamp
            * Total record count
            * Date filter parameters
        - S3 key organized under reports folder structure
        - Error handling with graceful degradation if S3 fails
    
    File Management:
        - Timestamped filename generation for uniqueness
        - Local storage in dedicated reports directory
        - Automatic cleanup of reports older than 7 days
        - UTF-8 encoding for international character support
        - Secure temporary file handling
    
    Monitoring & Analytics:
        - Business metrics tracking for report generation operations
        - Prometheus monitoring via @track_business_operation decorator
        - Success/failure tracking for all operations
        - Performance metrics for generation time
        - Comprehensive logging for troubleshooting
    
    Example Usage:
        GET /provider_bucket_report
        GET /provider_bucket_report?start_date=2024-01-01&end_date=2024-12-31
        GET /provider_bucket_report?start_date=2024-01-01
        GET /provider_bucket_report?end_date=2024-12-31
    
    Example Response Headers:
        Content-Type: text/csv
        Content-Disposition: attachment; filename="provider_bucket_report_20240815_143022.csv"
        X-S3-Upload-Status: success
        X-Total-Records: 245
    
    Example CSV Content:
        first_name,last_name,pay_category,case_status,bucket_count,bucket_total
        John,Doe,Standard,1,15,2500.00
        John,Doe,Standard,15,8,1200.00
        John,Doe,Premium,15,3,900.00
        Jane,Smith,Standard,1,20,3500.00
        Jane,Smith,Premium,15,5,1500.00
    
    Use Cases:
        - Analyze payment distribution by provider and category
        - Track case status progression by provider
        - Filter in Excel to focus on specific providers or categories
        - Create pivot tables for custom summaries
        - Export data for financial reporting and analysis
        - Monitor case volume and payment amounts by bucket
    
    Note:
        - Report includes ALL case statuses without filtering, allowing users to filter in Excel
        - Empty date filters query the entire cases table
        - Provider sorting enables easy alphabetical lookup
        - Decimal values are preserved for accurate financial calculations
        - Report is optimized for Excel/spreadsheet manipulation
        - S3 backup ensures data persistence and sharing capabilities
        - File cleanup prevents storage bloat on local filesystem
        - Professional data structure suitable for financial analysis and audit purposes
    """
    start_time = time.time()
    response_status = 200
    response_data = None
    error_message = None
    
    try:
        if logger:
            logger.info(f"Starting provider bucket report generation")
        
        conn = get_db_connection()
        
        try:
            # INPUT VALIDATION -- Check date format if provided
            if start_date:
                try:
                    datetime.strptime(start_date, '%Y-%m-%d')
                except ValueError:
                    response_status = 400
                    error_message = "Invalid start_date format. Use YYYY-MM-DD"
                    raise HTTPException(
                        status_code=400,
                        detail="Invalid start_date format. Use YYYY-MM-DD"
                    )
            
            if end_date:
                try:
                    datetime.strptime(end_date, '%Y-%m-%d')
                except ValueError:
                    response_status = 400
                    error_message = "Invalid end_date format. Use YYYY-MM-DD"
                    raise HTTPException(
                        status_code=400,
                        detail="Invalid end_date format. Use YYYY-MM-DD"
                    )
            
            with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                # Build the query with proper formatting
                sql = """
                    SELECT 
                        up.first_name,
                        up.last_name,
                        c.pay_category,
                        c.case_status,
                        COUNT(*) as bucket_count,
                        SUM(c.pay_amount) as bucket_total
                    FROM cases c
                    LEFT JOIN user_profile up ON c.user_id = up.user_id
                    WHERE c.active = 1
                    AND up.user_type = 1
                """
                
                params = []
                
                # Add date filters if provided
                if start_date:
                    sql += " AND c.case_date >= %s"
                    params.append(start_date)
                
                if end_date:
                    sql += " AND c.case_date <= %s"
                    params.append(end_date)
                
                # Group by provider, pay_category, and case_status
                sql += """
                    GROUP BY up.first_name, up.last_name, c.pay_category, c.case_status
                    ORDER BY up.last_name, up.first_name, c.pay_category, c.case_status
                """
                
                # Execute query
                cursor.execute(sql, params)
                report_data = cursor.fetchall()
                
                if not report_data:
                    response_status = 404
                    error_message = "No data found matching the criteria"
                    raise HTTPException(
                        status_code=404,
                        detail="No data found matching the criteria"
                    )
                
                if logger:
                    logger.info(f"Provider bucket report: Retrieved {len(report_data)} records")
                
                # Create reports directory
                reports_dir = os.path.join(os.getcwd(), "reports")
                os.makedirs(reports_dir, exist_ok=True)
                
                # Clean up old reports (older than 7 days)
                cleanup_old_reports(reports_dir, days_to_keep=7)
                
                # Generate filename with timestamp
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"provider_bucket_report_{timestamp}.csv"
                filepath = os.path.join(reports_dir, filename)
                
                # Create CSV file
                create_provider_bucket_csv(report_data, filepath)
                
                if logger:
                    logger.info(f"Provider bucket report: CSV file created at {filepath}")
                
                # Prepare metadata for S3
                metadata = {
                    "report_type": "provider_bucket_report",
                    "generated_at": datetime.now().isoformat(),
                    "total_records": str(len(report_data)),
                    "start_date": start_date or "all",
                    "end_date": end_date or "all"
                }
                
                # Upload to S3
                s3_key = generate_s3_key("reports", filename)
                s3_result = upload_file_to_s3(
                    file_path=filepath,
                    s3_key=s3_key,
                    content_type="text/csv",
                    metadata=metadata
                )
                
                if logger:
                    if s3_result.get("success"):
                        logger.info(f"Provider bucket report: Successfully uploaded to S3: {s3_result.get('s3_url')}")
                    else:
                        logger.warning(f"Provider bucket report: S3 upload failed: {s3_result.get('message')}")
                
                # Record successful report generation
                business_metrics.record_utility_operation("provider_bucket_report", "success")
                
                response_data = {
                    "success": True,
                    "filename": filename,
                    "filepath": filepath,
                    "s3_upload": s3_result,
                    "total_records": len(report_data),
                    "export_timestamp": timestamp
                }
                
                # Return the CSV file as a download
                return FileResponse(
                    path=filepath,
                    filename=filename,
                    media_type="text/csv",
                    headers={
                        "Content-Disposition": f"attachment; filename={filename}",
                        "X-S3-Upload-Status": "success" if s3_result["success"] else "failed",
                        "X-Total-Records": str(len(report_data))
                    }
                )
                
        finally:
            close_db_connection(conn)
            
    except HTTPException as http_error:
        response_status = http_error.status_code
        error_message = str(http_error.detail)
        raise
    except Exception as e:
        response_status = 500
        error_message = str(e)
        business_metrics.record_utility_operation("provider_bucket_report", "error")
        if logger:
            logger.error(f"Error generating provider bucket report: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error generating provider bucket report: {str(e)}"
        )
    finally:
        # Calculate execution time in milliseconds for logging
        execution_time_ms = int((time.time() - start_time) * 1000)
        
        # Log request details for monitoring using the utility function
        from endpoints.utility.log_request import log_request_from_endpoint
        log_request_from_endpoint(
            request=request,
            execution_time_ms=execution_time_ms,
            response_status=response_status,
            user_id=None,
            response_data=response_data,
            error_message=error_message
        )

