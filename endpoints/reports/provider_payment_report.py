# Created: 2025-01-27 10:00:00
# Last Modified: 2025-08-03 16:41:58
# Author: Scott Cadreau

# endpoints/reports/provider_payment_report.py
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
import pymysql.cursors
from core.database import get_db_connection, close_db_connection
from utils.monitoring import track_business_operation, business_metrics
from utils.report_cleanup import cleanup_old_reports, get_reports_directory_size
from utils.s3_storage import upload_file_to_s3, generate_s3_key
from utils.text_formatting import capitalize_name_field
from utils.email_service import send_provider_payment_report_emails
from utils.timezone_utils import format_datetime_for_user
from fpdf import FPDF
from datetime import datetime, timedelta
import os
import tempfile
import logging
from typing import Optional
from pypdf import PdfReader, PdfWriter

logger = logging.getLogger(__name__)

router = APIRouter()

def get_upcoming_friday(run_date=None):
    """Calculate the upcoming Friday from the given date (or today if not provided)"""
    if run_date is None:
        run_date = datetime.now().date()
    elif isinstance(run_date, datetime):
        run_date = run_date.date()
    
    # Find the next Friday (weekday 4)
    # Monday=0, Tuesday=1, Wednesday=2, Thursday=3, Friday=4, Saturday=5, Sunday=6
    days_until_friday = (4 - run_date.weekday()) % 7
    
    # If today is Friday, get next Friday (7 days from now)
    if days_until_friday == 0:
        days_until_friday = 7
    
    upcoming_friday = run_date + timedelta(days=days_until_friday)
    return upcoming_friday

class ProviderPaymentReportPDF(FPDF):
    def __init__(self, user_id: Optional[str] = None):
        super().__init__()
        self.user_id = user_id

    def header(self):
        self.set_font("Arial", 'B', 13)
        header_height = self.font_size + 2
        self.cell(0, header_height, "All-Stars Surgical Assist - Provider Payment Report", ln=True, align="C")
        self.ln(2)
        
        self.set_font("Arial", '', 11)
        info_height = self.font_size + 1
        # Use user's timezone for report date
        report_date = format_datetime_for_user(
            datetime.utcnow(), 
            user_id=self.user_id, 
            format_string='%B %d, %Y'
        )
        self.cell(0, info_height, f"Report Date: {report_date}", ln=True, align="L")
        self.ln(1)

    def footer(self):
        self.set_y(-20)
        self.set_font("Arial", 'I', 8)
        footer_height = self.font_size + 1
        # Use user's timezone for footer timestamp
        footer_timestamp = format_datetime_for_user(
            datetime.utcnow(), 
            user_id=self.user_id, 
            format_string='%Y-%m-%d %H:%M:%S %Z'
        )
        self.cell(0, footer_height, f"Report generated on: {footer_timestamp}", align="L")
        self.cell(0, footer_height, f"Page {self.page_no()} of {{nb}}", align="R")

    def add_provider_section(self, provider_data, cases_data, is_first_provider=False):
        """Add a section for each provider with their cases"""
        # Start new page for each provider (except the first one)
        if not is_first_provider:
            self.add_page()
        
        # Provider header
        self.set_font("Arial", '', 11)
        provider_height = self.font_size + 2
        first_name = provider_data.get('first_name', '') or ''
        last_name = provider_data.get('last_name', '') or ''
        # Apply proper capitalization to provider names
        if first_name:
            first_name = capitalize_name_field(first_name)
        if last_name:
            last_name = capitalize_name_field(last_name)
        provider_name = f"Provider: {first_name} {last_name}".strip()
        if provider_data.get('user_npi'):
            provider_name += f" (NPI: {provider_data['user_npi']})"
        
        self.cell(0, provider_height, provider_name, ln=True, align="L")
        
        # Add projected pay date line below provider name
        projected_pay_date = get_upcoming_friday()
        projected_pay_text = f"Projected Pay Date: {projected_pay_date.strftime('%B %d, %Y')}"
        self.cell(0, provider_height, projected_pay_text, ln=True, align="L")
        self.ln(2)

        # Table header
        self.set_font("Arial", 'B', 10)
        header_height = self.font_size + 2
        self.cell(25, header_height, "Date", border=1)
        self.cell(50, header_height, "Patient Name", border=1)
        self.cell(55, header_height, "Procedure(s)", border=1)
        self.cell(30, header_height, "Category", border=1)
        self.cell(20, header_height, "Amount", border=1, ln=True, align="R")

        # Table data
        self.set_font("Arial", '', 10)
        data_height = self.font_size + 2
        provider_total = 0
        
        for case in cases_data:
            # Format date
            case_date = case['case_date']
            if hasattr(case_date, 'strftime'):
                formatted_date = case_date.strftime('%Y-%m-%d')
            else:
                formatted_date = str(case_date)[:10]  # Take first 10 chars if it's a string
            
            # Format patient name
            patient_first = case.get('patient_first', '') or ''
            patient_last = case.get('patient_last', '') or ''
            # Apply proper capitalization to patient names
            if patient_first:
                patient_first = capitalize_name_field(patient_first)
            if patient_last:
                patient_last = capitalize_name_field(patient_last)
            patient_name = f"{patient_first} {patient_last}".strip()
            
            # Format procedures
            procedures = case.get('procedures', '')
            if isinstance(procedures, list):
                procedures = ', '.join(procedures) if procedures else ''
            elif procedures is None:
                procedures = ''
            
            # Format amount
            amount = case.get('pay_amount', 0) or 0
            
            self.cell(25, data_height, formatted_date, border=1)
            self.cell(50, data_height, patient_name, border=1)
            self.cell(55, data_height, procedures, border=1)
            self.cell(30, data_height, case.get('pay_category', '') or '', border=1)
            self.cell(20, data_height, f"${amount:.2f}", border=1, ln=True, align="R")
            provider_total += amount

        # Provider subtotal
        self.set_font("Arial", 'B', 10)
        total_height = self.font_size + 3
        self.cell(160, total_height, f"Provider Total:", align="R")
        self.cell(20, total_height, f"${provider_total:.2f}", border=1, ln=True, align="R")
        self.ln(5)
        
        return provider_total

    def add_summary(self, total_amount, provider_count, case_count):
        """Add summary section at the end"""
        self.add_page()
        
        self.set_font("Arial", 'B', 14)
        self.cell(0, 10, "Report Summary", ln=True, align="C")
        self.ln(5)
        
        self.set_font("Arial", '', 12)
        self.cell(0, 8, f"Total Providers: {provider_count}", ln=True)
        self.cell(0, 8, f"Total Cases: {case_count}", ln=True)
        self.cell(0, 8, f"Total Amount: ${total_amount:.2f}", ln=True)

