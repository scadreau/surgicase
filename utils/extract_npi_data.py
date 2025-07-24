# Created: 2025-07-21
# Last Modified: 2025-07-24 00:27:43

"""
NPI Data Extraction and Processing Script

This comprehensive script handles the complete workflow for National Provider Identifier (NPI) 
data management in the SurgiCase system. It performs the following key operations:

1. DOWNLOAD: Automatically downloads the most recent weekly NPI file from the CMS website
   - Fetches from https://download.cms.gov/nppes/NPI_Files.html
   - Identifies and downloads the latest weekly incremental file
   - Extracts the ZIP archive to the local npi_data directory

2. DATA PROCESSING: Processes the downloaded CSV file and distributes records by entity type
   - npi_data_0: Unknown/Other entity types (entity_type_code = 0 or NULL)
   - npi_data_1: Individual providers (entity_type_code = 1) - doctors, nurses, etc.
   - npi_data_2: Organizations (entity_type_code = 2) - hospitals, clinics, etc.
   - Uses optimized batch processing (10,000 records per batch) for performance
   - Handles data validation, NaN value conversion, and error recovery

3. SEARCH TABLE CREATION: Creates optimized A-Z search tables for fast lookups
   - Surgeon tables: search_surgeon_a through search_surgeon_z (from npi_data_1)
   - Facility tables: search_facility_a through search_facility_z (from npi_data_2)
   - Uses multi-threading for parallel table creation to minimize execution time
   - Adds database indexes for optimal search performance

4. LOGGING & MONITORING: Comprehensive logging for operational monitoring
   - Main processing logged to npi_update_log table
   - Search table creation logged to npi_search_table_log table
   - Real-time console output for progress tracking
   - Detailed error handling and recovery mechanisms

USAGE:
    python utils/extract_npi_data.py

REQUIREMENTS:
    - npi_data/new_header.csv file must exist (column mapping)
    - Database tables: npi_data_0, npi_data_1, npi_data_2, npi_update_log, npi_search_table_log
    - Internet connectivity to download from CMS
    - Sufficient database permissions for table creation and data insertion

PERFORMANCE:
    - Typical weekly files: 50-100MB, ~50,000 records, 2-5 minutes execution
    - Search table creation: 52 tables (26 surgeon + 26 facility), parallel processing
    - Memory usage: Moderate (DataFrame processing in batches)
    - Database load: Optimized with batch inserts and transaction management

This script is designed to be run on a weekly schedule to keep NPI data current
for the surgeon and facility search functionality in the SurgiCase API.
"""

import os
import sys
import requests
from bs4 import BeautifulSoup
from zipfile import ZipFile
from io import BytesIO
import pandas as pd
import pymysql.cursors
from datetime import datetime
import threading
import time
import string

# Add the project root to the Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from core.database import get_db_connection, close_db_connection

# Constants
URL = "https://download.cms.gov/nppes/NPI_Files.html"
DOWNLOAD_DIR = "../npi_data"

# Ensure the download directory exists
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

def download_and_extract_npi_file():
    """Download the most recent NPI weekly file and extract it"""
    print("Downloading NPI data file...")
    
    # Fetch the webpage
    response = requests.get(URL)
    response.raise_for_status()

    # Parse the HTML content
    soup = BeautifulSoup(response.content, 'html.parser')

    # Find all links in the Weekly Incremental NPI Files Version 2 (V.2) section
    weekly_links = []
    for link in soup.find_all('a', href=True):
        href = link['href']
        if 'weekly' in href.lower() and href.endswith('.zip'):
            weekly_links.append(href)

    # Sort links to find the most recent one
    weekly_links.sort(reverse=True)
    most_recent_link = weekly_links[0] if weekly_links else None

    if not most_recent_link:
        raise Exception("No weekly files found.")

    # Correct the URL construction logic
    if not most_recent_link.startswith('http'):
        most_recent_link = most_recent_link.lstrip('.')
        file_url = f'https://download.cms.gov/nppes{most_recent_link}'
    else:
        file_url = most_recent_link

    zip_response = requests.get(file_url)
    zip_response.raise_for_status()

    # Unzip the file
    with ZipFile(BytesIO(zip_response.content)) as thezip:
        thezip.extractall(DOWNLOAD_DIR)

    print(f"Downloaded and extracted: {file_url}")
    
    # Return the extracted CSV filename
    extracted_files = os.listdir(DOWNLOAD_DIR)
    csv_file = next((f for f in extracted_files if f.startswith('npidata_pfile') and f.endswith('.csv') and '_fileheader' not in f), None)
    
    if not csv_file:
        raise Exception("No CSV file found in extracted archive.")
    
    return csv_file

