# Created: 2025-07-21
# Last Modified: 2025-07-21 14:39:23

import os
import requests
from bs4 import BeautifulSoup
from zipfile import ZipFile
from io import BytesIO
import pandas as pd
import pymysql.cursors
from datetime import datetime
from core.database import get_db_connection, close_db_connection

# Constants
URL = "https://download.cms.gov/nppes/NPI_Files.html"
DOWNLOAD_DIR = "npi_data"

# Ensure the download directory exists
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

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

# Correct the URL construction logic
if most_recent_link:
    # Ensure the link is correctly formed
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
else:
    print("No weekly files found.")
    exit()

# Identify the extracted CSV file, excluding '_fileheader.csv'
extracted_files = os.listdir(DOWNLOAD_DIR)
csv_file = next((f for f in extracted_files if f.startswith('npidata_pfile') and f.endswith('.csv') and '_fileheader' not in f), None)

if csv_file:
    csv_path = os.path.join(DOWNLOAD_DIR, csv_file)
    
    # Path to the new header file
    NEW_HEADER_FILE = os.path.join(DOWNLOAD_DIR, 'new_header.csv')
    
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
            
            batch_size = 1000
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

            # Insert log entry
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

            # Commit the transaction
            conn.commit()
            
            # Print summary
            print(f"Processing completed:")
            print(f"  Total rows processed: {processed_count}")
            print(f"  Entity type 0 inserted: {entity_counts['total_0_rows']}")
            print(f"  Entity type 1 inserted: {entity_counts['total_1_rows']}")
            print(f"  Entity type 2 inserted: {entity_counts['total_2_rows']}")

    finally:
        # Close the database connection
        close_db_connection(conn)

else:
    print("No CSV file found to process.") 