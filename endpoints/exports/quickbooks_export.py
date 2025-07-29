# Created: 2025-01-27 15:00:00
# Last Modified: 2025-07-29 02:22:37
# Author: Scott Cadreau

# endpoints/exports/quickbooks_export.py
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
import pymysql.cursors
from core.database import get_db_connection, close_db_connection
from utils.monitoring import track_business_operation, business_metrics
from utils.report_cleanup import cleanup_old_reports
from utils.s3_storage import upload_file_to_s3, generate_s3_key
from utils.text_formatting import capitalize_name_field
from datetime import datetime
import os
import csv
import tempfile
from typing import Optional, List, Dict, Any
from functools import reduce
from itertools import groupby

router = APIRouter()

# --- Pure Functions for Data Transformation ---

def format_provider_name(first_name: str, last_name: str) -> str:
    """Format provider name with proper capitalization."""
    first = capitalize_name_field(first_name) if first_name else ''
    last = capitalize_name_field(last_name) if last_name else ''
    return f"{first} {last}".strip()

def format_patient_name(first_name: str, last_name: str) -> str:
    """Format patient name with proper capitalization."""
    first = capitalize_name_field(first_name) if first_name else ''
    last = capitalize_name_field(last_name) if last_name else ''
    return f"{first} {last}".strip()

def format_case_date(case_date) -> str:
    """Format case date for export."""
    if hasattr(case_date, 'strftime'):
        return case_date.strftime('%m/%d/%Y')
    return str(case_date)[:10] if case_date else ''

def format_procedures(procedures: List[str]) -> str:
    """Format procedure codes as comma-separated string."""
    if isinstance(procedures, list):
        return ', '.join(procedures) if procedures else ''
    return str(procedures) if procedures else ''

def format_amount(amount) -> float:
    """Format monetary amount."""
    try:
        return float(amount) if amount else 0.0
    except (ValueError, TypeError):
        return 0.0

# --- Data Extraction Functions ---

