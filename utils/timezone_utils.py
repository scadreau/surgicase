# Created: 2025-07-31 01:40:21
# Last Modified: 2025-07-31 02:02:25
# Author: Scott Cadreau

# Timezone utility functions for converting UTC dates to user timezones
# 
# Database Requirements:
# - user_profile.timezone field should contain IANA timezone identifiers
# - Examples: 'America/New_York', 'America/Chicago', 'America/Los_Angeles', 'Europe/London'
# - Field can be NULL or empty (defaults to 'America/New_York')

import pytz
from datetime import datetime
from typing import Optional
import pymysql.cursors
from core.database import get_db_connection, close_db_connection
import logging

logger = logging.getLogger(__name__)

def get_user_timezone(user_id: Optional[str] = None, email_address: Optional[str] = None) -> str:
    """
    Get user's timezone from user_profile table
    
    Args:
        user_id: User ID to look up timezone for
        email_address: Email address to look up timezone for (alternative to user_id)
        
    Returns:
        User's timezone string in IANA format (defaults to 'America/New_York' if not found or empty)
        Examples: 'America/New_York', 'America/Chicago', 'America/Los_Angeles', 'Europe/London'
    """
    if not user_id and not email_address:
        logger.warning("No user_id or email_address provided, defaulting to America/New_York")
        return 'America/New_York'
    
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            if user_id:
                cursor.execute(
                    "SELECT timezone FROM user_profile WHERE user_id = %s AND active = 1",
                    (user_id,)
                )
            else:
                cursor.execute(
                    "SELECT timezone FROM user_profile WHERE user_email = %s AND active = 1",
                    (email_address,)
                )
            
            result = cursor.fetchone()
            if result and result.get('timezone'):
                timezone = result['timezone'].strip()
                if timezone:
                    return timezone
            
            # Default to America/New_York if timezone is null, empty, or blank
            logger.info(f"No timezone found for user, defaulting to America/New_York")
            return 'America/New_York'
            
    except Exception as e:
        logger.error(f"Error fetching user timezone: {str(e)}")
        return 'America/New_York'
    finally:
        if conn:
            close_db_connection(conn)

def convert_utc_to_user_timezone(utc_datetime: datetime, user_timezone: str) -> datetime:
    """
    Convert UTC datetime to user's timezone
    
    Args:
        utc_datetime: UTC datetime object
        user_timezone: User's timezone string in IANA format (e.g., 'America/New_York', 'America/Los_Angeles')
        
    Returns:
        Datetime object converted to user's timezone
    """
    try:
        # Ensure the UTC datetime is timezone-aware
        if utc_datetime.tzinfo is None:
            utc_datetime = pytz.utc.localize(utc_datetime)
        
        # Get user's timezone
        user_tz = pytz.timezone(user_timezone)
        
        # Convert to user's timezone
        user_datetime = utc_datetime.astimezone(user_tz)
        return user_datetime
        
    except Exception as e:
        logger.error(f"Error converting timezone from UTC to {user_timezone}: {str(e)}")
        # Fallback to America/New_York if conversion fails
        fallback_tz = pytz.timezone('America/New_York')
        if utc_datetime.tzinfo is None:
            utc_datetime = pytz.utc.localize(utc_datetime)
        return utc_datetime.astimezone(fallback_tz)

def format_datetime_for_user(utc_datetime: datetime, user_id: Optional[str] = None, 
                           email_address: Optional[str] = None, 
                           format_string: str = '%B %d, %Y') -> str:
    """
    Format a UTC datetime for display to a user in their timezone
    
    Args:
        utc_datetime: UTC datetime object
        user_id: User ID to look up timezone for
        email_address: Email address to look up timezone for (alternative to user_id)
        format_string: Python datetime format string
        
    Returns:
        Formatted datetime string in user's timezone
    """
    try:
        user_timezone = get_user_timezone(user_id, email_address)
        user_datetime = convert_utc_to_user_timezone(utc_datetime, user_timezone)
        return user_datetime.strftime(format_string)
        
    except Exception as e:
        logger.error(f"Error formatting datetime for user: {str(e)}")
        # Fallback to UTC formatting
        return utc_datetime.strftime(format_string)

def format_datetime_for_user_with_timezone(utc_datetime: datetime, user_id: Optional[str] = None,
                                         email_address: Optional[str] = None,
                                         format_string: str = '%B %d, %Y at %I:%M %p %Z') -> str:
    """
    Format a UTC datetime for display to a user in their timezone, including timezone name
    
    Args:
        utc_datetime: UTC datetime object
        user_id: User ID to look up timezone for
        email_address: Email address to look up timezone for (alternative to user_id)
        format_string: Python datetime format string (should include %Z for timezone)
        
    Returns:
        Formatted datetime string in user's timezone with timezone abbreviation
    """
    try:
        user_timezone = get_user_timezone(user_id, email_address)
        user_datetime = convert_utc_to_user_timezone(utc_datetime, user_timezone)
        return user_datetime.strftime(format_string)
        
    except Exception as e:
        logger.error(f"Error formatting datetime with timezone for user: {str(e)}")
        # Fallback to UTC formatting
        if utc_datetime.tzinfo is None:
            utc_datetime = pytz.utc.localize(utc_datetime)
        return utc_datetime.strftime(format_string)

def get_user_timezone_for_email_recipients(report_name: str) -> dict:
    """
    Get timezone information for all email recipients of a report
    
    Args:
        report_name: Name of the report (e.g., 'provider_payment_report')
        
    Returns:
        Dictionary mapping email addresses to timezone strings
    """
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            # Get email recipients and their timezones
            sql = """
                SELECT rel.email_address, up.timezone
                FROM report_email_list rel
                LEFT JOIN user_profile up ON rel.email_address = up.user_email AND up.active = 1
                WHERE rel.report_name = %s
            """
            cursor.execute(sql, (report_name,))
            results = cursor.fetchall()
            
            # Build timezone mapping
            timezone_map = {}
            for row in results:
                email = row['email_address']
                timezone = row.get('timezone')
                if timezone and timezone.strip():
                    timezone_map[email] = timezone.strip()
                else:
                    timezone_map[email] = 'America/New_York'  # Default to Eastern Time
                    
            return timezone_map
            
    except Exception as e:
        logger.error(f"Error fetching recipient timezones for {report_name}: {str(e)}")
        return {}
    finally:
        if conn:
            close_db_connection(conn)

def test_timezone_conversion(user_id: Optional[str] = None, email_address: Optional[str] = None) -> dict:
    """
    Test function to demonstrate timezone conversion functionality
    
    Args:
        user_id: User ID to test timezone conversion for
        email_address: Email address to test timezone conversion for
        
    Returns:
        Dictionary with test results showing UTC time and user's local time
    """
    try:
        # Get current UTC time
        utc_now = datetime.utcnow()
        
        # Get user's timezone
        user_timezone = get_user_timezone(user_id, email_address)
        
        # Format times
        utc_formatted = utc_now.strftime('%Y-%m-%d %H:%M:%S UTC')
        user_formatted = format_datetime_for_user(utc_now, user_id, email_address, '%Y-%m-%d %I:%M:%S %p %Z')
        
        return {
            "success": True,
            "user_id": user_id,
            "email_address": email_address,
            "user_timezone": user_timezone,
            "utc_time": utc_formatted,
            "user_local_time": user_formatted,
            "message": f"Time conversion successful from UTC to {user_timezone}"
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "message": "Time conversion failed"
        }