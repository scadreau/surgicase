# Created: 2025-07-28 19:48:18
# Last Modified: 2025-08-06 16:04:25
# Author: Scott Cadreau

# endpoints/exports/case_export.py
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel
import pymysql.cursors
from core.database import get_db_connection, close_db_connection
from utils.monitoring import track_business_operation, business_metrics
from utils.s3_storage import upload_file_to_s3, generate_s3_key
from utils.report_cleanup import cleanup_old_reports
from typing import List, Dict, Any
import json
import csv
import os
import tempfile
import time
from datetime import datetime

router = APIRouter()

# --- Request Models ---

class CaseExportRequest(BaseModel):
    case_ids: List[str]

# --- Pure Functions for Data Processing ---

def get_cases_with_procedures(cursor: pymysql.cursors.DictCursor, case_ids: List[str]) -> List[Dict[str, Any]]:
    """
    Extract case data with associated procedure codes.
    Pure function that takes a cursor and case_ids and returns comprehensive case data.
    """
    if not case_ids:
        return []
    
    # Create placeholders for the IN clause
    placeholders = ','.join(['%s'] * len(case_ids))
    
    # Query to get all data from cases table joined with case_procedure_codes
    sql = f"""
        SELECT 
            c.*,
            cpc.procedure_code
        FROM cases c
        LEFT JOIN case_procedure_codes cpc ON c.case_id = cpc.case_id
        WHERE c.case_id IN ({placeholders})
        ORDER BY c.case_id, cpc.procedure_code
    """
    
    cursor.execute(sql, case_ids)
    results = cursor.fetchall()
    
    # Group results by case_id to handle multiple procedure codes per case
    cases_dict = {}
    for row in results:
        case_id = row['case_id']
        
        if case_id not in cases_dict:
            # Create new case entry with all case data
            case_data = {k: v for k, v in row.items() if k != 'procedure_code'}
            case_data['procedure_codes'] = []
            cases_dict[case_id] = case_data
        
        # Add procedure code if it exists
        if row['procedure_code'] is not None:
            cases_dict[case_id]['procedure_codes'].append(row['procedure_code'])
    
    return list(cases_dict.values())

def format_export_response(cases: List[Dict[str, Any]], requested_case_ids: List[str]) -> Dict[str, Any]:
    """
    Format the export response with metadata.
    """
    found_case_ids = [case['case_id'] for case in cases]
    missing_case_ids = [case_id for case_id in requested_case_ids if case_id not in found_case_ids]
    
    return {
        'cases': cases,
        'summary': {
            'total_requested': len(requested_case_ids),
            'total_found': len(cases),
            'total_missing': len(missing_case_ids),
            'found_case_ids': found_case_ids,
            'missing_case_ids': missing_case_ids
        }
    }

