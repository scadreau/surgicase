#!/usr/bin/env python3
# Created: 2025-09-14 07:59:14
# Last Modified: 2025-09-14 08:01:11
# Author: Scott Cadreau

"""
Script to load CPT assist data from cpt_assist.csv into cpt_assist table

This script:
1. Creates a cpt_assist table with proper schema
2. Loads data from the CSV file with CPT code padding
3. Validates data integrity and provides detailed reporting

Expected CSV format:
- cpt_code: CPT codes that need left-padding with zeros to 5 digits
- asst_surg: Integer values (0, 1, 2, or 9)

Example usage:
    python load_cpt_assist.py

Input file: ../cpt_assist.csv (relative to script location)
Output: Data loaded into cpt_assist table
"""

import csv
import sys
import os
from typing import Dict, Any, Tuple

# Add the project root to the path so we can import modules
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from core.database import get_db_connection, close_db_connection

def create_cpt_assist_table(conn) -> bool:
    """
    Create cpt_assist table with proper schema for CPT assist data
    
    Args:
        conn: Database connection
        
    Returns:
        bool: True if successful, False otherwise
        
    Schema:
        - cpt_code: VARCHAR(5) NOT NULL - 5-digit CPT code with leading zeros
        - asst_surg: INT UNSIGNED NOT NULL - Assistant surgeon flag (0,1,2,9)
    """
    try:
        with conn.cursor() as cursor:
            # ! DANGER -- Dropping existing cpt_assist table if it exists
            drop_sql = "DROP TABLE IF EXISTS cpt_assist"
            cursor.execute(drop_sql)
            print("Dropped existing cpt_assist table if it existed")
            
            # Create table with proper schema
            create_sql = """
            CREATE TABLE cpt_assist (
                cpt_code VARCHAR(5) NOT NULL,
                asst_surg INT UNSIGNED NOT NULL,
                PRIMARY KEY (cpt_code),
                KEY idx_asst_surg (asst_surg)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
            """
            cursor.execute(create_sql)
            print("Created cpt_assist table successfully")
            
        return True
        
    except Exception as e:
        print(f"Error creating cpt_assist table: {e}")
        return False

def validate_and_clean_cpt_code(cpt_code: str) -> Tuple[bool, str, str]:
    """
    Validate and clean a CPT code by padding with leading zeros
    
    Args:
        cpt_code: Raw CPT code from CSV
        
    Returns:
        Tuple of (is_valid, cleaned_code, error_message)
        
    Business Rules:
        - All CPT codes must be padded to exactly 5 digits with leading zeros
        - Only alphanumeric characters are allowed
        - Empty codes are invalid
    """
    if not cpt_code or not cpt_code.strip():
        return False, "", "Empty CPT code"
    
    cleaned = cpt_code.strip().upper()
    
    # Check for invalid characters (only alphanumeric allowed)
    if not cleaned.replace('F', '').isdigit() and not cleaned.isalnum():
        return False, "", f"Invalid characters in CPT code: {cleaned}"
    
    # Pad numeric codes with leading zeros to 5 digits
    if cleaned.isdigit():
        if len(cleaned) > 5:
            return False, "", f"CPT code too long: {cleaned} (max 5 digits)"
        padded_code = cleaned.zfill(5)
    else:
        # Handle alphanumeric codes (like category codes ending in F)
        if len(cleaned) > 5:
            return False, "", f"CPT code too long: {cleaned} (max 5 characters)"
        # For alphanumeric codes, pad the numeric part only
        if cleaned.endswith('F') and len(cleaned) <= 5:
            numeric_part = cleaned[:-1]
            if numeric_part.isdigit():
                padded_numeric = numeric_part.zfill(4)  # 4 digits + F = 5 chars
                padded_code = padded_numeric + 'F'
            else:
                padded_code = cleaned.ljust(5, '0')  # Fallback padding
        else:
            padded_code = cleaned.ljust(5, '0')
    
    return True, padded_code, ""

