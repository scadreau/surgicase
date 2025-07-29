# Created: 2025-07-21
# Last Modified: 2025-07-29 02:14:14
# Author: Scott Cadreau

# utils/npi_initial_load.py
import os
import sys
import pandas as pd
import pymysql.cursors
from datetime import datetime

# Add the project root to the Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from core.database import get_db_connection, close_db_connection

# Constants
DOWNLOAD_DIR = "npi_data"
INITIAL_DATA_FILE = "npidata_pfile_20050523-20250713.csv"
NEW_HEADER_FILE = os.path.join(DOWNLOAD_DIR, 'new_header.csv')

def load_initial_npi_data():
    """Load the initial NPI data file into the database tables."""
    
    # Check if files exist
    csv_path = os.path.join(DOWNLOAD_DIR, INITIAL_DATA_FILE)
    if not os.path.exists(csv_path):
        print(f"Error: Initial data file not found: {csv_path}")
        return
    
    if not os.path.exists(NEW_HEADER_FILE):
        print(f"Error: Header file not found: {NEW_HEADER_FILE}")
        return
    
    print(f"Starting initial load of: {INITIAL_DATA_FILE}")
    
    # Read the new header
    with open(NEW_HEADER_FILE, 'r') as header_file:
        new_header = header_file.readline().strip().split(',')

    # Ensure column names are correctly formatted
    new_header = [col.strip().strip('"') for col in new_header]

    # Load the CSV data into a DataFrame with the new header
    print("Loading CSV file... (this may take a few minutes for large files)")
    df = pd.read_csv(csv_path, header=None, low_memory=False, chunksize=10000)
    
    # Record execution timestamp
    execution_ts = datetime.now()
    start_time = datetime.now()
    
    # Connect to the database
    conn = get_db_connection()
    total_processed = 0
    entity_counts = {
        'total_0_rows': 0,
        'total_1_rows': 0,
        'total_2_rows': 0
    }

    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            # Retrieve column names from one of the target tables
            cursor.execute("SHOW COLUMNS FROM npi_data_0")
            db_columns = [row['Field'] for row in cursor.fetchall()]

            print("Processing data in chunks...")
            
            # Process data in chunks to handle large file
            for chunk_num, chunk in enumerate(df):
                # Set column names for this chunk
                chunk.columns = new_header
                
                # Filter the DataFrame to include only the columns present in the database
                df_filtered = chunk[[col for col in db_columns if col in chunk.columns]]

                # Replace NaN values with None for MySQL compatibility
                df_filtered = df_filtered.where(pd.notnull(df_filtered), None)
                
                # Additional NaN handling - convert any remaining NaN values
                for col in df_filtered.columns:
                    df_filtered[col] = df_filtered[col].apply(lambda x: None if pd.isna(x) or (isinstance(x, float) and pd.isna(x)) else x)
                
                # Prepare batch data for each table
                batch_data = {
                    'npi_data_0': [],
                    'npi_data_1': [],
                    'npi_data_2': []
                }
                
                batch_size = 1000
                chunk_processed = 0

                # Iterate over DataFrame rows and prepare batches
                for index, row in df_filtered.iterrows():
                    try:
                        entity_type_code = int(row.get('entity_type_code')) if row.get('entity_type_code') is not None else None
                    except (ValueError, TypeError):
                        entity_type_code = None  # Handle non-integer or missing values
                    
                    # Determine the target table and update counters
                    if entity_type_code == 0 or entity_type_code is None:
                        target_table = 'npi_data_0'
                        entity_counts['total_0_rows'] += 1
                    elif entity_type_code == 1:
                        target_table = 'npi_data_1'
                        entity_counts['total_1_rows'] += 1
                    elif entity_type_code == 2:
                        target_table = 'npi_data_2'
                        entity_counts['total_2_rows'] += 1
                    else:
                        continue  # Skip if entity_type_code is not 0, 1, or 2

                    # Get values in the same order as filtered columns
                    filtered_columns = list(df_filtered.columns)
                    values = []
                    for col in filtered_columns:
                        val = row[col]
                        # Comprehensive NaN checking
                        if pd.isna(val) or (isinstance(val, float) and pd.isna(val)) or str(val).lower() == 'nan':
                            values.append(None)
                        else:
                            values.append(val)
                    batch_data[target_table].append(tuple(values))
                    
                    chunk_processed += 1
                    total_processed += 1
                    
                    # Progress update every 5000 rows
                    if total_processed % 5000 == 0:
                        elapsed_time = datetime.now() - start_time
                        elapsed_seconds = elapsed_time.total_seconds()
                        rows_per_second = total_processed / elapsed_seconds if elapsed_seconds > 0 else 0
                        
                        # Format elapsed time
                        hours, remainder = divmod(int(elapsed_seconds), 3600)
                        minutes, seconds = divmod(remainder, 60)
                        elapsed_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
                        
                        # Estimate remaining time (assuming 10M total rows)
                        estimated_total_rows = 10000000
                        remaining_rows = estimated_total_rows - total_processed
                        estimated_remaining_seconds = remaining_rows / rows_per_second if rows_per_second > 0 else 0
                        
                        if estimated_remaining_seconds > 0:
                            rem_hours, rem_remainder = divmod(int(estimated_remaining_seconds), 3600)
                            rem_minutes, rem_seconds = divmod(rem_remainder, 60)
                            remaining_str = f"{rem_hours:02d}:{rem_minutes:02d}:{rem_seconds:02d}"
                            
                            print(f"Processed {total_processed:,} rows (Type 0: {entity_counts['total_0_rows']:,}, Type 1: {entity_counts['total_1_rows']:,}, Type 2: {entity_counts['total_2_rows']:,}) | Elapsed: {elapsed_str} | Est. Remaining: {remaining_str} | Rate: {rows_per_second:.1f} rows/sec")
                        else:
                            print(f"Processed {total_processed:,} rows (Type 0: {entity_counts['total_0_rows']:,}, Type 1: {entity_counts['total_1_rows']:,}, Type 2: {entity_counts['total_2_rows']:,}) | Elapsed: {elapsed_str} | Rate: {rows_per_second:.1f} rows/sec")
                    
                    # Process batch when it reaches batch_size
                    if chunk_processed % batch_size == 0:
                        # Insert batches for each table
                        for table_name, data in batch_data.items():
                            if data:  # Only insert if there's data
                                columns = ', '.join([f'`{col.strip()}`' for col in filtered_columns])
                                placeholders = ', '.join(['%s'] * len(filtered_columns))
                                sql = f"INSERT INTO {table_name} ({columns}) VALUES ({placeholders})"
                                
                                try:
                                    cursor.executemany(sql, data)
                                except Exception as e:
                                    print(f"Error inserting batch into {table_name}: {e}")
                                    # Try inserting one by one to identify problematic rows
                                    for i, row_data in enumerate(data):
                                        try:
                                            cursor.execute(sql, row_data)
                                        except Exception as row_error:
                                            print(f"Error in row {i}: {row_error}")
                                            break
                                    return
                        
                        # Clear batch data
                        for table_name in batch_data:
                            batch_data[table_name] = []

                # Process any remaining data in the chunk
                for table_name, data in batch_data.items():
                    if data:  # Only insert if there's data
                        columns = ', '.join([f'`{col.strip()}`' for col in filtered_columns])
                        placeholders = ', '.join(['%s'] * len(filtered_columns))
                        sql = f"INSERT INTO {table_name} ({columns}) VALUES ({placeholders})"
                        
                        try:
                            cursor.executemany(sql, data)
                        except Exception as e:
                            print(f"Error inserting final batch into {table_name}: {e}")
                            return

                # Progress update every 10 chunks
                if (chunk_num + 1) % 10 == 0:
                    print(f"Processed {chunk_num + 1} chunks, total rows: {total_processed}")

            # Insert log entry
            log_sql = """
                INSERT INTO npi_update_log 
                (execution_ts, filename_processed, total_rows, total_0_rows, total_1_rows, total_2_rows) 
                VALUES (%s, %s, %s, %s, %s, %s)
            """
            cursor.execute(log_sql, (
                execution_ts,
                INITIAL_DATA_FILE,
                total_processed,
                entity_counts['total_0_rows'],
                entity_counts['total_1_rows'],
                entity_counts['total_2_rows']
            ))

            # Commit the transaction
            conn.commit()
            
            # Print summary
            print(f"Initial load completed:")
            print(f"  Total rows processed: {total_processed}")
            print(f"  Entity type 0 inserted: {entity_counts['total_0_rows']}")
            print(f"  Entity type 1 inserted: {entity_counts['total_1_rows']}")
            print(f"  Entity type 2 inserted: {entity_counts['total_2_rows']}")

    finally:
        # Close the database connection
        close_db_connection(conn)

if __name__ == "__main__":
    load_initial_npi_data() 