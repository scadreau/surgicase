# Created: 2025-07-28 19:48:18
# Last Modified: 2025-07-29 00:54:09
# Author: Scott Cadreau

# endpoints/exports/case_export.py
from fastapi import APIRouter, HTTPException
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
def export_cases(request: CaseExportRequest):
    """
    Export case data with associated procedure codes.
    
    Accepts a JSON request with a list of case_ids and returns all data
    from the cases table joined with case_procedure_codes table.
    """
    try:
        if not request.case_ids:
            raise HTTPException(status_code=400, detail="case_ids list cannot be empty")
        
        conn = get_db_connection()
        
        try:
            with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                # Get case data with procedure codes
                cases = get_cases_with_procedures(cursor, request.case_ids)
                
                # Format response with metadata
                response = format_export_response(cases, request.case_ids)
                
                business_metrics.record_utility_operation("case_export", "success")
                
                return response
                
        finally:
            close_db_connection(conn)
            
    except HTTPException:
        raise
    except Exception as e:
        business_metrics.record_utility_operation("case_export", "error")
        raise HTTPException(status_code=500, detail=f"Error exporting cases: {str(e)}")

@router.post("/export_cases_csv")
@track_business_operation("export", "cases_csv")
def export_cases_csv(request: CaseExportRequest):
    """
    Export case data as CSV file with S3 storage.
    
    Accepts a JSON request with a list of case_ids and returns a CSV file
    with all data from the cases table joined with case_procedure_codes table.
    Stores the file in S3 under the exports_csv directory.
    """
    try:
        if not request.case_ids:
            raise HTTPException(status_code=400, detail="case_ids list cannot be empty")
        
        conn = get_db_connection()
        
        try:
            with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                # Get case data with procedure codes
                cases = get_cases_with_procedures(cursor, request.case_ids)
                
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
                    "total_cases_requested": str(len(request.case_ids)),
                    "total_cases_found": str(len(cases)),
                    "export_format": "csv"
                }
                
                # Upload to S3 with custom folder prefix
                s3_key = generate_s3_key(
                    file_type="",
                    filename=filename,
                    folder_prefix="private/exports/csv/"
                )
                
                s3_result = upload_file_to_s3(
                    file_path=filepath,
                    s3_key=s3_key,
                    content_type="text/csv",
                    metadata=metadata
                )
                
                # Format response with export summary and S3 info
                found_case_ids = [case['case_id'] for case in cases]
                missing_case_ids = [case_id for case_id in request.case_ids if case_id not in found_case_ids]
                
                response = {
                    "success": True,
                    "filename": filename,
                    "filepath": filepath,
                    "s3_upload": s3_result,
                    "summary": {
                        "total_requested": len(request.case_ids),
                        "total_found": len(cases),
                        "total_missing": len(missing_case_ids),
                        "found_case_ids": found_case_ids,
                        "missing_case_ids": missing_case_ids
                    },
                    "export_timestamp": timestamp
                }
                
                business_metrics.record_utility_operation("case_export_csv", "success")
                
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
            
    except HTTPException:
        raise
    except Exception as e:
        business_metrics.record_utility_operation("case_export_csv", "error")
        raise HTTPException(status_code=500, detail=f"Error exporting cases to CSV: {str(e)}") 