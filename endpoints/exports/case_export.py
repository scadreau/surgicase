# Created: 2025-07-28 19:48:18
# Last Modified: 2025-07-28 19:50:23
# Author: Scott Cadreau

# endpoints/exports/case_export.py
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import pymysql.cursors
from core.database import get_db_connection, close_db_connection
from utils.monitoring import track_business_operation, business_metrics
from typing import List, Dict, Any
import json

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

# --- Main Export Endpoint ---

@router.post("/cases")
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