def validate_asst_surg(asst_surg: str) -> Tuple[bool, int, str]:
    """
    Validate assistant surgeon flag value
    
    Args:
        asst_surg: Raw asst_surg value from CSV
        
    Returns:
        Tuple of (is_valid, int_value, error_message)
        
    Business Rules:
        - Must be a valid integer
        - Must be unsigned (>= 0)
        - Expected values are typically 0, 1, 2, or 9
    """
    if not asst_surg or not asst_surg.strip():
        return False, 0, "Empty asst_surg value"
    
    try:
        value = int(asst_surg.strip())
        if value < 0:
            return False, 0, f"asst_surg must be unsigned: {value}"
        return True, value, ""
    except ValueError:
        return False, 0, f"Invalid integer for asst_surg: {asst_surg}"

def load_csv_data(conn, csv_file_path: str) -> Dict[str, Any]:
    """
    Load and validate CSV data into cpt_assist table
    
    Args:
        conn: Database connection
        csv_file_path: Path to the CSV file
        
    Returns:
        Dict with results including success status, row counts, and validation errors
        
    Data Processing:
        - Validates and pads CPT codes to 5 digits
        - Validates asst_surg as unsigned integer
        - Processes data in batches for performance
        - Provides detailed error reporting
    """
    result = {
        'success': False,
        'rows_processed': 0,
        'rows_inserted': 0,
        'validation_errors': [],
        'duplicate_codes': [],
        'data_summary': {}
    }
    
    try:
        if not os.path.exists(csv_file_path):
            result['validation_errors'].append(f"CSV file not found: {csv_file_path}")
            return result
            
        print(f"Loading data from: {csv_file_path}")
        
        with open(csv_file_path, 'r', encoding='utf-8-sig') as csvfile:
            # Read CSV with DictReader to handle headers automatically
            reader = csv.DictReader(csvfile)
            
            if not reader.fieldnames or 'cpt_code' not in reader.fieldnames or 'asst_surg' not in reader.fieldnames:
                result['validation_errors'].append("CSV must have 'cpt_code' and 'asst_surg' columns")
                return result
            
            # TRANSACTION -- Loading CPT assist data with validation and deduplication
            insert_sql = "INSERT INTO cpt_assist (cpt_code, asst_surg) VALUES (%s, %s)"
            
            batch_size = 1000
            batch_data = []
            seen_codes = set()
            asst_surg_counts = {}
            
            with conn.cursor() as cursor:
                for row_num, row in enumerate(reader, 1):
                    try:
                        result['rows_processed'] += 1
                        
                        # INPUT VALIDATION -- Validating CPT code and assistant surgeon flag
                        raw_cpt_code = row.get('cpt_code', '').strip()
                        raw_asst_surg = row.get('asst_surg', '').strip()
                        
                        # Validate and clean CPT code
                        is_valid_cpt, clean_cpt_code, cpt_error = validate_and_clean_cpt_code(raw_cpt_code)
                        if not is_valid_cpt:
                            result['validation_errors'].append(f"Row {row_num}: {cpt_error}")
                            continue
                        
                        # Validate asst_surg
                        is_valid_asst, asst_surg_value, asst_error = validate_asst_surg(raw_asst_surg)
                        if not is_valid_asst:
                            result['validation_errors'].append(f"Row {row_num}: {asst_error}")
                            continue
                        
                        # Check for duplicates
                        if clean_cpt_code in seen_codes:
                            result['duplicate_codes'].append(f"Row {row_num}: Duplicate CPT code {clean_cpt_code}")
                            continue
                        
                        seen_codes.add(clean_cpt_code)
                        
                        # Track asst_surg distribution for summary
                        asst_surg_counts[asst_surg_value] = asst_surg_counts.get(asst_surg_value, 0) + 1
                        
                        # Add to batch
                        batch_data.append((clean_cpt_code, asst_surg_value))
                        
                        # Execute batch when it reaches batch_size
                        if len(batch_data) >= batch_size:
                            cursor.executemany(insert_sql, batch_data)
                            result['rows_inserted'] += len(batch_data)
                            print(f"Inserted batch of {len(batch_data)} rows (total: {result['rows_inserted']})")
                            batch_data = []
                            
                    except Exception as e:
                        result['validation_errors'].append(f"Row {row_num}: Unexpected error - {str(e)}")
                        continue
                
                # Insert remaining batch
                if batch_data:
                    cursor.executemany(insert_sql, batch_data)
                    result['rows_inserted'] += len(batch_data)
                    print(f"Inserted final batch of {len(batch_data)} rows (total: {result['rows_inserted']})")
        
        # Store summary data
        result['data_summary'] = {
            'asst_surg_distribution': asst_surg_counts,
            'unique_codes_processed': len(seen_codes),
            'duplicates_found': len(result['duplicate_codes'])
        }
        
        result['success'] = True
        print(f"Successfully loaded {result['rows_inserted']} rows from CSV")
        
    except Exception as e:
        result['validation_errors'].append(f"Error loading CSV data: {str(e)}")
        
    return result