def password_protect_pdf(input_path: str, output_path: str, password: str) -> bool:
    """
    Password protect a PDF file using pypdf
    
    Args:
        input_path: Path to the input PDF file
        output_path: Path to save the password-protected PDF
        password: Password to protect the PDF with
        
    Returns:
        True if successful, False otherwise
    """
    try:
        reader = PdfReader(input_path)
        writer = PdfWriter()
        
        # Add all pages from the reader to the writer
        for page in reader.pages:
            writer.add_page(page)
        
        # Encrypt the PDF with the password
        writer.encrypt(password)
        
        # Write the password-protected PDF
        with open(output_path, "wb") as output_file:
            writer.write(output_file)
        
        logger.info(f"Successfully password-protected PDF: {output_path}")
        return True
        
    except Exception as e:
        logger.error(f"Error password protecting PDF: {str(e)}")
        return False

def generate_provider_password(last_name: str, npi: str) -> str:
    """
    Generate password for provider using last_name_npi format
    
    Args:
        last_name: Provider's last name
        npi: Provider's NPI number
        
    Returns:
        Generated password in lowercase
    """
    if not last_name or not npi:
        raise ValueError("Both last_name and npi are required for password generation")
    
    # Convert to lowercase and create password
    password = f"{last_name.lower()}_{npi}"
    return password