def process_npi_data_file(csv_file):
    """Process the NPI CSV file and update the main npi_data tables"""
    print(f"Processing NPI data file: {csv_file}")
    
    csv_path = os.path.join(DOWNLOAD_DIR, csv_file)
    
    # Path to the new header file
    NEW_HEADER_FILE = os.path.join(DOWNLOAD_DIR, 'new_header.txt')
    
    # Read the new header
    with open(NEW_HEADER_FILE, 'r') as header_file:
        new_header = header_file.readline().strip().split(',')

    # Ensure column names are correctly formatted
    new_header = [col.strip().strip('"') for col in new_header]

    # Load the CSV data into a DataFrame with the new header
    df = pd.read_csv(csv_path, header=None, low_memory=False)
    df.columns = new_header

    # Record execution timestamp
    execution_ts = datetime.now()
    
    # Connect to the database
    conn = get_db_connection()

    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            # Retrieve column names from one of the target tables
            cursor.execute("SHOW COLUMNS FROM npi_data_0")
            db_columns = [row['Field'] for row in cursor.fetchall()]

            # Filter the DataFrame to include only the columns present in the database
            df_filtered = df[[col for col in db_columns if col in df.columns]]

            # Replace NaN values with None for MySQL compatibility
            df_filtered = df_filtered.where(pd.notnull(df_filtered), None)
            
            # Prepare batch data for each table and counters
            batch_data = {
                'npi_data_0': [],
                'npi_data_1': [],
                'npi_data_2': []
            }
            
            # Counters for each entity type
            entity_counts = {
                'total_0_rows': 0,
                'total_1_rows': 0,
                'total_2_rows': 0
            }
            
            batch_size = 10000  # Increased from 1000 to leverage available memory and RDS burst capacity
            processed_count = 0

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
                values = [row[col] for col in filtered_columns]
                batch_data[target_table].append(tuple(values))
                
                processed_count += 1
                
                # Process batch when it reaches batch_size or at the end
                if processed_count % batch_size == 0 or index == len(df_filtered) - 1:
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
                                break
                    
                    # Clear batch data
                    for table_name in batch_data:
                        batch_data[table_name] = []

            # Insert log entry for main NPI data processing
            log_sql = """
                INSERT INTO npi_update_log 
                (execution_ts, filename_processed, total_rows, total_0_rows, total_1_rows, total_2_rows) 
                VALUES (%s, %s, %s, %s, %s, %s)
            """
            cursor.execute(log_sql, (
                execution_ts,
                csv_file,
                processed_count,
                entity_counts['total_0_rows'],
                entity_counts['total_1_rows'],
                entity_counts['total_2_rows']
            ))

            # Commit the main data processing transaction
            conn.commit()
            
            # Print summary of main processing
            print(f"Main NPI data processing completed:")
            print(f"  Total rows processed: {processed_count}")
            print(f"  Entity type 0 inserted: {entity_counts['total_0_rows']}")
            print(f"  Entity type 1 inserted: {entity_counts['total_1_rows']}")
            print(f"  Entity type 2 inserted: {entity_counts['total_2_rows']}")
            
            return entity_counts

    finally:
        # Close the database connection for main processing
        close_db_connection(conn)

def log_search_table_creation(cursor, table_type, table_name, records_inserted, execution_time, status, error_message=None):
    """Log the search table creation process"""
    log_sql = """
        INSERT INTO npi_search_table_log 
        (execution_ts, table_type, table_name, records_inserted, execution_time_seconds, status, error_message) 
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """
    cursor.execute(log_sql, (
        datetime.now(),
        table_type,
        table_name,
        records_inserted,
        execution_time,
        status,
        error_message
    ))

