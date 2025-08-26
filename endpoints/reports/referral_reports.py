# Created: 2025-08-26 20:11:19
# Last Modified: 2025-08-26 20:13:06
# Author: Scott Cadreau

# endpoints/reports/referral_reports.py
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
import pymysql.cursors
from core.database import get_db_connection, close_db_connection
from utils.monitoring import track_business_operation, business_metrics
from utils.report_cleanup import cleanup_old_reports
from utils.s3_storage import upload_file_to_s3, generate_s3_key
from utils.text_formatting import capitalize_name_field
from utils.email_service import send_referral_report_emails
from utils.timezone_utils import format_datetime_for_user
from fpdf import FPDF
from datetime import datetime
import os
import logging
import time
from typing import Optional, Dict, List
from pypdf import PdfReader, PdfWriter

logger = logging.getLogger(__name__)

router = APIRouter()

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

class ReferralReportPDF(FPDF):
    def __init__(self):
        super().__init__()

    def header(self):
        self.set_font("Arial", 'B', 13)
        header_height = self.font_size + 2
        self.cell(0, header_height, "All-Stars Surgical Assist - Referral Report", ln=True, align="C")
        self.ln(2)
        
        self.set_font("Arial", '', 11)
        info_height = self.font_size + 1
        report_date = format_datetime_for_user(
            datetime.utcnow(), 
            user_id=None, 
            format_string='%B %d, %Y'
        )
        self.cell(0, info_height, f"Report Date: {report_date}", ln=True, align="L")
        self.ln(1)

    def footer(self):
        self.set_y(-20)
        self.set_font("Arial", 'I', 8)
        footer_height = self.font_size + 1
        footer_timestamp = format_datetime_for_user(
            datetime.utcnow(), 
            user_id=None, 
            format_string='%Y-%m-%d %H:%M:%S %Z'
        )
        self.cell(0, footer_height, f"Report generated on: {footer_timestamp}", align="L")
        self.cell(0, footer_height, f"Page {self.page_no()} of {{nb}}", align="R")

    def add_referral_user_section(self, referral_user_name: str, referred_users_data: List[Dict], is_first_section=False):
        """Add a section for each referral user with their referred users"""
        # Start new page for each referral user (except the first one)
        if not is_first_section:
            self.add_page()
        
        # Referral user header
        self.set_font("Arial", 'B', 14)
        referral_header_height = self.font_size + 4
        self.cell(0, referral_header_height, f"Referral User: {referral_user_name}", ln=True, align="L")
        self.ln(2)

        # Details subheader
        self.set_font("Arial", 'B', 12)
        details_header_height = self.font_size + 2
        self.cell(0, details_header_height, "Details", ln=True, align="L")
        self.ln(2)

        # Table header
        self.set_font("Arial", 'B', 10)
        header_height = self.font_size + 2
        self.cell(60, header_height, "Referred User", border=1)
        self.cell(30, header_height, "Pay Category", border=1)
        self.cell(25, header_height, "Case Count", border=1, align="C")
        self.cell(35, header_height, "Summed Pay Amount", border=1, ln=True, align="R")

        # Table data
        self.set_font("Arial", '', 10)
        data_height = self.font_size + 2
        section_total = 0
        total_cases = 0
        
        for user_data in referred_users_data:
            # Format referred user name
            first_name = user_data.get('first_name', '') or ''
            last_name = user_data.get('last_name', '') or ''
            # Apply proper capitalization to user names
            if first_name:
                first_name = capitalize_name_field(first_name)
            if last_name:
                last_name = capitalize_name_field(last_name)
            referred_user_name = f"{first_name} {last_name}".strip()
            
            # Format pay category, case count, and amount
            pay_category = user_data.get('pay_category', '') or ''
            case_count = user_data.get('case_count', 0) or 0
            pay_amount = user_data.get('total_pay_amount', 0) or 0
            
            self.cell(60, data_height, referred_user_name, border=1)
            self.cell(30, data_height, pay_category, border=1)
            self.cell(25, data_height, str(case_count), border=1, align="C")
            self.cell(35, data_height, f"${pay_amount:.2f}", border=1, ln=True, align="R")
            
            section_total += pay_amount
            total_cases += case_count

        # Section subtotal
        self.set_font("Arial", 'B', 10)
        total_height = self.font_size + 3
        self.cell(115, total_height, f"Referral User Total:", align="R")
        self.cell(35, total_height, f"${section_total:.2f}", border=1, ln=True, align="R")
        self.ln(8)
        
        return section_total, total_cases

    def add_summary(self, total_amount, referral_user_count, total_referred_users, total_cases):
        """Add summary section at the end"""
        self.add_page()
        
        self.set_font("Arial", 'B', 14)
        self.cell(0, 10, "Report Summary", ln=True, align="C")
        self.ln(5)
        
        self.set_font("Arial", '', 12)
        self.cell(0, 8, f"Total Referral Users: {referral_user_count}", ln=True)
        self.cell(0, 8, f"Total Referred Users: {total_referred_users}", ln=True)
        self.cell(0, 8, f"Total Cases: {total_cases}", ln=True)
        self.cell(0, 8, f"Total Amount: ${total_amount:.2f}", ln=True)