def get_provider_payment_data(
    cursor: pymysql.cursors.DictCursor,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    user_id: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Extract provider payment data using the same logic as the provider payment report.
    Pure function that takes a cursor and returns raw data.
    """
    sql = """
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
        WHERE c.case_status = 15
        AND c.active = 1 
        AND up.active = 1
    """
    params = []
    
    # Add filters
    if start_date:
        sql += " AND c.case_date >= %s"
        params.append(start_date)
    if end_date:
        sql += " AND c.case_date <= %s"
        params.append(end_date)
    if user_id:
        sql += " AND c.user_id = %s"
        params.append(user_id)
    
    sql += " ORDER BY c.user_id, c.case_date"
    
    cursor.execute(sql, params)
    cases = cursor.fetchall()
    
    # Get procedure codes for each case
    for case in cases:
        cursor.execute(
            "SELECT procedure_code FROM case_procedure_codes WHERE case_id = %s",
            (case['case_id'],)
        )
        procedure_codes = [row['procedure_code'] for row in cursor.fetchall()]
        case['procedures'] = procedure_codes
    
    return cases

def transform_cases_for_quickbooks(cases: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Transform raw case data into QuickBooks-ready format.
    Returns both vendor data and transaction data.
    """
    # Group cases by provider
    cases_by_provider = {}
    for case in cases:
        user_id = case['user_id']
        if user_id not in cases_by_provider:
            cases_by_provider[user_id] = []
        cases_by_provider[user_id].append(case)
    
    # Transform vendors (providers)
    vendors = []
    transactions = []
    
    for user_id, provider_cases in cases_by_provider.items():
        # Get provider info from first case
        first_case = provider_cases[0]
        
        # Create vendor record
        vendor = {
            'vendor_id': user_id,
            'vendor_name': format_provider_name(first_case['first_name'], first_case['last_name']),
            'npi': first_case.get('user_npi', ''),
            'total_amount': sum(format_amount(case['pay_amount']) for case in provider_cases),
            'case_count': len(provider_cases)
        }
        vendors.append(vendor)
        
        # Create transaction records
        for case in provider_cases:
            transaction = {
                'vendor_id': user_id,
                'vendor_name': vendor['vendor_name'],
                'case_id': case['case_id'],
                'transaction_date': format_case_date(case['case_date']),
                'patient_name': format_patient_name(case.get('patient_first', ''), case.get('patient_last', '')),
                'procedures': format_procedures(case.get('procedures', [])),
                'pay_category': case.get('pay_category', ''),
                'amount': format_amount(case['pay_amount']),
                'memo': f"Case {case['case_id']} - {format_patient_name(case.get('patient_first', ''), case.get('patient_last', ''))}"
            }
            transactions.append(transaction)
    
    return {
        'vendors': vendors,
        'transactions': transactions,
        'summary': {
            'total_vendors': len(vendors),
            'total_transactions': len(transactions),
            'total_amount': sum(v['total_amount'] for v in vendors)
        }
    }

# --- Export Format Functions ---

def create_vendors_csv(vendors: List[Dict[str, Any]], filepath: str) -> None:
    """Create CSV file for QuickBooks vendor import."""
    with open(filepath, 'w', newline='', encoding='utf-8') as csvfile:
        fieldnames = [
            'Name',
            'Company',
            'First Name',
            'Last Name',
            'Vendor Type',
            'Account Number',
            'Tax ID',
            'Is Vendor Eligible For 1099',
            'Terms',
            'Credit Limit',
            'Opening Balance',
            'As Of Date'
        ]
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        
        for vendor in vendors:
            name_parts = vendor['vendor_name'].split(' ', 1)
            first_name = name_parts[0] if len(name_parts) > 0 else ''
            last_name = name_parts[1] if len(name_parts) > 1 else ''
            
            writer.writerow({
                'Name': vendor['vendor_name'],
                'Company': vendor['vendor_name'],
                'First Name': first_name,
                'Last Name': last_name,
                'Vendor Type': 'Medical Provider',
                'Account Number': vendor['vendor_id'],
                'Tax ID': vendor.get('npi', ''),
                'Is Vendor Eligible For 1099': 'Y',
                'Terms': 'Net 30',
                'Credit Limit': '',
                'Opening Balance': f"{vendor['total_amount']:.2f}",
                'As Of Date': datetime.now().strftime('%m/%d/%Y')
            })

def create_transactions_iif(transactions: List[Dict[str, Any]], filepath: str) -> None:
    """Create IIF file for QuickBooks transaction import."""
    with open(filepath, 'w', encoding='utf-8') as iif_file:
        # IIF Header
        iif_file.write("!HDR\tPROD\tVER\tREL\tIIFVER\tDATE\tTIME\tACCNT\n")
        iif_file.write("HDR\tQuickBooks Pro\t2023\tR1\t1\t" + 
                      datetime.now().strftime('%m/%d/%Y') + "\t" +
                      datetime.now().strftime('%H:%M:%S') + "\tN\n")
        
        # Account Headers
        iif_file.write("!ACCNT\tNAME\tACCNTTYPE\tDESC\n")
        iif_file.write("ACCNT\tMedical Expenses\tEXP\tMedical Provider Payments\n")
        iif_file.write("ACCNT\tAccounts Payable\tAP\tAccounts Payable\n")
        
        # Vendor Headers
        iif_file.write("!VEND\tNAME\tVTYPE\tCONTACT\tCOMPANY\tADDR1\n")
        
        # Get unique vendors
        unique_vendors = {}
        for trans in transactions:
            if trans['vendor_id'] not in unique_vendors:
                unique_vendors[trans['vendor_id']] = trans['vendor_name']
        
        for vendor_id, vendor_name in unique_vendors.items():
            iif_file.write(f"VEND\t{vendor_name}\tMedical Provider\t{vendor_name}\t{vendor_name}\t\n")
        
        # Transaction Headers
        iif_file.write("!TRNS\tTRNSTYPE\tDATE\tACCNT\tNAME\tCLASS\tAMOUNT\tDOCNUM\tMEMO\n")
        iif_file.write("!SPL\tSPLID\tTRNSTYPE\tDATE\tACCNT\tNAME\tCLASS\tAMOUNT\tDOCNUM\tMEMO\n")
        iif_file.write("!ENDTRNS\n")
        
        # Write transactions
        for i, trans in enumerate(transactions, 1):
            # Bill transaction
            iif_file.write(f"TRNS\tBILL\t{trans['transaction_date']}\tAccounts Payable\t{trans['vendor_name']}\t\t{trans['amount']:.2f}\t{trans['case_id']}\t{trans['memo']}\n")
            iif_file.write(f"SPL\t{i}\tBILL\t{trans['transaction_date']}\tMedical Expenses\t{trans['vendor_name']}\t\t-{trans['amount']:.2f}\t{trans['case_id']}\t{trans['procedures']}\n")
            iif_file.write("ENDTRNS\n")

# --- Main Export Endpoints ---

@router.get("/quickbooks-vendors-csv")
@track_business_operation("export", "quickbooks_vendors_csv")
def export_quickbooks_vendors_csv(
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    user_id: Optional[str] = Query(None, description="Filter by specific provider user_id")
):
    """Export provider data as CSV for QuickBooks vendor import."""
    try:
        conn = get_db_connection()
        
        try:
            with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                # Get raw data using same logic as provider payment report
                cases = get_provider_payment_data(cursor, start_date, end_date, user_id)
                
                if not cases:
                    raise HTTPException(status_code=404, detail="No cases found matching the criteria")
                
                # Transform data for QuickBooks
                qb_data = transform_cases_for_quickbooks(cases)
                
                # Create exports directory
                exports_dir = os.path.join(os.getcwd(), "exports")
                os.makedirs(exports_dir, exist_ok=True)
                
                # Generate filename
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"quickbooks_vendors_{timestamp}.csv"
                filepath = os.path.join(exports_dir, filename)
                
                # Create CSV file
                create_vendors_csv(qb_data['vendors'], filepath)
                
                # Upload to S3
                metadata = {
                    'export_type': 'quickbooks_vendors_csv',
                    'generated_by': 'surgicase_api',
                    'total_vendors': str(qb_data['summary']['total_vendors']),
                    'total_amount': f"{qb_data['summary']['total_amount']:.2f}",
                    'start_date': start_date or 'all',
                    'end_date': end_date or 'all'
                }
                
                s3_key = generate_s3_key('exports/', filename)
                s3_result = upload_file_to_s3(
                    file_path=filepath,
                    s3_key=s3_key,
                    content_type='text/csv',
                    metadata=metadata
                )
                
                business_metrics.record_utility_operation("quickbooks_vendors_export", "success")
                
                return FileResponse(
                    path=filepath,
                    filename=filename,
                    media_type='text/csv',
                    headers={
                        'Content-Disposition': f'attachment; filename="{filename}"',
                        'X-S3-URL': s3_result.get('s3_url', ''),
                        'X-Export-Type': 'QuickBooks Vendors CSV',
                        'X-Record-Count': str(qb_data['summary']['total_vendors'])
                    }
                )
                
        finally:
            close_db_connection(conn)
            
    except HTTPException:
        raise
    except Exception as e:
        business_metrics.record_utility_operation("quickbooks_vendors_export", "error")
        raise HTTPException(status_code=500, detail=f"Error generating QuickBooks vendors export: {str(e)}")

@router.get("/quickbooks-transactions-iif")
@track_business_operation("export", "quickbooks_transactions_iif")
def export_quickbooks_transactions_iif(
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    user_id: Optional[str] = Query(None, description="Filter by specific provider user_id")
):
    """Export provider payment transactions as IIF for QuickBooks import."""
    try:
        conn = get_db_connection()
        
        try:
            with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                # Get raw data using same logic as provider payment report
                cases = get_provider_payment_data(cursor, start_date, end_date, user_id)
                
                if not cases:
                    raise HTTPException(status_code=404, detail="No cases found matching the criteria")
                
                # Transform data for QuickBooks
                qb_data = transform_cases_for_quickbooks(cases)
                
                # Create exports directory
                exports_dir = os.path.join(os.getcwd(), "exports")
                os.makedirs(exports_dir, exist_ok=True)
                
                # Generate filename
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"quickbooks_transactions_{timestamp}.iif"
                filepath = os.path.join(exports_dir, filename)
                
                # Create IIF file
                create_transactions_iif(qb_data['transactions'], filepath)
                
                # Upload to S3
                metadata = {
                    'export_type': 'quickbooks_transactions_iif',
                    'generated_by': 'surgicase_api',
                    'total_transactions': str(qb_data['summary']['total_transactions']),
                    'total_amount': f"{qb_data['summary']['total_amount']:.2f}",
                    'start_date': start_date or 'all',
                    'end_date': end_date or 'all'
                }
                
                s3_key = generate_s3_key('exports/', filename)
                s3_result = upload_file_to_s3(
                    file_path=filepath,
                    s3_key=s3_key,
                    content_type='application/octet-stream',
                    metadata=metadata
                )
                
                business_metrics.record_utility_operation("quickbooks_transactions_export", "success")
                
                return FileResponse(
                    path=filepath,
                    filename=filename,
                    media_type='application/octet-stream',
                    headers={
                        'Content-Disposition': f'attachment; filename="{filename}"',
                        'X-S3-URL': s3_result.get('s3_url', ''),
                        'X-Export-Type': 'QuickBooks Transactions IIF',
                        'X-Record-Count': str(qb_data['summary']['total_transactions'])
                    }
                )
                
        finally:
            close_db_connection(conn)
            
    except HTTPException:
        raise
    except Exception as e:
        business_metrics.record_utility_operation("quickbooks_transactions_export", "error")
        raise HTTPException(status_code=500, detail=f"Error generating QuickBooks transactions export: {str(e)}") 