#!/usr/bin/env python3
"""
Script to load procedure codes CSV data into temp_procedure_codes table
Created: 2025-01-27
Author: Assistant

This script:
1. Creates a temp_procedure_codes table with the same structure as procedure_codes
2. Loads data from the CSV file into the new table
3. Uses the existing database connection infrastructure
"""

import csv
import sys
import os
from typing import Dict, Any

# Add the project root to the path so we can import modules
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from core.database import get_db_connection, close_db_connection

def create_temp_procedure_codes_table(conn) -> bool:
    """
    Create temp_procedure_codes table with same structure as procedure_codes table
    
    Args:
        conn: Database connection
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        with conn.cursor() as cursor:
            # Drop table if it exists
            drop_sql = "DROP TABLE IF EXISTS temp_procedure_codes"
            cursor.execute(drop_sql)
            print("Dropped existing temp_procedure_codes table if it existed")
            
            # Create table with same structure as procedure_codes
            create_sql = """
            CREATE TABLE temp_procedure_codes (
                procedure_code varchar(10) NOT NULL,
                procedure_desc varchar(1000) DEFAULT NULL,
                code_category varchar(20) DEFAULT NULL,
                code_status varchar(20) DEFAULT NULL,
                code_pay_amount decimal(10,2) DEFAULT '0.00',
                tier int NOT NULL DEFAULT '1',
                PRIMARY KEY (procedure_code, tier),
                KEY idx_tier_procedure (tier, procedure_code)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
            """
            cursor.execute(create_sql)
            print("Created temp_procedure_codes table successfully")
            
        return True
        
    except Exception as e:
        print(f"Error creating temp_procedure_codes table: {e}")
        return False

def load_csv_data(conn, csv_file_path: str) -> Dict[str, Any]:
    """
    Load CSV data into temp_procedure_codes table
    
    Args:
        conn: Database connection
        csv_file_path: Path to the CSV file
        
    Returns:
        Dict with results including success status and row counts
    """
    result = {
        'success': False,
        'rows_processed': 0,
        'rows_inserted': 0,
        'errors': []
    }
    
    try:
        if not os.path.exists(csv_file_path):
            result['errors'].append(f"CSV file not found: {csv_file_path}")
            return result
            
        with open(csv_file_path, 'r', encoding='utf-8-sig') as csvfile:
            # Read CSV with DictReader to handle headers automatically
            reader = csv.DictReader(csvfile)
            
            # Prepare insert statement
            insert_sql = """
            INSERT INTO temp_procedure_codes 
            (procedure_code, procedure_desc, code_category, code_status, code_pay_amount, tier)
            VALUES (%s, %s, %s, %s, %s, %s)
            """
            
            batch_size = 1000  # Process in batches for better performance
            batch_data = []
            
            with conn.cursor() as cursor:
                for row_num, row in enumerate(reader, 1):
                    try:
                        result['rows_processed'] += 1
                        
                        # Extract data from CSV row
                        procedure_code = row.get('procedure_code', '').strip()
                        procedure_desc = row.get('procedure_desc', '').strip()
                        code_category = row.get('code_category', '').strip()
                        code_status = row.get('code_status', '').strip()
                        
                        # Handle pay amount - convert to decimal
                        pay_amount_str = row.get('code_pay_amount', '0').strip()
                        try:
                            code_pay_amount = float(pay_amount_str) if pay_amount_str else 0.00
                        except ValueError:
                            code_pay_amount = 0.00
                            
                        # Handle tier - convert to int
                        tier_str = row.get('tier', '1').strip()
                        try:
                            tier = int(tier_str) if tier_str else 1
                        except ValueError:
                            tier = 1
                        
                        # Validate required fields
                        if not procedure_code:
                            result['errors'].append(f"Row {row_num}: Missing procedure_code")
                            continue
                            
                        # Add to batch
                        batch_data.append((
                            procedure_code,
                            procedure_desc if procedure_desc else None,
                            code_category if code_category else None,
                            code_status if code_status else None,
                            code_pay_amount,
                            tier
                        ))
                        
                        # Execute batch when it reaches batch_size
                        if len(batch_data) >= batch_size:
                            cursor.executemany(insert_sql, batch_data)
                            result['rows_inserted'] += len(batch_data)
                            print(f"Inserted batch of {len(batch_data)} rows (total: {result['rows_inserted']})")
                            batch_data = []
                            
                    except Exception as e:
                        result['errors'].append(f"Row {row_num}: {str(e)}")
                        continue
                
                # Insert remaining batch
                if batch_data:
                    cursor.executemany(insert_sql, batch_data)
                    result['rows_inserted'] += len(batch_data)
                    print(f"Inserted final batch of {len(batch_data)} rows (total: {result['rows_inserted']})")
        
        result['success'] = True
        print(f"Successfully loaded {result['rows_inserted']} rows from CSV")
        
    except Exception as e:
        result['errors'].append(f"Error loading CSV data: {str(e)}")
        
    return result

def main():
    """Main function to orchestrate the CSV loading process"""
    
    # CSV file path (relative to script location)
    csv_file_path = "/home/scadreau/procedure_codes_202508291719a.csv"
    
    print("Starting procedure codes CSV loading process...")
    print(f"CSV file: {csv_file_path}")
    
    conn = None
    try:
        # Get database connection
        print("Connecting to database...")
        conn = get_db_connection()
        print("Database connection established")
        
        # Start transaction
        conn.begin()
        
        # Step 1: Create temp_procedure_codes table
        print("\nStep 1: Creating temp_procedure_codes table...")
        if not create_temp_procedure_codes_table(conn):
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
        
        # Print summary
        print(f"\n=== SUMMARY ===")
        print(f"Rows processed: {result['rows_processed']}")
        print(f"Rows inserted: {result['rows_inserted']}")
        print(f"Errors: {len(result['errors'])}")
        
        if result['errors']:
            print("\nErrors encountered:")
            for error in result['errors'][:10]:  # Show first 10 errors
                print(f"  - {error}")
            if len(result['errors']) > 10:
                print(f"  ... and {len(result['errors']) - 10} more errors")
        
        # Verify the data was loaded
        print(f"\nVerifying data in temp_procedure_codes table...")
        with conn.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) as count FROM temp_procedure_codes")
            count_result = cursor.fetchone()
            print(f"Total rows in temp_procedure_codes: {count_result['count']}")
            
            # Show sample data
            cursor.execute("SELECT * FROM temp_procedure_codes LIMIT 5")
            sample_rows = cursor.fetchall()
            print(f"\nSample data:")
            for row in sample_rows:
                print(f"  {row['procedure_code']}: {row['procedure_desc']} (Category: {row['code_category']}, Tier: {row['tier']}, Amount: ${row['code_pay_amount']})")
        
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
            print("Database connection closed")

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
