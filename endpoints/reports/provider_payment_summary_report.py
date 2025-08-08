# Created: 2025-08-08 02:31:02
# Last Modified: 2025-08-08 17:17:52
# Author: Scott Cadreau

# endpoints/reports/provider_payment_summary_report.py
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse
import pymysql.cursors
from core.database import get_db_connection, close_db_connection
from utils.monitoring import track_business_operation, business_metrics
from utils.report_cleanup import cleanup_old_reports, get_reports_directory_size
from utils.s3_storage import upload_file_to_s3, generate_s3_key
from utils.text_formatting import capitalize_name_field
from utils.email_service import send_provider_payment_summary_report_emails
from utils.timezone_utils import format_datetime_for_user
from fpdf import FPDF
from datetime import datetime, timedelta
import os
import tempfile
import logging
import time
from typing import Optional, Dict, List

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

class ProviderPaymentSummaryReportPDF(FPDF):
    def __init__(self, user_id: Optional[str] = None):
        super().__init__()
        self.user_id = user_id

    def header(self):
        self.set_font("Arial", 'B', 13)
        header_height = self.font_size + 2
        self.cell(0, header_height, "All-Stars Surgical Assist - Provider Payment Summary Report", ln=True, align="C")
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

    def add_state_section(self, state_name: str, providers_data: List[Dict], is_first_state=False):
        """Add a section for each state with their providers"""
        # Start new page for each state (except the first one)
        if not is_first_state:
            self.add_page()
        
        # State header
        self.set_font("Arial", 'B', 14)
        state_header_height = self.font_size + 4
        self.cell(0, state_header_height, f"State: {state_name}", ln=True, align="L")
        self.ln(2)

        # Add projected pay date line below state name
#        projected_pay_date = get_upcoming_friday()
#        self.set_font("Arial", '', 11)
#        projected_pay_text = f"Projected Pay Date: {projected_pay_date.strftime('%B %d, %Y')}"#
#        self.cell(0, 8, projected_pay_text, ln=True, align="L")
#        self.ln(3)

        # Table header
        self.set_font("Arial", 'B', 10)
        header_height = self.font_size + 2
        self.cell(80, header_height, "Provider Name", border=1)
        self.cell(40, header_height, "NPI", border=1)
        self.cell(40, header_height, "Total Amount", border=1, ln=True, align="R")

        # Table data
        self.set_font("Arial", '', 10)
        data_height = self.font_size + 2
        state_total = 0
        
        for provider in providers_data:
            # Format provider name
            first_name = provider.get('first_name', '') or ''
            last_name = provider.get('last_name', '') or ''
            # Apply proper capitalization to provider names
            if first_name:
                first_name = capitalize_name_field(first_name)
            if last_name:
                last_name = capitalize_name_field(last_name)
            provider_name = f"{first_name} {last_name}".strip()
            
            # Format NPI
            npi = provider.get('user_npi', '') or ''
            if npi:
                npi = str(npi)
            
            # Format amount
            total_amount = provider.get('total_amount', 0) or 0
            
            self.cell(80, data_height, provider_name, border=1)
            self.cell(40, data_height, npi, border=1)
            self.cell(40, data_height, f"${total_amount:.2f}", border=1, ln=True, align="R")
            state_total += total_amount

        # State subtotal
        self.set_font("Arial", 'B', 10)
        total_height = self.font_size + 3
        self.cell(120, total_height, f"State Total:", align="R")
        self.cell(40, total_height, f"${state_total:.2f}", border=1, ln=True, align="R")
        self.ln(8)
        
        return state_total

    def add_summary(self, total_amount, state_count, provider_count):
        """Add summary section at the end"""
        self.add_page()
        
        self.set_font("Arial", 'B', 14)
        self.cell(0, 10, "Report Summary", ln=True, align="C")
        self.ln(5)
        
        self.set_font("Arial", '', 12)
        self.cell(0, 8, f"Total States: {state_count}", ln=True)
        self.cell(0, 8, f"Total Providers: {provider_count}", ln=True)
        self.cell(0, 8, f"Total Amount: ${total_amount:.2f}", ln=True)

