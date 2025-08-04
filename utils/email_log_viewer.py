# Created: 2025-08-03
# Last Modified: 2025-08-04 10:17:40
# Author: Scott Cadreau

"""
Utility functions to view and query email logs
"""

import sys
import os
from typing import List, Dict, Optional, Any
from datetime import datetime, timedelta

# Add the project root to the Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(project_root)

from core.database import get_db_connection, close_db_connection
import pymysql.cursors

def get_recent_emails(hours: int = 24, limit: int = 50) -> List[Dict[str, Any]]:
    """
    Get recent emails from the email log
    
    Args:
        hours: Number of hours back to look (default: 24)
        limit: Maximum number of records to return (default: 50)
        
    Returns:
        List of email log records
    """
    conn = None
    try:
        conn = get_db_connection()
        
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            sql = """
                SELECT 
                    id, message_id, to_address, from_address, subject,
                    email_type, report_type, status, attachments_count,
                    sent_at, error_message
                FROM email_log 
                WHERE sent_at >= DATE_SUB(NOW(), INTERVAL %s HOUR)
                ORDER BY sent_at DESC
                LIMIT %s
            """
            cursor.execute(sql, (hours, limit))
            return cursor.fetchall()
            
    except Exception as e:
        print(f"Error fetching recent emails: {e}")
        return []
    finally:
        if conn:
            close_db_connection(conn)

def get_emails_by_type(email_type: str, hours: int = 168, limit: int = 100) -> List[Dict[str, Any]]:
    """
    Get emails by type from the email log
    
    Args:
        email_type: Type of email to filter by
        hours: Number of hours back to look (default: 168 = 1 week)
        limit: Maximum number of records to return (default: 100)
        
    Returns:
        List of email log records
    """
    conn = None
    try:
        conn = get_db_connection()
        
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            sql = """
                SELECT 
                    id, message_id, to_address, from_address, subject,
                    email_type, report_type, status, attachments_count,
                    sent_at, error_message
                FROM email_log 
                WHERE email_type = %s 
                AND sent_at >= DATE_SUB(NOW(), INTERVAL %s HOUR)
                ORDER BY sent_at DESC
                LIMIT %s
            """
            cursor.execute(sql, (email_type, hours, limit))
            return cursor.fetchall()
            
    except Exception as e:
        print(f"Error fetching emails by type: {e}")
        return []
    finally:
        if conn:
            close_db_connection(conn)

def get_failed_emails(hours: int = 24, limit: int = 50) -> List[Dict[str, Any]]:
    """
    Get failed emails from the email log
    
    Args:
        hours: Number of hours back to look (default: 24)
        limit: Maximum number of records to return (default: 50)
        
    Returns:
        List of failed email log records
    """
    conn = None
    try:
        conn = get_db_connection()
        
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            sql = """
                SELECT 
                    id, message_id, to_address, from_address, subject,
                    email_type, report_type, status, attachments_count,
                    sent_at, error_message
                FROM email_log 
                WHERE status = 'failed'
                AND sent_at >= DATE_SUB(NOW(), INTERVAL %s HOUR)
                ORDER BY sent_at DESC
                LIMIT %s
            """
            cursor.execute(sql, (hours, limit))
            return cursor.fetchall()
            
    except Exception as e:
        print(f"Error fetching failed emails: {e}")
        return []
    finally:
        if conn:
            close_db_connection(conn)

def get_email_stats(hours: int = 24) -> Dict[str, Any]:
    """
    Get email statistics for the specified time period
    
    Args:
        hours: Number of hours back to look (default: 24)
        
    Returns:
        Dictionary with email statistics
    """
    conn = None
    try:
        conn = get_db_connection()
        
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            # Total emails
            cursor.execute("""
                SELECT COUNT(*) as total_emails
                FROM email_log 
                WHERE sent_at >= DATE_SUB(NOW(), INTERVAL %s HOUR)
            """, (hours,))
            total_result = cursor.fetchone()
            
            # Emails by status
            cursor.execute("""
                SELECT status, COUNT(*) as count
                FROM email_log 
                WHERE sent_at >= DATE_SUB(NOW(), INTERVAL %s HOUR)
                GROUP BY status
            """, (hours,))
            status_results = cursor.fetchall()
            
            # Emails by type
            cursor.execute("""
                SELECT email_type, COUNT(*) as count
                FROM email_log 
                WHERE sent_at >= DATE_SUB(NOW(), INTERVAL %s HOUR)
                GROUP BY email_type
            """, (hours,))
            type_results = cursor.fetchall()
            
            return {
                "total_emails": total_result['total_emails'] if total_result else 0,
                "by_status": {row['status']: row['count'] for row in status_results},
                "by_type": {row['email_type']: row['count'] for row in type_results},
                "time_period_hours": hours
            }
            
    except Exception as e:
        print(f"Error fetching email stats: {e}")
        return {}
    finally:
        if conn:
            close_db_connection(conn)

def print_email_summary(emails: List[Dict[str, Any]], title: str = "Email Summary"):
    """
    Print a formatted summary of emails
    
    Args:
        emails: List of email records
        title: Title for the summary
    """
    print(f"\n{title}")
    print("=" * len(title))
    
    if not emails:
        print("No emails found.")
        return
    
    print(f"Found {len(emails)} email(s):\n")
    
    for email in emails:
        status_emoji = "✅" if email['status'] == 'sent' else "❌"
        print(f"{status_emoji} {email['sent_at']} | {email['status'].upper()}")
        print(f"   To: {email['to_address']}")
        print(f"   Subject: {email['subject']}")
        print(f"   Type: {email['email_type'] or 'N/A'}")
        if email['attachments_count'] > 0:
            print(f"   Attachments: {email['attachments_count']}")
        if email['error_message']:
            print(f"   Error: {email['error_message']}")
        print()

def main():
    """
    Main function for command-line usage
    """
    import argparse
    
    parser = argparse.ArgumentParser(description='View SurgiCase email logs')
    parser.add_argument('--recent', type=int, default=24, 
                       help='Show recent emails (hours back, default: 24)')
    parser.add_argument('--type', type=str, 
                       help='Filter by email type')
    parser.add_argument('--failed', action='store_true', 
                       help='Show only failed emails')
    parser.add_argument('--stats', action='store_true', 
                       help='Show email statistics')
    parser.add_argument('--limit', type=int, default=50, 
                       help='Maximum number of emails to show (default: 50)')
    
    args = parser.parse_args()
    
    if args.stats:
        stats = get_email_stats(args.recent)
        print(f"\nEmail Statistics (last {args.recent} hours)")
        print("=" * 40)
        print(f"Total emails: {stats.get('total_emails', 0)}")
        
        if stats.get('by_status'):
            print("\nBy Status:")
            for status, count in stats['by_status'].items():
                print(f"  {status}: {count}")
        
        if stats.get('by_type'):
            print("\nBy Type:")
            for email_type, count in stats['by_type'].items():
                type_display = email_type or 'Unknown'
                print(f"  {type_display}: {count}")
        
        return
    
    if args.failed:
        emails = get_failed_emails(args.recent, args.limit)
        print_email_summary(emails, f"Failed Emails (last {args.recent} hours)")
    elif args.type:
        emails = get_emails_by_type(args.type, args.recent, args.limit)
        print_email_summary(emails, f"Emails of type '{args.type}' (last {args.recent} hours)")
    else:
        emails = get_recent_emails(args.recent, args.limit)
        print_email_summary(emails, f"Recent Emails (last {args.recent} hours)")

if __name__ == "__main__":
    main()