def main():
    """
    Main function to orchestrate the CPT assist data loading process
    
    Process:
        1. Connects to database
        2. Creates cpt_assist table (drops existing if present)
        3. Loads and validates CSV data
        4. Provides comprehensive reporting
        
    Returns:
        bool: True if successful, False otherwise
    """
    
    # CSV file path (relative to script location)
    csv_file_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "cpt_assist.csv")
    
    print("Starting CPT assist data loading process...")
    print(f"CSV file: {csv_file_path}")
    
    conn = None
    try:
        # Get database connection
        print("\nConnecting to database...")
        conn = get_db_connection()
        print("Database connection established")
        
        # Start transaction
        conn.begin()
        
        # Step 1: Create cpt_assist table
        print("\nStep 1: Creating cpt_assist table...")
        if not create_cpt_assist_table(conn):
            print("Failed to create table. Exiting.")
            return False
            
        # Step 2: Load CSV data
        print(f"\nStep 2: Loading data from CSV file...")
        result = load_csv_data(conn, csv_file_path)
        
        if not result['success']:
            print("Failed to load CSV data. Rolling back transaction.")
            conn.rollback()
            return False
            
        # Commit transaction
        conn.commit()
        print("\nTransaction committed successfully!")
        
        # Print comprehensive summary
        print(f"\n=== LOADING SUMMARY ===")
        print(f"Rows processed: {result['rows_processed']}")
        print(f"Rows inserted: {result['rows_inserted']}")
        print(f"Validation errors: {len(result['validation_errors'])}")
        print(f"Duplicate codes found: {len(result['duplicate_codes'])}")
        
        # Show asst_surg distribution
        if result['data_summary'].get('asst_surg_distribution'):
            print(f"\nAssistant Surgeon Flag Distribution:")
            for flag, count in sorted(result['data_summary']['asst_surg_distribution'].items()):
                print(f"  asst_surg = {flag}: {count:,} codes")
        
        # Show validation errors (first 10)
        if result['validation_errors']:
            print(f"\nValidation Errors (showing first 10):")
            for error in result['validation_errors'][:10]:
                print(f"  - {error}")
            if len(result['validation_errors']) > 10:
                print(f"  ... and {len(result['validation_errors']) - 10} more errors")
        
        # Show duplicate codes (first 10)
        if result['duplicate_codes']:
            print(f"\nDuplicate Codes Found (showing first 10):")
            for duplicate in result['duplicate_codes'][:10]:
                print(f"  - {duplicate}")
            if len(result['duplicate_codes']) > 10:
                print(f"  ... and {len(result['duplicate_codes']) - 10} more duplicates")
        
        # Verify the data was loaded
        print(f"\nVerifying data in cpt_assist table...")
        with conn.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) as count FROM cpt_assist")
            count_result = cursor.fetchone()
            print(f"Total rows in cpt_assist: {count_result['count']:,}")
            
            # Show sample data
            cursor.execute("SELECT * FROM cpt_assist ORDER BY cpt_code LIMIT 10")
            sample_rows = cursor.fetchall()
            print(f"\nSample data (first 10 rows):")
            for row in sample_rows:
                print(f"  CPT: {row['cpt_code']} -> asst_surg: {row['asst_surg']}")
            
            # Show distribution by asst_surg
            cursor.execute("""
                SELECT asst_surg, COUNT(*) as count 
                FROM cpt_assist 
                GROUP BY asst_surg 
                ORDER BY asst_surg
            """)
            distribution = cursor.fetchall()
            print(f"\nFinal asst_surg distribution in database:")
            for row in distribution:
                print(f"  asst_surg = {row['asst_surg']}: {row['count']:,} codes")
        
        return True
        
    except Exception as e:
        print(f"Unexpected error: {e}")
        if conn:
            try:
                conn.rollback()
                print("Transaction rolled back due to error")
            except:
                pass
        return False
        
    finally:
        # Always close the database connection
        if conn:
            close_db_connection(conn)
            print("\nDatabase connection closed")

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