def create_cases_csv(cases: List[Dict[str, Any]], filepath: str) -> None:
    """
    Create CSV file for case export.
    """
    if not cases:
        # Create empty CSV with headers only
        with open(filepath, 'w', newline='', encoding='utf-8') as csvfile:
            fieldnames = ['case_id', 'user_id', 'case_date', 'patient_first', 'patient_last', 'procedure_codes']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
        return

    # Get all possible fields from the first case (excluding procedure_codes which we'll handle separately)
    sample_case = cases[0]
    fieldnames = [field for field in sample_case.keys() if field != 'procedure_codes']
    fieldnames.append('procedure_codes')  # Add procedure_codes as the last field
    
    with open(filepath, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        
        for case in cases:
            # Create a copy of the case data
            csv_row = {k: v for k, v in case.items() if k != 'procedure_codes'}
            
            # Convert procedure codes list to comma-separated string
            procedure_codes = case.get('procedure_codes', [])
            csv_row['procedure_codes'] = ', '.join(procedure_codes) if procedure_codes else ''
            
            # Handle None values and convert dates to strings
            for key, value in csv_row.items():
                if value is None:
                    csv_row[key] = ''
                elif isinstance(value, datetime):
                    csv_row[key] = value.strftime('%Y-%m-%d %H:%M:%S')
                elif hasattr(value, 'date'):  # Handle date objects
                    csv_row[key] = value.strftime('%Y-%m-%d')
            
            writer.writerow(csv_row)

# --- Main Export Endpoints ---

@router.post("/export_cases")
@track_business_operation("export", "cases")
def export_cases(request_obj: Request, export_request: CaseExportRequest):
    """
    Export comprehensive case data with associated procedure codes in JSON format.
    
    This endpoint provides complete case data export functionality including:
    - Comprehensive case data extraction from multiple database tables
    - Procedure code aggregation and association per case
    - Data validation and missing case identification
    - Comprehensive monitoring and business metrics tracking
    - Full request logging and execution time tracking
    - Prometheus metrics integration for operational monitoring
    
    Args:
        request (CaseExportRequest): The export request containing:
            - case_ids (List[str]): List of case IDs to export data for
    
    Returns:
        dict: Response containing:
            - cases (List[dict]): Array of case records, each containing:
                - All fields from the 'cases' table (case_id, user_id, case_date, patient info, etc.)
                - procedure_codes (List[str]): Array of associated procedure codes
            - summary (dict): Export metadata including:
                - total_requested (int): Number of case IDs requested
                - total_found (int): Number of cases successfully found
                - total_missing (int): Number of cases not found
                - found_case_ids (List[str]): List of successfully exported case IDs
                - missing_case_ids (List[str]): List of case IDs that were not found
    
    Raises:
        HTTPException: 
            - 400 Bad Request: case_ids list is empty or missing
            - 500 Internal Server Error: Database query failures or connection issues
    
    Database Operations:
        - Executes JOIN query on 'cases' and 'case_procedure_codes' tables
        - Uses parameterized IN clause for case ID filtering
        - Groups results by case_id to handle multiple procedure codes per case
        - Uses proper cursor management with DictCursor for JSON serialization
        - Automatic connection cleanup in finally block
    
    Data Processing:
        - Aggregates multiple procedure codes per case into arrays
        - Preserves all original case table fields without modification
        - Identifies and reports missing case IDs for validation
        - Maintains data integrity and consistency across export
    
    Monitoring & Logging:
        - Business metrics tracking for case export operations
        - Prometheus monitoring via @track_business_operation decorator
        - Records success/error metrics via business_metrics.record_utility_operation()
        - Comprehensive request logging with execution time tracking
        - Error logging with full exception details
    
    Example:
        POST /export_cases
        {
            "case_ids": ["CASE-2024-001", "CASE-2024-002", "CASE-2024-003"]
        }
        
        Response:
        {
            "cases": [
                {
                    "case_id": "CASE-2024-001",
                    "user_id": "USER123",
                    "case_date": "2024-01-15",
                    "patient_first": "John",
                    "patient_last": "Doe",
                    "pay_amount": 150.00,
                    "procedure_codes": ["12345", "67890"]
                }
            ],
            "summary": {
                "total_requested": 3,
                "total_found": 1,
                "total_missing": 2,
                "found_case_ids": ["CASE-2024-001"],
                "missing_case_ids": ["CASE-2024-002", "CASE-2024-003"]
            }
        }
    
    Note:
        - Export includes all fields from the cases table
        - Procedure codes are aggregated into arrays per case
        - Missing cases are reported in the summary for audit purposes
        - Export format is JSON for programmatic consumption
        - Use /export_cases_csv for spreadsheet-compatible format
    """
    start_time = time.time()
    response_status = 200
    response_data = None
    error_message = None
    
    try:
        if not export_request.case_ids:
            response_status = 400
            error_message = "case_ids list cannot be empty"
            raise HTTPException(status_code=400, detail="case_ids list cannot be empty")
        
        conn = get_db_connection()
        
        try:
            with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                # Get case data with procedure codes
                cases = get_cases_with_procedures(cursor, export_request.case_ids)
                
                # Format response with metadata
                response = format_export_response(cases, export_request.case_ids)
                
                business_metrics.record_utility_operation("case_export", "success")
                
                response_data = response
                return response
                
        finally:
            close_db_connection(conn)
            
    except HTTPException as http_error:
        response_status = http_error.status_code
        error_message = str(http_error.detail)
        raise
    except Exception as e:
        response_status = 500
        error_message = str(e)
        business_metrics.record_utility_operation("case_export", "error")
        raise HTTPException(status_code=500, detail=f"Error exporting cases: {str(e)}")
    finally:
        # Calculate execution time in milliseconds for logging
        execution_time_ms = int((time.time() - start_time) * 1000)
        
        # Log request details for monitoring using the utility function
        from endpoints.utility.log_request import log_request_from_endpoint
        log_request_from_endpoint(
            request=request_obj,
            execution_time_ms=execution_time_ms,
            response_status=response_status,
            user_id=None,
            response_data=response_data,
            error_message=error_message
        )

@router.post("/export_cases_csv")
@track_business_operation("export", "cases_csv")
def export_cases_csv(request_obj: Request, export_request: CaseExportRequest):
    """
    Export comprehensive case data as downloadable CSV file with S3 backup storage.
    
    This endpoint provides complete case data export functionality in CSV format including:
    - Comprehensive case data extraction and CSV formatting
    - Procedure code aggregation into comma-separated values
    - File generation with automatic timestamping
    - S3 backup storage with metadata preservation
    - File cleanup automation for storage management
    - Comprehensive monitoring and business metrics tracking
    - Full request logging and execution time tracking
    - Prometheus metrics integration for operational monitoring
    
    Args:
        request (CaseExportRequest): The export request containing:
            - case_ids (List[str]): List of case IDs to export data for
    
    Returns:
        FileResponse: Direct CSV file download containing:
            - All fields from the 'cases' table as CSV columns
            - procedure_codes column with comma-separated procedure codes
            - Proper CSV encoding (UTF-8) for international compatibility
            - Headers with export metadata including:
                - Content-Disposition: attachment with timestamped filename
                - X-Export-Summary: JSON summary of export results
                - X-S3-Upload-Status: S3 backup status indicator
    
    Raises:
        HTTPException: 
            - 400 Bad Request: case_ids list is empty or missing
            - 500 Internal Server Error: Database, file system, or S3 failures
    
    Database Operations:
        - Executes JOIN query on 'cases' and 'case_procedure_codes' tables
        - Uses parameterized IN clause for case ID filtering
        - Groups results by case_id to handle multiple procedure codes per case
        - Uses proper cursor management with DictCursor for JSON serialization
        - Automatic connection cleanup in finally block
    
    File & Storage Operations:
        - Creates local exports directory with automatic permission handling
        - Generates timestamped CSV filename for uniqueness
        - Applies CSV formatting with proper field handling and encoding
        - Uploads backup copy to S3 with comprehensive metadata
        - Implements automatic file cleanup (7-day retention policy)
        - Uses S3 folder prefix for organized storage structure
    
    Data Processing:
        - Aggregates multiple procedure codes per case into comma-separated strings
        - Handles NULL values and date formatting for CSV compatibility
        - Preserves all original case table fields without modification
        - Maintains data integrity and consistency across export
        - Applies proper character encoding for international data
    
    Monitoring & Logging:
        - Business metrics tracking for CSV export operations
        - Prometheus monitoring via @track_business_operation decorator
        - Records success/error metrics via business_metrics.record_utility_operation()
        - Comprehensive request logging with execution time tracking
        - Error logging with full exception details
        - S3 upload status tracking and metadata logging
    
    File Management:
        - Automatic directory creation with proper permissions
        - Timestamped filename generation for collision avoidance
        - Old file cleanup (configurable retention period)
        - S3 backup with organized folder structure
        - Comprehensive metadata preservation for audit trails
    
    Example:
        POST /export_cases_csv
        {
            "case_ids": ["CASE-2024-001", "CASE-2024-002"]
        }
        
        Response: CSV file download with headers:
        Content-Disposition: attachment; filename=case_export_20240815_143022.csv
        X-Export-Summary: {"total_requested":2,"total_found":1,"total_missing":1}
        X-S3-Upload-Status: success
        
        CSV Content:
        case_id,user_id,case_date,patient_first,patient_last,procedure_codes
        CASE-2024-001,USER123,2024-01-15,John,Doe,"12345, 67890"
    
    Note:
        - CSV includes all fields from the cases table
        - Procedure codes are comma-separated within a single column
        - Files are automatically backed up to S3 for redundancy
        - Local files are cleaned up after 7 days to manage storage
        - Export includes comprehensive metadata for audit purposes
        - S3 storage uses organized folder structure for easy management
        - File encoding is UTF-8 for international character support
    """
    start_time = time.time()
    response_status = 200
    response_data = None
    error_message = None
    
    try:
        if not export_request.case_ids:
            response_status = 400
            error_message = "case_ids list cannot be empty"
            raise HTTPException(status_code=400, detail="case_ids list cannot be empty")
        
        conn = get_db_connection()
        
        try:
            with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                # Get case data with procedure codes
                cases = get_cases_with_procedures(cursor, export_request.case_ids)
                
                # Create exports directory
                exports_dir = os.path.join(os.getcwd(), "exports")
                os.makedirs(exports_dir, exist_ok=True)
                
                # Clean up old files (older than 7 days)
                cleanup_old_reports(exports_dir, days_to_keep=7)
                
                # Generate filename with timestamp
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"case_export_{timestamp}.csv"
                filepath = os.path.join(exports_dir, filename)
                
                # Create CSV file
                create_cases_csv(cases, filepath)
                
                # Prepare metadata for S3
                metadata = {
                    "report_type": "case_export",
                    "generated_at": datetime.now().isoformat(),
                    "total_cases_requested": str(len(export_request.case_ids)),
                    "total_cases_found": str(len(cases)),
                    "export_format": "csv"
                }
                
                # Upload to S3 with custom folder prefix
                s3_key = generate_s3_key(
                    file_type="csv",
                    filename=filename,
                    folder_prefix="private/exports/"
                )
                
                s3_result = upload_file_to_s3(
                    file_path=filepath,
                    s3_key=s3_key,
                    content_type="text/csv",
                    metadata=metadata
                )
                
                # Format response with export summary and S3 info
                found_case_ids = [case['case_id'] for case in cases]
                missing_case_ids = [case_id for case_id in export_request.case_ids if case_id not in found_case_ids]
                
                response = {
                    "success": True,
                    "filename": filename,
                    "filepath": filepath,
                    "s3_upload": s3_result,
                    "summary": {
                        "total_requested": len(export_request.case_ids),
                        "total_found": len(cases),
                        "total_missing": len(missing_case_ids),
                        "found_case_ids": found_case_ids,
                        "missing_case_ids": missing_case_ids
                    },
                    "export_timestamp": timestamp
                }
                
                business_metrics.record_utility_operation("case_export_csv", "success")
                
                response_data = response
                
                # Return the CSV file as a download
                return FileResponse(
                    path=filepath,
                    filename=filename,
                    media_type="text/csv",
                    headers={
                        "Content-Disposition": f"attachment; filename={filename}",
                        "X-Export-Summary": json.dumps(response["summary"]),
                        "X-S3-Upload-Status": "success" if s3_result["success"] else "failed"
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
        business_metrics.record_utility_operation("case_export_csv", "error")
        raise HTTPException(status_code=500, detail=f"Error exporting cases to CSV: {str(e)}")
    finally:
        # Calculate execution time in milliseconds for logging
        execution_time_ms = int((time.time() - start_time) * 1000)
        
        # Log request details for monitoring using the utility function
        from endpoints.utility.log_request import log_request_from_endpoint
        log_request_from_endpoint(
            request=request_obj,
            execution_time_ms=execution_time_ms,
            response_status=response_status,
            user_id=None,
            response_data=response_data,
            error_message=error_message
        ) 