@router.get("/provider_payment_summary_report")
@track_business_operation("generate", "provider_payment_summary_report")
def generate_provider_payment_summary_report(
    request: Request,
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    user_id: Optional[str] = Query(None, description="Filter by specific provider user_id"),
    email_type: Optional[str] = Query("on_demand", description="Email template type: 'weekly' or 'on_demand'")
):
    """
    Generate comprehensive provider payment summary reports grouped by state with automated distribution and cloud storage integration.
    
    This endpoint produces professional PDF summary reports showing provider payment totals grouped by state.
    Each state gets its own page with providers listed alphabetically within that state, showing provider name,
    NPI, and total payment amount. The system handles report generation, AWS S3 storage, automated email 
    distribution, and local file management with comprehensive monitoring and error handling.
    
    Key Features:
    - Professional PDF report generation with state-based grouping
    - Automated AWS S3 cloud storage with metadata and version control
    - Multi-recipient email distribution with customizable templates
    - Flexible date range and provider filtering capabilities
    - Projected payment date calculations (upcoming Friday logic)
    - State-wise financial summaries and provider breakdowns
    - Automatic file cleanup and storage optimization
    - Real-time report generation with immediate download capability
    - Alphabetical provider sorting within each state
    
    Args:
        request (Request): FastAPI request object for logging and monitoring
        start_date (str, optional): Start date for case filtering in YYYY-MM-DD format
                                   Filters cases where case_date >= start_date
        end_date (str, optional): End date for case filtering in YYYY-MM-DD format
                                 Filters cases where case_date <= end_date
        user_id (str, optional): Specific provider user_id to filter results
                                When provided, generates single-provider report
        email_type (str, optional): Email template type for notifications:
                                   - "weekly": Automated weekly report template
                                   - "on_demand": Manual/ad-hoc report template
                                   Default: "on_demand"
    
    Returns:
        FileResponse: PDF file download with comprehensive metadata headers:
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
            - 404 Not Found: No cases found matching the specified criteria
            - 500 Internal Server Error: Report generation, S3 upload, or email errors
    
    Database Operations:
        1. Queries cases with case_status = 15 (pending payment status)
        2. Joins with user_profile for provider information including state
        3. Filters by active status (cases and users)
        4. Excludes system/test accounts from reporting
        5. Groups results by state, then by provider for organized reporting
        6. Calculates total payment amounts per provider
        7. Applies date and provider filtering as specified
    
    Report Content Structure:
        PDF Header:
        - All-Stars Surgical Assist branding
        - Report generation date in user's timezone
        - Professional formatting with consistent styling
        
        State Sections (one per page):
        - State name header
        - Projected payment date (upcoming Friday)
        - Tabular provider listing with columns:
            * Provider Name (properly capitalized, sorted alphabetically)
            * NPI (National Provider Identifier)
            * Total Payment Amount for that provider
        - State-specific financial totals
        
        Summary Section:
        - Total payment amount across all states
        - Total state count
        - Total provider count
        - Report generation metadata
    
    Payment Logic & Business Rules:
        - Only includes cases with case_status = 15 (ready for payment)
        - Excludes specific system accounts from payment calculations
        - Projected pay dates calculated as upcoming Friday
        - Payment amounts aggregated per provider from pay_amount field
        - Active cases and users only
        - States ordered alphabetically
        - Providers ordered alphabetically within each state
    
    AWS S3 Integration:
        - Automatic upload to configured S3 bucket
        - Metadata tagging with report details:
            * Report type, generation source
            * State count, provider count, total amount
            * Filter parameters applied
            * Timestamp and version information
        - S3 URL generation for cloud access
        - Error handling with fallback to local storage
    
    Email Distribution System:
        - Multi-recipient automated email sending
        - Template-based email formatting (weekly vs on-demand)
        - PDF attachment with secure delivery
        - Timezone-aware date formatting for recipients
        - Comprehensive delivery tracking and error reporting
        - Failed email logging without blocking report generation
    
    File Management:
        - Timestamped filename generation for uniqueness
        - Local storage in dedicated reports directory
        - Automatic cleanup of reports older than 7 days
        - File size optimization and compression
        - Secure temporary file handling
    
    Text Formatting & Presentation:
        - Proper name capitalization using capitalize_name_field utility
        - Professional PDF layout with consistent fonts and spacing
        - Timezone-aware date formatting for user context
        - Currency formatting for financial amounts
        - State-based organization for easy review
    
    Monitoring & Analytics:
        - Business metrics tracking for report generation operations
        - Prometheus monitoring via @track_business_operation decorator
        - Success/failure tracking for all operations
        - Performance metrics for generation time
        - Email delivery analytics and error tracking
        - S3 upload success monitoring
    
    Example Usage:
        GET /provider_payment_summary_report
        GET /provider_payment_summary_report?start_date=2024-01-01&end_date=2024-01-31
        GET /provider_payment_summary_report?user_id=PROV123&email_type=weekly
        GET /provider_payment_summary_report?start_date=2024-01-15
    
    Example Response Headers:
        Content-Type: application/pdf
        Content-Disposition: attachment; filename="provider_payment_summary_report_20240815_143022.pdf"
        Cache-Control: no-cache
        Content-Length: 125760
        X-S3-URL: https://bucket.s3.amazonaws.com/reports/provider_payment_summary_report_20240815_143022.pdf
        X-S3-Key: reports/provider_payment_summary_report_20240815_143022.pdf
        X-S3-Upload-Success: True
        X-Email-Sent: True
        X-Email-Count: 3
        X-Email-Total-Recipients: 5
    
    Report File Structure:
        provider_payment_summary_report_20240815_143022.pdf
        ├── Header: All-Stars Surgical Assist branding
        ├── State Section 1: Alabama
        │   ├── Projected Pay Date: August 16, 2024
        │   ├── Provider Table: Name | NPI | Total Amount
        │   │   ├── Dr. Jane Doe (1234567890) - $2,500.00
        │   │   └── Dr. John Smith (0987654321) - $3,750.00
        │   └── State Total: $6,250.00
        ├── State Section 2: California
        │   └── [Similar structure]
        └── Summary: Total Amount: $25,750.00 | 5 States | 15 Providers
    
    Note:
        - Report generation may take time for large datasets
        - S3 upload provides cloud backup and sharing capabilities
        - Email notifications enhance workflow automation
        - Timezone formatting ensures proper date display for users
        - File cleanup prevents storage bloat
        - System accounts are automatically excluded from payment reports
        - Projected payment dates follow business rule of upcoming Friday
        - Report security handled through access control and temporary file management
        - Professional formatting suitable for financial documentation and audit purposes
        - Each state creates a new page for easy state-by-state review
        - Provider sorting within states enables quick provider location
    """
    start_time = time.time()
    response_status = 200
    response_data = None
    error_message = None
    
    try:
        conn = get_db_connection()
        
        try:
            with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                # Build the main query to get provider summary data grouped by state
                sql = """
                    SELECT 
                        up.state,
                        up.first_name,
                        up.last_name,
                        up.user_npi,
                        SUM(c.pay_amount) as total_amount,
                        COUNT(c.case_id) as case_count
                    FROM cases c
                    INNER JOIN user_profile up ON c.user_id = up.user_id
                    WHERE c.case_status = 15
                    AND c.active = 1 
                    AND up.active = 1
                    AND c.user_id NOT IN ('04e884e8-4011-70e9-f3bd-d89fabd15c7b', '94883428-50c1-7049-9d3d-e095ca81f174', '94b80418-6091-701b-eac8-8b325f95a799')
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
                
                # Group by provider and order by state, then provider name
                sql += """
                    GROUP BY c.user_id, up.state, up.first_name, up.last_name, up.user_npi
                    ORDER BY up.state, up.last_name, up.first_name
                """
                
                cursor.execute(sql, params)
                providers = cursor.fetchall()
                
                if not providers:
                    response_status = 404
                    error_message = "No cases found matching the criteria"
                    raise HTTPException(
                        status_code=404, 
                        detail="No cases found matching the criteria"
                    )
                
                # Group providers by state
                states_data = {}
                for provider in providers:
                    state = provider['state'] or 'Unknown'
                    if state not in states_data:
                        states_data[state] = []
                    states_data[state].append(provider)
                
                # Generate PDF
                pdf = ProviderPaymentSummaryReportPDF(user_id=user_id)
                pdf.alias_nb_pages()
                pdf.add_page()
                
                total_amount = 0
                total_providers = 0
                
                # Add each state's section
                first_state = True
                for state_name in sorted(states_data.keys()):
                    state_providers = states_data[state_name]
                    state_total = pdf.add_state_section(
                        state_name, 
                        state_providers,
                        is_first_state=first_state
                    )
                    total_amount += state_total
                    total_providers += len(state_providers)
                    first_state = False
                
                # Add summary
                pdf.add_summary(total_amount, len(states_data), total_providers)
                
                # Create reports directory if it doesn't exist
                reports_dir = os.path.join(os.getcwd(), "reports")
                os.makedirs(reports_dir, exist_ok=True)
                
                # Clean up old reports before generating new one
                cleanup_old_reports(reports_dir, days_to_keep=7)
                
                # Save to reports directory
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"provider_payment_summary_report_{timestamp}.pdf"
                filepath = os.path.join(reports_dir, filename)
                
                pdf.output(filepath)
                
                # Prepare metadata for S3
                metadata = {
                    'report_type': 'provider_payment_summary',
                    'generated_by': 'surgicase_api',
                    'total_states': str(len(states_data)),
                    'total_providers': str(total_providers),
                    'total_amount': f"{total_amount:.2f}",
                    'start_date': start_date or 'all',
                    'end_date': end_date or 'all',
                    'user_filter': user_id or 'all'
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
                business_metrics.record_utility_operation("provider_summary_report", "success")
                
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
                        "total_states": len(states_data),
                        "total_providers": total_providers,
                        "total_amount": f"{total_amount:.2f}",
                        "report_type": "Provider Payment Summary Report"
                    }
                    
                    # Send emails with appropriate template type
                    email_result = send_provider_payment_summary_report_emails(
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
            
    except HTTPException as http_error:
        response_status = http_error.status_code
        error_message = str(http_error.detail)
        raise
    except Exception as e:
        # Record failed report generation
        response_status = 500
        error_message = str(e)
        business_metrics.record_utility_operation("provider_summary_report", "error")
        raise HTTPException(
            status_code=500,
            detail=f"Error generating summary report: {str(e)}"
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
            user_id=user_id,
            response_data=response_data,
            error_message=error_message
        )
