# Created: 2025-10-21
# Last Modified: 2025-10-21 19:09:33
# Author: Scott Cadreau

# utils/export_npi_to_csv.py
"""
Export NPI data tables from MySQL to CSV files for migration to PostgreSQL.

This script exports the three core NPI data tables:
- npi_data_0: Unknown/Other entity types
- npi_data_1: Individual providers (doctors, nurses, etc.)
- npi_data_2: Organizations (hospitals, clinics, etc.)

The exported CSV files can then be imported into a PostgreSQL database.
"""

import os
import sys
import csv
import time
from datetime import datetime
import pymysql.cursors

# Add the project root to the Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from core.database import get_db_connection, close_db_connection

# Output directory
OUTPUT_DIR = "/home/scadreau"

# Tables to export
TABLES = ['npi_data_0', 'npi_data_1', 'npi_data_2']

def export_table_to_csv(table_name, output_dir):
    """
    Export a single table to CSV file using direct MySQL cursor
    
    Args:
        table_name: Name of the table to export
        output_dir: Directory where CSV file will be saved
    
    Returns:
        dict: Statistics about the export (rows, file size, duration)
    """
    start_time = time.time()
    output_file = os.path.join(output_dir, f"{table_name}.csv")
    
    print(f"\nExporting {table_name}...")
    print(f"  Output: {output_file}")
    
    # Connect to database
    conn = get_db_connection()
    
    try:
        # Use SSCursor to stream results without loading everything into memory
        with conn.cursor(pymysql.cursors.SSCursor) as cursor:
            print(f"  Executing query...")
            query = f"SELECT * FROM {table_name}"
            cursor.execute(query)
            
            # Get column names from cursor description
            columns = [desc[0] for desc in cursor.description]
            
            print(f"  Writing data to CSV (streaming)...")
            row_count = 0
            
            # Open CSV file and write in chunks
            with open(output_file, 'w', encoding='utf-8', newline='') as csvfile:
                writer = csv.writer(csvfile, quoting=csv.QUOTE_MINIMAL)
                
                # Write header
                writer.writerow(columns)
                
                # Write data rows in chunks
                chunk_size = 10000
                chunk = []
                
                for row in cursor:
                    chunk.append(row)
                    row_count += 1
                    
                    if len(chunk) >= chunk_size:
                        writer.writerows(chunk)
                        chunk = []
                        
                        # Progress indicator
                        if row_count % 100000 == 0:
                            print(f"    Progress: {row_count:,} rows written...")
                
                # Write remaining rows
                if chunk:
                    writer.writerows(chunk)
        
        # Get file size
        file_size = os.path.getsize(output_file)
        file_size_mb = file_size / (1024 * 1024)
        
        duration = time.time() - start_time
        
        print(f"  ✓ Export completed: {row_count:,} rows, {file_size_mb:.2f} MB, {duration:.2f} seconds")
        
        return {
            "table_name": table_name,
            "rows": row_count,
            "file_size_mb": file_size_mb,
            "duration_seconds": duration,
            "output_file": output_file,
            "status": "success"
        }
        
    except Exception as e:
        print(f"  ✗ Error exporting {table_name}: {e}")
        return {
            "table_name": table_name,
            "status": "error",
            "error": str(e)
        }
        
    finally:
        close_db_connection(conn)

def main():
    """Main execution function"""
    print("=" * 80)
    print("NPI Data Export to CSV")
    print("=" * 80)
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Output directory: {OUTPUT_DIR}")
    print(f"Tables to export: {', '.join(TABLES)}")
    
    overall_start = time.time()
    results = []
    
    # Export each table
    for table_name in TABLES:
        result = export_table_to_csv(table_name, OUTPUT_DIR)
        results.append(result)
    
    # Print summary
    print("\n" + "=" * 80)
    print("EXPORT SUMMARY")
    print("=" * 80)
    
    total_rows = 0
    total_size = 0
    success_count = 0
    
    for result in results:
        if result["status"] == "success":
            success_count += 1
            total_rows += result["rows"]
            total_size += result["file_size_mb"]
            print(f"✓ {result['table_name']}: {result['rows']:,} rows, {result['file_size_mb']:.2f} MB")
        else:
            print(f"✗ {result['table_name']}: ERROR - {result['error']}")
    
    overall_duration = time.time() - overall_start
    
    print(f"\nTotal exported: {total_rows:,} rows")
    print(f"Total file size: {total_size:.2f} MB")
    print(f"Success rate: {success_count}/{len(TABLES)} tables")
    print(f"Total duration: {overall_duration:.2f} seconds ({overall_duration/60:.1f} minutes)")
    print(f"\nCompleted: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)
    
    # Return results for potential programmatic use
    return results

if __name__ == "__main__":
    main()