@router.get("/provider_payment_report")
@track_business_operation("generate", "provider_payment_report")
def generate_provider_payment_report(
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    user_id: Optional[str] = Query(None, description="Filter by specific provider user_id"),
    email_type: Optional[str] = Query("on_demand", description="Email template type: 'weekly' or 'on_demand'")
):
    """
    Generate a provider payment report as a PDF file.
    Returns cases with case_status=1 grouped by provider.
    """
    try:
        conn = get_db_connection()
        
        try:
            with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                # Build the main query
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
                
                # Add date filters if provided
                if start_date:
                    sql += " AND c.case_date >= %s"
                    params.append(start_date)
                if end_date:
                    sql += " AND c.case_date <= %s"
                    params.append(end_date)
                
                # Add user filter if provided
                if user_id:
                    sql += " AND c.user_id = %s"
                    params.append(user_id)
                
                # Order by user_id and case_date
                sql += " ORDER BY c.user_id, c.case_date"
                
                cursor.execute(sql, params)
                cases = cursor.fetchall()
                
                if not cases:
                    raise HTTPException(
                        status_code=404, 
                        detail="No cases found matching the criteria"
                    )
                
                # Get procedure codes for each case
                for case in cases:
                    cursor.execute(
                        "SELECT procedure_code FROM case_procedure_codes WHERE case_id = %s",
                        (case['case_id'],)
                    )
                    procedure_codes = [row['procedure_code'] for row in cursor.fetchall()]
                    case['procedures'] = procedure_codes
                
                # Group cases by provider
                providers = {}
                for case in cases:
                    user_id = case['user_id']
                    if user_id not in providers:
                        providers[user_id] = {
                            'provider_data': {
                                'first_name': case['first_name'],
                                'last_name': case['last_name'],
                                'user_npi': case['user_npi']
                            },
                            'cases': []
                        }
                    providers[user_id]['cases'].append(case)
                
                # Generate PDF
                pdf = ProviderPaymentReportPDF(user_id=user_id)
                pdf.alias_nb_pages()
                pdf.add_page()
                
                total_amount = 0
                total_cases = 0
                
                # Add each provider's section
                first_provider = True
                for user_id, provider_info in providers.items():
                    provider_total = pdf.add_provider_section(
                        provider_info['provider_data'], 
                        provider_info['cases'],
                        is_first_provider=first_provider
                    )
                    total_amount += provider_total
                    total_cases += len(provider_info['cases'])
                    first_provider = False
                
                # Add summary
                pdf.add_summary(total_amount, len(providers), total_cases)
                
                # Create reports directory if it doesn't exist
                reports_dir = os.path.join(os.getcwd(), "reports")
                os.makedirs(reports_dir, exist_ok=True)
                
                # Clean up old reports before generating new one
                cleanup_old_reports(reports_dir, days_to_keep=7)
                
                # Save to reports directory
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"provider_payment_report_{timestamp}.pdf"
                filepath = os.path.join(reports_dir, filename)
                
                pdf.output(filepath)
                
                # Prepare metadata for S3
                metadata = {
                    'report_type': 'provider_payment',
                    'generated_by': 'surgicase_api',
                    'total_providers': str(len(providers)),
                    'total_cases': str(total_cases),
                    'total_amount': f"{total_amount:.2f}",
                    'start_date': start_date or 'all',
                    'end_date': end_date or 'all',
                    'user_filter': user_id or 'all'
                }
                
                # Upload to S3
                s3_key = generate_s3_key('', filename)
                s3_result = upload_file_to_s3(
                    file_path=filepath,
                    s3_key=s3_key,
                    content_type='application/pdf',
                    metadata=metadata
                )
                
                # Record successful report generation
                business_metrics.record_utility_operation("provider_report", "success")
                
                # Send email notifications
                try:
                    # Prepare email data
                    report_date_range = ""
                    if start_date and end_date:
                        report_date_range = f"{start_date} to {end_date}"
                    elif start_date:
                        report_date_range = f"from {start_date}"
                    elif end_date:
                        report_date_range = f"through {end_date}"
                    else:
                        report_date_range = "all dates"
                    
                    # Store the current UTC datetime for timezone conversion in emails
                    current_utc = datetime.utcnow()
                    
                    email_data = {
                        "creation_date": current_utc.strftime('%B %d, %Y'),  # Fallback for templates that expect string
                        "creation_date_utc": current_utc,  # UTC datetime for timezone conversion
                        "report_date": report_date_range,
                        "total_providers": len(providers),
                        "total_cases": total_cases,
                        "total_amount": f"{total_amount:.2f}"
                    }
                    
                    # Send emails with appropriate template type
                    email_result = send_provider_payment_report_emails(
                        report_path=filepath,
                        report_filename=filename,
                        report_data=email_data,
                        email_type=email_type  # Use parameter: "weekly" for scheduled, "on_demand" for manual
                    )
                    
                    # Log with user_id only if filtering by specific provider
                    extra_data = {'provider_filter': user_id} if user_id else {}
                    logger.info(f"Email sending result: {email_result['message']}", extra=extra_data)
                    
                except Exception as e:
                    # Log email error but don't fail the report generation
                    # Log with user_id only if filtering by specific provider
                    extra_data = {'provider_filter': user_id} if user_id else {}
                    logger.error(f"Error sending email notifications: {str(e)}", extra=extra_data)
                    email_result = {
                        "success": False,
                        "message": f"Email sending failed: {str(e)}",
                        "emails_sent": 0
                    }
                
                # Prepare response with S3 and email information
                response_data = {
                    "local_file": filepath,
                    "filename": filename,
                    "s3_upload": s3_result,
                    "email_notifications": email_result
                }
                
                # Return file for download with proper headers and S3 info
                return FileResponse(
                    path=filepath,
                    filename=filename,
                    media_type='application/pdf',
                    headers={
                        'Content-Disposition': f'attachment; filename="{filename}"',
                        'Cache-Control': 'no-cache',
                        'Content-Length': str(os.path.getsize(filepath)),
                        'X-S3-URL': s3_result.get('s3_url', ''),
                        'X-S3-Key': s3_result.get('s3_key', ''),
                        'X-S3-Upload-Success': str(s3_result.get('success', False)),
                        'X-Email-Sent': str(email_result.get('success', False)),
                        'X-Email-Count': str(email_result.get('emails_sent', 0)),
                        'X-Email-Total-Recipients': str(email_result.get('total_recipients', 0))
                    }
                )
                
        finally:
            close_db_connection(conn)
            
    except HTTPException:
        raise
    except Exception as e:
        # Record failed report generation
        business_metrics.record_utility_operation("provider_report", "error")
        raise HTTPException(
            status_code=500,
            detail=f"Error generating report: {str(e)}"
        )