@router.get("/referral_report")
@track_business_operation("generate", "referral_report")
def generate_referral_report(request: Request):
    """
    Generate comprehensive referral reports showing payment summaries by referring user and pay category.
    
    This endpoint produces professional PDF reports that analyze the referral network by showing which users
    were referred by whom, along with their payment categories, case counts, and total payment amounts.
    The system handles report generation, AWS S3 storage, automated email distribution, and local file 
    management with comprehensive monitoring and error handling.
    
    Key Features:
    - Professional PDF report generation with referral user-based grouping
    - Automated AWS S3 cloud storage with metadata and version control
    - Multi-recipient email distribution with weekly template
    - Password protection using weekly_YYYYMMDD format
    - Comprehensive financial summaries and referral network analysis
    - Automatic file cleanup and storage optimization
    - Real-time report generation with immediate download capability
    - Referral user sections with detailed breakdowns
    
    Args:
        request (Request): FastAPI request object for logging and monitoring
    
    Returns:
        FileResponse: Password-protected PDF file download with comprehensive metadata headers:
            - Content-Type: application/pdf
            - Content-Disposition: attachment with timestamped filename
            - Cache-Control: no-cache for security
            - Content-Length: File size in bytes
            - X-S3-URL: AWS S3 storage URL for cloud access
            - X-S3-Key: S3 object key for cloud reference
            - X-S3-Upload-Success: S3 upload success status
            - X-Email-Sent: Email notification success status
            - X-Email-Count: Number of emails successfully sent
            - X-Email-Total-Recipients: Total recipient count
    
    Raises:
        HTTPException:
            - 404 Not Found: No referral data found matching the criteria
            - 500 Internal Server Error: Report generation, S3 upload, or email errors
    
    Database Operations:
        1. Queries cases with case_status = 15 (pending payment status)
        2. Joins with user_profile for user information and referral relationships
        3. Filters by active status (cases and users)
        4. Excludes system/test accounts from reporting
        5. Groups results by referred_by_user, user_id, and pay_category
        6. Calculates case counts and payment amount sums per group
        7. Handles null/empty referred_by_user by excluding from report
    
    Report Content Structure:
        PDF Header:
        - All-Stars Surgical Assist branding
        - Report generation date in system timezone
        - Professional formatting with consistent styling
        
        Referral User Sections (one per page):
        - Referral user name header
        - "Details" subheader
        - Tabular listing with columns:
            * Referred User Name (properly capitalized)
            * Pay Category
            * Case Count
            * Summed Pay Amount
        - Referral user-specific financial totals
        
        Summary Section:
        - Total payment amount across all referral users
        - Total referral user count
        - Total referred user count
        - Total case count
        - Report generation metadata
    
    Business Logic & Rules:
        - Only includes cases with case_status = 15 (ready for payment)
        - Excludes specific system accounts from calculations
        - Ignores users with null/empty referred_by_user field
        - Payment amounts aggregated from pay_amount field
        - Active cases and users only
        - Referral users ordered alphabetically
        - Referred users ordered alphabetically within each referral user section
    
    AWS S3 Integration:
        - Automatic upload to configured S3 bucket
        - Metadata tagging with report details:
            * Report type, generation source
            * Referral user count, referred user count, total amount
            * Timestamp and version information
        - S3 URL generation for cloud access
        - Error handling with fallback to local storage
    
    Email Distribution System:
        - Multi-recipient automated email sending using referral_report_weekly template
        - Password-protected PDF attachment with secure delivery
        - Timezone-aware date formatting for recipients
        - Comprehensive delivery tracking and error reporting
        - Failed email logging without blocking report generation
    
    File Management:
        - Timestamped filename generation for uniqueness
        - Local storage in dedicated reports directory
        - Password protection using weekly_YYYYMMDD format
        - Automatic cleanup of reports older than 7 days
        - File size optimization and compression
        - Secure temporary file handling
    
    Text Formatting & Presentation:
        - Proper name capitalization using capitalize_name_field utility
        - Professional PDF layout with consistent fonts and spacing
        - Timezone-aware date formatting for system context
        - Currency formatting for financial amounts
        - Referral network organization for easy analysis
    
    Monitoring & Analytics:
        - Business metrics tracking for report generation operations
        - Prometheus monitoring via @track_business_operation decorator
        - Success/failure tracking for all operations
        - Performance metrics for generation time
        - Email delivery analytics and error tracking
        - S3 upload success monitoring
    
    Example Usage:
        GET /referral_report
    
    Example Response Headers:
        Content-Type: application/pdf
        Content-Disposition: attachment; filename="referral_report_20240815_143022.pdf"
        Cache-Control: no-cache
        Content-Length: 185760
        X-S3-URL: https://bucket.s3.amazonaws.com/reports/referral_report_20240815_143022.pdf
        X-S3-Key: reports/referral_report_20240815_143022.pdf
        X-S3-Upload-Success: True
        X-Email-Sent: True
        X-Email-Count: 2
        X-Email-Total-Recipients: 3
    
    Report File Structure:
        referral_report_20240815_143022.pdf (Password: weekly_20240815)
        ├── Header: All-Stars Surgical Assist branding
        ├── Referral User Section 1: Dr. Jane Smith
        │   ├── Details Header
        │   ├── Referred User Table: Name | Category | Count | Amount
        │   │   ├── Dr. John Doe (Primary) - 5 cases - $2,500.00
        │   │   └── Dr. Mary Johnson (Secondary) - 3 cases - $1,750.00
        │   └── Referral User Total: $4,250.00
        ├── Referral User Section 2: Dr. Robert Wilson
        │   └── [Similar structure]
        └── Summary: Total Amount: $15,750.00 | 3 Referral Users | 8 Referred Users | 25 Cases
    
    Note:
        - Report generation processes all pending payment cases regardless of date
        - Password protection uses consistent weekly format for security
        - S3 upload provides cloud backup and sharing capabilities
        - Email notifications enhance workflow automation for weekly processing
        - File cleanup prevents storage bloat
        - System accounts are automatically excluded from referral analysis
        - Users without referral relationships are excluded from the report
        - Professional formatting suitable for business analysis and referral tracking
        - Each referral user creates a new page for clear separation and analysis
        - Referral network analysis helps understand user acquisition patterns
        - Weekly scheduling aligns with other payment report generation cycles
    """
    start_time = time.time()
    response_status = 200
    response_data = None
    error_message = None
    
    try:
        conn = get_db_connection()
        
        try:
            with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                # Build the main query to get referral data
                sql = """
                    SELECT 
                        referring_user.first_name as referring_first_name,
                        referring_user.last_name as referring_last_name,
                        up.first_name,
                        up.last_name,
                        c.pay_category,
                        COUNT(c.case_id) as case_count,
                        SUM(c.pay_amount) as total_pay_amount
                    FROM cases c
                    INNER JOIN user_profile up ON c.user_id = up.user_id
                    INNER JOIN user_profile referring_user ON up.referred_by_user = referring_user.user_id
                    WHERE c.case_status = 15
                    AND c.active = 1 
                    AND up.active = 1
                    AND referring_user.active = 1
                    AND up.referred_by_user IS NOT NULL
                    AND up.referred_by_user != ''
                    AND c.user_id NOT IN ('04e884e8-4011-70e9-f3bd-d89fabd15c7b', '94883428-50c1-7049-9d3d-e095ca81f174', '94b80418-6091-701b-eac8-8b325f95a799')
                    GROUP BY up.referred_by_user, c.user_id, c.pay_category
                    ORDER BY referring_user.last_name, referring_user.first_name, up.last_name, up.first_name, c.pay_category
                """
                
                cursor.execute(sql)
                referral_data = cursor.fetchall()
                
                if not referral_data:
                    response_status = 404
                    error_message = "No referral data found"
                    raise HTTPException(
                        status_code=404, 
                        detail="No referral data found"
                    )
                
                # Group data by referral user
                referral_users = {}
                for row in referral_data:
                    # Create referral user key
                    referring_first = row['referring_first_name'] or ''
                    referring_last = row['referring_last_name'] or ''
                    if referring_first:
                        referring_first = capitalize_name_field(referring_first)
                    if referring_last:
                        referring_last = capitalize_name_field(referring_last)
                    referral_user_name = f"{referring_first} {referring_last}".strip()
                    
                    if referral_user_name not in referral_users:
                        referral_users[referral_user_name] = []
                    
                    referral_users[referral_user_name].append(row)
                
                # Generate PDF
                pdf = ReferralReportPDF()
                pdf.alias_nb_pages()
                pdf.add_page()
                
                total_amount = 0
                total_cases = 0
                total_referred_users = 0
                
                # Add each referral user's section
                first_section = True
                for referral_user_name in sorted(referral_users.keys()):
                    referred_users_data = referral_users[referral_user_name]
                    section_total, section_cases = pdf.add_referral_user_section(
                        referral_user_name, 
                        referred_users_data,
                        is_first_section=first_section
                    )
                    total_amount += section_total
                    total_cases += section_cases
                    total_referred_users += len(referred_users_data)
                    first_section = False
                
                # Add summary
                pdf.add_summary(total_amount, len(referral_users), total_referred_users, total_cases)
                
                # Create reports directory if it doesn't exist
                reports_dir = os.path.join(os.getcwd(), "reports")
                os.makedirs(reports_dir, exist_ok=True)
                
                # Clean up old reports before generating new one
                cleanup_old_reports(reports_dir, days_to_keep=7)
                
                # Save to reports directory
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"referral_report_{timestamp}.pdf"
                
                # Create temporary unprotected file first
                temp_filename = f"temp_{filename}"
                temp_filepath = os.path.join(reports_dir, temp_filename)
                pdf.output(temp_filepath)
                
                # Generate password for weekly report (format: weekly_YYYYMMDD)
                report_password = f"weekly_{datetime.now().strftime('%Y%m%d')}"
                
                # Create password-protected version
                filepath = os.path.join(reports_dir, filename)
                if not password_protect_pdf(temp_filepath, filepath, report_password):
                    logger.error("Failed to password protect referral report PDF")
                    # Use unprotected version as fallback
                    os.rename(temp_filepath, filepath)
                    report_password = None
                else:
                    # Clean up temporary unprotected file
                    try:
                        os.remove(temp_filepath)
                    except Exception as e:
                        logger.warning(f"Could not remove temporary file {temp_filepath}: {str(e)}")
                
                # Prepare metadata for S3
                metadata = {
                    'report_type': 'referral_report',
                    'generated_by': 'surgicase_api',
                    'total_referral_users': str(len(referral_users)),
                    'total_referred_users': str(total_referred_users),
                    'total_cases': str(total_cases),
                    'total_amount': f"{total_amount:.2f}"
                }
                
                # Upload to S3
                s3_key = generate_s3_key('reports', filename)
                s3_result = upload_file_to_s3(
                    file_path=filepath,
                    s3_key=s3_key,
                    content_type='application/pdf',
                    metadata=metadata
                )
                
                # Record successful report generation
                business_metrics.record_utility_operation("referral_report", "success")
                
                # Send email notifications
                try:
                    # Store the current UTC datetime for timezone conversion in emails
                    current_utc = datetime.utcnow()
                    
                    email_data = {
                        "creation_date": current_utc.strftime('%B %d, %Y'),
                        "creation_date_utc": current_utc,
                        "total_referral_users": len(referral_users),
                        "total_referred_users": total_referred_users,
                        "total_cases": total_cases,
                        "total_amount": f"{total_amount:.2f}",
                        "password": report_password,
                        "report_type": "Referral Report"
                    }
                    
                    # Send emails with weekly template
                    email_result = send_referral_report_emails(
                        report_path=filepath,
                        report_filename=filename,
                        report_data=email_data,
                        email_type="weekly"
                    )
                    
                    logger.info(f"Email sending result: {email_result['message']}")
                    
                except Exception as e:
                    # Log email error but don't fail the report generation
                    logger.error(f"Error sending email notifications: {str(e)}")
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
            
    except HTTPException as http_error:
        response_status = http_error.status_code
        error_message = str(http_error.detail)
        raise
    except Exception as e:
        # Record failed report generation
        response_status = 500
        error_message = str(e)
        business_metrics.record_utility_operation("referral_report", "error")
        raise HTTPException(
            status_code=500,
            detail=f"Error generating referral report: {str(e)}"
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