def create_surgeon_table(letter, conn_params):
    """Create a single surgeon search table for the given letter"""
    start_time = time.time()
    table_name = f"search_surgeon_{letter.lower()}"
    records_inserted = 0
    
    # Create a new connection for this thread
    conn = get_db_connection()
    
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            # Drop table if exists
            cursor.execute(f"DROP TABLE IF EXISTS search_surgeon_facility.{table_name}")
            
            # Create and populate the table
            create_sql = f"""
                CREATE TABLE search_surgeon_facility.{table_name} 
                SELECT 
                    npi, 
                    provider_first_name AS first_name, 
                    provider_last_name AS last_name, 
                    provider_first_line_business_practice_location_address AS address, 
                    provider_business_practice_location_address_city_name AS city, 
                    provider_business_practice_location_address_state_name AS state, 
                    provider_business_practice_location_address_postal_code AS zip 
                FROM npi_data_1 
                WHERE LEFT(provider_last_name, 1) = %s 
                AND provider_last_name IS NOT NULL 
                AND provider_last_name != ''
            """
            
            cursor.execute(create_sql, (letter,))
            records_inserted = cursor.rowcount
            
            # Add indexes for better search performance
            cursor.execute(f"ALTER TABLE search_surgeon_facility.{table_name} ADD INDEX idx_npi (npi)")
            cursor.execute(f"ALTER TABLE search_surgeon_facility.{table_name} ADD INDEX idx_last_name (last_name)")
            cursor.execute(f"ALTER TABLE search_surgeon_facility.{table_name} ADD INDEX idx_first_name (first_name)")
            cursor.execute(f"ALTER TABLE search_surgeon_facility.{table_name} ADD INDEX idx_last_first (last_name, first_name)")
            
            conn.commit()
            
            execution_time = time.time() - start_time
            log_search_table_creation(cursor, 'surgeon', table_name, records_inserted, execution_time, 'success')
            conn.commit()
            
            print(f"Created {table_name}: {records_inserted} records in {execution_time:.2f} seconds")
            
    except Exception as e:
        execution_time = time.time() - start_time
        error_msg = str(e)
        print(f"Error creating {table_name}: {error_msg}")
        
        try:
            with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                log_search_table_creation(cursor, 'surgeon', table_name, 0, execution_time, 'error', error_msg)
                conn.commit()
        except:
            pass  # Don't fail if logging fails
            
    finally:
        close_db_connection(conn)

def create_facility_table(letter, conn_params):
    """Create a single facility search table for the given letter"""
    start_time = time.time()
    table_name = f"search_facility_{letter.lower()}"
    records_inserted = 0
    
    # Create a new connection for this thread
    conn = get_db_connection()
    
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            # Drop table if exists
            cursor.execute(f"DROP TABLE IF EXISTS search_surgeon_facility.{table_name}")
            
            # Create and populate the table
            create_sql = f"""
                CREATE TABLE search_surgeon_facility.{table_name} 
                SELECT 
                    npi, 
                    provider_organization_name AS facility_name, 
                    provider_first_line_business_practice_location_address AS address, 
                    provider_business_practice_location_address_city_name AS city, 
                    provider_business_practice_location_address_state_name AS state, 
                    provider_business_practice_location_address_postal_code AS zip 
                FROM npi_data_2 
                WHERE LEFT(provider_organization_name, 1) = %s 
                AND provider_organization_name IS NOT NULL 
                AND provider_organization_name != ''
            """
            
            cursor.execute(create_sql, (letter,))
            records_inserted = cursor.rowcount
            
            # Add indexes for better search performance
            cursor.execute(f"ALTER TABLE search_surgeon_facility.{table_name} ADD INDEX idx_npi (npi)")
            cursor.execute(f"ALTER TABLE search_surgeon_facility.{table_name} ADD INDEX idx_facility_name (facility_name)")
            
            conn.commit()
            
            execution_time = time.time() - start_time
            log_search_table_creation(cursor, 'facility', table_name, records_inserted, execution_time, 'success')
            conn.commit()
            
            print(f"Created {table_name}: {records_inserted} records in {execution_time:.2f} seconds")
            
    except Exception as e:
        execution_time = time.time() - start_time
        error_msg = str(e)
        print(f"Error creating {table_name}: {error_msg}")
        
        try:
            with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                log_search_table_creation(cursor, 'facility', table_name, 0, execution_time, 'error', error_msg)
                conn.commit()
        except:
            pass  # Don't fail if logging fails
            
    finally:
        close_db_connection(conn)