@router.get("/individual_provider_reports")
@track_business_operation("generate", "individual_provider_reports")
def generate_individual_provider_reports_endpoint(
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    email_type: Optional[str] = Query("weekly", description="Email template type: 'weekly' or 'on_demand'")
):
    """
    Generate individual password-protected PDF reports for each provider
    and send them via email. Each provider receives only their own cases.
    """
    try:
        # Record business operation start
        business_metrics.record_utility_operation("individual_provider_reports", "start")
        
        # Clean up old reports first
        cleanup_old_reports()
        
        # Generate individual reports for all providers
        result = generate_individual_provider_reports(
            start_date=start_date,
            end_date=end_date,
            email_type=email_type
        )
        
        if result["success"]:
            business_metrics.record_utility_operation("individual_provider_reports", "success")
        else:
            business_metrics.record_utility_operation("individual_provider_reports", "error")
        
        return {
            "message": result["message"],
            "success": result["success"],
            "providers_processed": result["providers_processed"],
            "reports_generated": result["reports_generated"],
            "emails_sent": result["emails_sent"],
            "errors": result["errors"]
        }
        
    except Exception as e:
        business_metrics.record_utility_operation("individual_provider_reports", "error")
        logger.error(f"Error in individual provider reports endpoint: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error generating individual provider reports: {str(e)}"
        )

