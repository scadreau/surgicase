# Created: 2025-07-23 13:19:34
# Last Modified: 2025-07-29 02:14:37
# Author: Scott Cadreau

# utils/metrics_report.py
import argparse
import sys
import os
from datetime import datetime, timedelta
import re

# Add the project root to the Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from core.database import get_db_connection, close_db_connection

def parse_timeframe(timeframe_str):
    """
    Parse timeframe string and return datetime offset from now
    Supported formats: 1min, 5min, 1hr, 3hr, 1day, etc.
    """
    pattern = r'^(\d+)(min|hr|day)s?$'
    match = re.match(pattern, timeframe_str.lower())
    
    if not match:
        raise ValueError(f"Invalid timeframe format: {timeframe_str}. Use format like: 1min, 5min, 1hr, 3hr, 1day")
    
    value = int(match.group(1))
    unit = match.group(2)
    
    if unit == 'min':
        return datetime.now() - timedelta(minutes=value)
    elif unit == 'hr':
        return datetime.now() - timedelta(hours=value)
    elif unit == 'day':
        return datetime.now() - timedelta(days=value)
    else:
        raise ValueError(f"Unsupported time unit: {unit}")

def get_success_metrics(conn, since_time):
    """Get metrics for successful requests (error_message is null)"""
    with conn.cursor() as cursor:
        cursor.execute("""
            SELECT 
                endpoint, 
                method, 
                COUNT(*) as queries, 
                MIN(execution_time_ms) as min_time, 
                MAX(execution_time_ms) as max_time, 
                AVG(execution_time_ms) as avg_time 
            FROM request_logs 
            WHERE error_message IS NULL 
            AND timestamp >= %s
            GROUP BY endpoint, method
            ORDER BY endpoint, method
        """, (since_time,))
        return cursor.fetchall()

def get_error_metrics(conn, since_time):
    """Get metrics for failed requests (error_message is not null)"""
    with conn.cursor() as cursor:
        cursor.execute("""
            SELECT 
                endpoint, 
                method, 
                COUNT(*) as error_count
            FROM request_logs 
            WHERE error_message IS NOT NULL 
            AND timestamp >= %s
            GROUP BY endpoint, method
            ORDER BY endpoint, method
        """, (since_time,))
        return cursor.fetchall()

def format_time(time_ms):
    """Format execution time in a readable format"""
    if time_ms is None:
        return "N/A"
    if time_ms < 1000:
        return f"{time_ms:.0f}ms"
    else:
        return f"{time_ms/1000:.2f}s"

def generate_report(timeframe):
    """Generate and display the metrics report"""
    try:
        since_time = parse_timeframe(timeframe)
    except ValueError as e:
        print(f"Error: {e}")
        return 1
    
    conn = None
    try:
        conn = get_db_connection()
        
        # Get success metrics
        success_metrics = get_success_metrics(conn, since_time)
        
        # Get error metrics
        error_metrics = get_error_metrics(conn, since_time)
        
        # Create a lookup for error counts
        error_lookup = {}
        for row in error_metrics:
            key = (row['endpoint'], row['method'])
            error_lookup[key] = row['error_count']
        
        # Display report
        print("=" * 80)
        print(f"METRICS REPORT - Last {timeframe}")
        print(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Period: {since_time.strftime('%Y-%m-%d %H:%M:%S')} to now")
        print("=" * 80)
        
        if not success_metrics and not error_metrics:
            print(f"No requests found in the last {timeframe}")
            return 0
        
        # Combine all endpoints
        all_endpoints = set()
        for row in success_metrics:
            all_endpoints.add((row['endpoint'], row['method']))
        for row in error_metrics:
            all_endpoints.add((row['endpoint'], row['method']))
        
        # Create success lookup
        success_lookup = {}
        for row in success_metrics:
            key = (row['endpoint'], row['method'])
            success_lookup[key] = row
        
        print(f"{'Endpoint':<40} {'Method':<8} {'Requests':<10} {'Min Time':<10} {'Max Time':<10} {'Avg Time':<10} {'Errors':<8}")
        print("-" * 106)
        
        for endpoint, method in sorted(all_endpoints):
            key = (endpoint, method)
            
            # Get success data
            if key in success_lookup:
                success_data = success_lookup[key]
                requests = success_data['queries']
                min_time = format_time(success_data['min_time'])
                max_time = format_time(success_data['max_time'])
                avg_time = format_time(success_data['avg_time'])
            else:
                requests = 0
                min_time = max_time = avg_time = "N/A"
            
            # Get error count
            error_count = error_lookup.get(key, 0)
            
            # Total requests including errors
            total_requests = requests + error_count
            
            print(f"{endpoint:<40} {method:<8} {total_requests:<10} {min_time:<10} {max_time:<10} {avg_time:<10} {error_count:<8}")
        
        # Summary statistics
        print("\n" + "=" * 80)
        print("SUMMARY")
        print("=" * 80)
        
        total_successful = sum(row['queries'] for row in success_metrics)
        total_errors = sum(row['error_count'] for row in error_metrics)
        total_requests = total_successful + total_errors
        
        if total_requests > 0:
            error_rate = (total_errors / total_requests) * 100
            print(f"Total Requests: {total_requests}")
            print(f"Successful: {total_successful}")
            print(f"Errors: {total_errors}")
            print(f"Error Rate: {error_rate:.2f}%")
            
            if success_metrics:
                all_times = []
                for row in success_metrics:
                    # Calculate total time for all requests in this endpoint/method
                    total_time = row['avg_time'] * row['queries']
                    all_times.extend([row['avg_time']] * row['queries'])  # Approximate
                
                if all_times:
                    overall_avg = sum(all_times) / len(all_times)
                    print(f"Overall Average Response Time: {format_time(overall_avg)}")
        else:
            print("No requests found in the specified timeframe.")
        
    except Exception as e:
        print(f"Database error: {e}")
        return 1
    finally:
        if conn:
            close_db_connection(conn)
    
    return 0

def main():
    """Main function to handle command line arguments and run the report"""
    parser = argparse.ArgumentParser(
        description="Generate metrics report from request logs",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python utils/metrics_report.py --timeframe=1min
  python utils/metrics_report.py --timeframe=5min
  python utils/metrics_report.py --timeframe=1hr
  python utils/metrics_report.py --timeframe=3hr
  python utils/metrics_report.py --timeframe=1day
        """
    )
    
    parser.add_argument(
        '--timeframe',
        required=True,
        help='Timeframe for the report (e.g., 1min, 5min, 1hr, 3hr, 1day)'
    )
    
    args = parser.parse_args()
    
    return generate_report(args.timeframe)

if __name__ == "__main__":
    sys.exit(main()) 