def create_search_tables():
    """Create all search tables using threading"""
    print("Starting creation of search tables...")
    start_time = time.time()
    
    # Get connection parameters (we'll create new connections in each thread)
    conn_params = None  # Not needed since get_db_connection() handles everything
    
    # Create all surgeon tables (A-Z)
    print("Creating surgeon search tables...")
    surgeon_threads = []
    for letter in string.ascii_uppercase:
        thread = threading.Thread(target=create_surgeon_table, args=(letter, conn_params))
        surgeon_threads.append(thread)
        thread.start()
    
    # Wait for all surgeon tables to complete
    for thread in surgeon_threads:
        thread.join()
    
    print("All surgeon tables created. Starting facility tables...")
    
    # Create all facility tables (A-Z)
    facility_threads = []
    for letter in string.ascii_uppercase:
        thread = threading.Thread(target=create_facility_table, args=(letter, conn_params))
        facility_threads.append(thread)
        thread.start()
    
    # Wait for all facility tables to complete
    for thread in facility_threads:
        thread.join()
    
    total_time = time.time() - start_time
    print(f"All search tables created in {total_time:.2f} seconds")

def cleanup_old_files(current_csv_file):
    """
    Clean up old files in the npi_data directory and archive the current CSV file:
    - Move the current CSV file to ../npi_data/archive directory
    - Keep only the new_header.csv file in the main directory
    - Delete all other files
    """
    print("Cleaning up old files and archiving current file...")
    
    # Create archive directory if it doesn't exist
    archive_dir = os.path.join(DOWNLOAD_DIR, 'archive')
    try:
        os.makedirs(archive_dir, exist_ok=True)
    except Exception as e:
        print(f"Warning: Could not create archive directory: {e}")
        return
    
    # Files to always preserve in main directory
    preserve_files = {
        'new_header.txt'
    }
    
    try:
        # First, move the current CSV file to archive
        current_file_path = os.path.join(DOWNLOAD_DIR, current_csv_file)
        archive_file_path = os.path.join(archive_dir, current_csv_file)
        
        if os.path.exists(current_file_path):
            try:
                # Use shutil.move for better cross-platform compatibility
                import shutil
                shutil.move(current_file_path, archive_file_path)
                print(f"  Archived: {current_csv_file} -> archive/{current_csv_file}")
            except Exception as e:
                print(f"  Warning: Could not archive {current_csv_file}: {e}")
        
        # Now clean up remaining files in main directory
        all_files = os.listdir(DOWNLOAD_DIR)
        deleted_count = 0
        
        for file_name in all_files:
            file_path = os.path.join(DOWNLOAD_DIR, file_name)
            
            # Skip if it's a directory (including our new archive directory)
            if os.path.isdir(file_path):
                continue
            
            # Skip if it's one of the files we want to preserve
            if file_name in preserve_files:
                continue
            
            # Delete the file
            try:
                os.remove(file_path)
                print(f"  Deleted: {file_name}")
                deleted_count += 1
            except Exception as e:
                print(f"  Warning: Could not delete {file_name}: {e}")
        
        if deleted_count > 0:
            print(f"Cleanup completed: {deleted_count} old files removed, current file archived")
        else:
            print("Cleanup completed: No old files to remove, current file archived")
            
    except Exception as e:
        print(f"Warning: Cleanup failed: {e}")
        # Don't raise the exception - cleanup failure shouldn't stop the main process

def main():
    """Main execution function"""
    print("Starting NPI data update process...")
    overall_start_time = time.time()
    
    try:
        # Step 1: Download and extract the NPI file
        csv_file = download_and_extract_npi_file()
        
        # Step 2: Process the main NPI data file
        entity_counts = process_npi_data_file(csv_file)
        
        # Step 3: Create the search tables
        create_search_tables()
        
        # Step 4: Clean up old files
        cleanup_old_files(csv_file)
        
        overall_time = time.time() - overall_start_time
        print(f"\nComplete NPI data update process finished successfully!")
        print(f"Total execution time: {overall_time:.2f} seconds ({overall_time/60:.1f} minutes)")
        
    except Exception as e:
        print(f"Error in main execution: {e}")
        raise

# Execute the main function
if __name__ == "__main__":
    main()