def generate_individual_provider_reports(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    email_type: str = "weekly"
) -> dict:
    """
    Generate individual password-protected PDF reports for each provider
    and send them via email
    
    Args:
        start_date: Start date filter (YYYY-MM-DD)
        end_date: End date filter (YYYY-MM-DD)
        email_type: Email template type
        
    Returns:
        Dictionary with generation results
    """
    try:
        conn = get_db_connection()
        results = {
            "success": True,
            "message": "Individual provider reports generated successfully",
            "providers_processed": 0,
            "reports_generated": 0,
            "emails_sent": 0,
            "errors": []
        }
        
        try:
            with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                # Get all providers who have cases with case_status=15
                sql = """
                    SELECT DISTINCT
                        c.user_id,
                        up.first_name,
                        up.last_name,
                        up.user_npi,
                        up.user_email
                    FROM cases c
                    INNER JOIN user_profile up ON c.user_id = up.user_id
                    WHERE c.case_status = 15
                    AND c.active = 1 
                    AND up.active = 1
                """
                params = []
                
                # Add date filters if provided
                if start_date:
                    sql += " AND c.case_date >= %s"
                    params.append(start_date)
                if end_date:
                    sql += " AND c.case_date <= %s"
                    params.append(end_date)
                
                sql += " ORDER BY up.last_name, up.first_name"
                
                cursor.execute(sql, params)
                providers = cursor.fetchall()
                
                if not providers:
                    logger.info("No providers found with cases matching the criteria")
                    results["message"] = "No providers found with cases"
                    return results
                
                logger.info(f"Found {len(providers)} providers to process")
                results["providers_processed"] = len(providers)
                
                # Generate individual report for each provider
                for provider in providers:
                    try:
                        user_id = provider['user_id']
                        first_name = provider['first_name'] or ''
                        last_name = provider['last_name'] or ''
                        npi = provider['user_npi'] or ''
                        email = provider['user_email'] or ''
                        
                        # Skip if missing critical information
                        if not last_name or not npi or not email:
                            error_msg = f"Provider {user_id} missing required info (last_name: {bool(last_name)}, npi: {bool(npi)}, email: {bool(email)})"
                            logger.warning(error_msg)
                            results["errors"].append({
                                "provider": user_id,
                                "error": error_msg
                            })
                            continue
                        
                        # Generate individual provider report
                        report_result = generate_single_provider_report(
                            user_id=user_id,
                            start_date=start_date,
                            end_date=end_date,
                            email_type=email_type,
                            provider_info=provider
                        )
                        
                        if report_result["success"]:
                            results["reports_generated"] += 1
                            if report_result.get("email_sent"):
                                results["emails_sent"] += 1
                        else:
                            results["errors"].append({
                                "provider": user_id,
                                "error": report_result.get("error", "Unknown error")
                            })
                        
                    except Exception as e:
                        error_msg = f"Error processing provider {provider.get('user_id', 'unknown')}: {str(e)}"
                        logger.error(error_msg)
                        results["errors"].append({
                            "provider": provider.get('user_id', 'unknown'),
                            "error": error_msg
                        })
                
                # Update final success status
                if results["errors"]:
                    results["success"] = len(results["errors"]) < results["providers_processed"]
                    if not results["success"]:
                        results["message"] = "Failed to generate reports for all providers"
                    else:
                        results["message"] = f"Generated {results['reports_generated']} reports with {len(results['errors'])} errors"
                
                logger.info(f"Individual provider reports completed: {results['reports_generated']} generated, {results['emails_sent']} emailed, {len(results['errors'])} errors")
                return results
                
        finally:
            close_db_connection(conn)
            
    except Exception as e:
        logger.error(f"Error in generate_individual_provider_reports: {str(e)}")
        return {
            "success": False,
            "message": f"Failed to generate individual provider reports: {str(e)}",
            "providers_processed": 0,
            "reports_generated": 0,
            "emails_sent": 0,
            "errors": [{"provider": "system", "error": str(e)}]
        }

def generate_single_provider_report(
    user_id: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    email_type: str = "weekly",
    provider_info: Optional[dict] = None
) -> dict:
    """
    Generate a single provider's password-protected report and send via email
    
    Args:
        user_id: Provider's user ID
        start_date: Start date filter
        end_date: End date filter
        email_type: Email template type
        provider_info: Provider information dict (to avoid extra DB query)
        
    Returns:
        Dictionary with generation results
    """
    try:
        conn = get_db_connection()
        
        try:
            with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                # Build the main query for this specific provider
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
                    AND c.user_id = %s
                """
                params = [user_id]
                
                # Add date filters if provided
                if start_date:
                    sql += " AND c.case_date >= %s"
                    params.append(start_date)
                if end_date:
                    sql += " AND c.case_date <= %s"
                    params.append(end_date)
                
                # Order by case_date
                sql += " ORDER BY c.case_date"
                
                cursor.execute(sql, params)
                cases = cursor.fetchall()
                
                if not cases:
                    return {
                        "success": False,
                        "error": f"No cases found for provider {user_id}",
                        "provider": user_id,
                        "email_sent": False
                    }
                
                # Get procedure codes for each case
                for case in cases:
                    cursor.execute(
                        "SELECT procedure_code FROM case_procedure_codes WHERE case_id = %s",
                        (case['case_id'],)
                    )
                    procedure_codes = [row['procedure_code'] for row in cursor.fetchall()]
                    case['procedures'] = procedure_codes
                
                # Generate PDF for this provider only
                provider_data = {
                    'provider_data': {
                        'first_name': cases[0]['first_name'],
                        'last_name': cases[0]['last_name'],
                        'user_npi': cases[0]['user_npi']
                    },
                    'cases': cases
                }
                
                # Create PDF
                pdf = ProviderPaymentReportPDF(user_id=user_id)
                pdf.add_page()
                
                # Add provider section
                total_amount = pdf.add_provider_section(
                    provider_data['provider_data'], 
                    provider_data['cases'], 
                    is_first_provider=True
                )
                
                # Generate unique filename
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                npi = provider_info['user_npi']
                date_str = datetime.now().strftime('%Y%m%d')
                filename = f"provider_payment_report_{npi}_{date_str}.pdf"
                
                # Get reports directory
                reports_dir = "reports"
                os.makedirs(reports_dir, exist_ok=True)
                
                # Temporary unprotected file
                temp_filename = f"temp_{filename}"
                temp_filepath = os.path.join(reports_dir, temp_filename)
                
                # Save unprotected PDF first
                pdf.output(temp_filepath)
                
                # Generate password
                password = generate_provider_password(
                    provider_info['last_name'],
                    provider_info['user_npi']
                )
                
                # Create password-protected version
                protected_filepath = os.path.join(reports_dir, filename)
                
                # Password protect the PDF
                if not password_protect_pdf(temp_filepath, protected_filepath, password):
                    raise Exception("Failed to password protect PDF")
                
                # Clean up temporary unprotected file
                try:
                    os.remove(temp_filepath)
                except Exception as e:
                    logger.warning(f"Could not remove temporary file {temp_filepath}: {str(e)}")
                
                # Upload to S3
                try:
                    s3_key = generate_s3_key('individual-provider-payment', filename)
                    s3_result = upload_file_to_s3(
                        file_path=protected_filepath,
                        s3_key=s3_key,
                        metadata={
                            'report_type': 'individual_provider_payment',
                            'provider_id': user_id,
                            'npi': npi,
                            'creation_date': datetime.now().isoformat(),
                            'case_count': str(len(cases)),
                            'total_amount': str(total_amount)
                        }
                    )
                except Exception as e:
                    logger.error(f"S3 upload failed for {filename}: {str(e)}")
                    s3_result = {"success": False, "message": str(e)}
                
                # Send email to provider
                email_sent = send_individual_provider_email(
                    provider_info=provider_info,
                    report_path=protected_filepath,
                    report_filename=filename,
                    password=password,
                    email_type=email_type,
                    total_amount=total_amount,
                    case_count=len(cases)
                )
                
                return {
                    "success": True,
                    "message": f"Report generated for provider {user_id}",
                    "report_path": protected_filepath,
                    "email_sent": email_sent,
                    "provider": user_id,
                    "case_count": len(cases),
                    "total_amount": total_amount,
                    "s3_upload": s3_result
                }
                
        finally:
            close_db_connection(conn)
        
    except Exception as e:
        logger.error(f"Error generating single provider report for {user_id}: {str(e)}")
        return {
            "success": False,
            "error": str(e),
            "provider": user_id,
            "email_sent": False
        }

def send_individual_provider_email(
    provider_info: dict,
    report_path: str,
    report_filename: str,
    password: str,
    email_type: str = "weekly",
    total_amount: float = 0.0,
    case_count: int = 0
) -> bool:
    """
    Send individual provider report email
    
    Args:
        provider_info: Provider information dictionary
        report_path: Path to the password-protected PDF
        report_filename: Name of the PDF file
        password: PDF password
        email_type: Email template type
        total_amount: Total payment amount for this provider
        case_count: Number of cases for this provider
        
    Returns:
        True if email sent successfully, False otherwise
    """
    try:
        from utils.email_service import send_individual_provider_payment_report_email
        
        # Prepare email data
        email_data = {
            "provider_name": f"{provider_info.get('first_name', '')} {provider_info.get('last_name', '')}".strip(),
            "npi": provider_info.get('user_npi', ''),
            "creation_date": datetime.now().strftime('%B %d, %Y'),
            "filename": report_filename,
            "password": password,
            "total_amount": f"${total_amount:.2f}",
            "case_count": str(case_count)
        }
        
        # Send email
        result = send_individual_provider_payment_report_email(
            provider_email=provider_info['user_email'],
            provider_info=provider_info,
            report_path=report_path,
            report_filename=report_filename,
            email_data=email_data,
            email_type=email_type
        )
        
        return result.get('success', False)
        
    except Exception as e:
        logger.error(f"Error sending email to provider {provider_info.get('user_id', 'unknown')}: {str(e)}")
        return False 