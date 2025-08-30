#!/usr/bin/env python3
"""
Generalized CSV Loader Script
Created: 2025-01-27
Author: Assistant

A reusable script to load CSV data into any existing database table.
Validates that CSV columns match the target table schema before loading.

Usage:
    python load_csv.py --input <csv_file> --table <table_name> [options]

Examples:
    python load_csv.py --input data.csv --table temp_procedure_codes
    python load_csv.py --input users.csv --table user_profiles --batch-size 500 --dry-run
"""

import csv
import sys
import os
import argparse
from typing import Dict, Any, List, Tuple, Optional

# Add the project root to the path so we can import modules
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from core.database import get_db_connection, close_db_connection

def get_table_schema(conn, table_name: str) -> Dict[str, Dict[str, Any]]:
    """
    Get the schema information for a table
    
    Args:
        conn: Database connection
        table_name: Name of the table
        
    Returns:
        Dict mapping column names to their properties
        
    Raises:
        Exception: If table doesn't exist or can't be accessed
    """
    try:
        with conn.cursor() as cursor:
            cursor.execute(f"DESCRIBE {table_name}")
            columns = cursor.fetchall()
            
            if not columns:
                raise Exception(f"Table '{table_name}' does not exist or has no columns")
            
            schema = {}
            for col in columns:
                schema[col['Field']] = {
                    'type': col['Type'],
                    'null': col['Null'] == 'YES',
                    'key': col['Key'],
                    'default': col['Default'],
                    'extra': col.get('Extra', '')
                }
            
            return schema
            
    except Exception as e:
        raise Exception(f"Error getting schema for table '{table_name}': {str(e)}")

def validate_csv_against_schema(csv_file_path: str, schema: Dict[str, Dict[str, Any]]) -> Tuple[bool, List[str]]:
    """
    Validate that CSV columns match the table schema
    
    Args:
        csv_file_path: Path to the CSV file
        schema: Table schema from get_table_schema()
        
    Returns:
        Tuple of (is_valid, list_of_errors)
    """
    errors = []
    
    try:
        with open(csv_file_path, 'r', encoding='utf-8-sig') as csvfile:
            reader = csv.DictReader(csvfile)
            csv_columns = set(reader.fieldnames or [])
            
            # Get table columns (excluding auto-increment columns)
            table_columns = set()
            required_columns = set()
            
            for col_name, col_info in schema.items():
                # Skip auto-increment columns
                if 'auto_increment' not in col_info['extra'].lower():
                    table_columns.add(col_name)
                    
                    # Required columns are those that are NOT NULL and have no default
                    if not col_info['null'] and col_info['default'] is None and 'auto_increment' not in col_info['extra'].lower():
                        required_columns.add(col_name)
            
            # Check for missing required columns
            missing_required = required_columns - csv_columns
            if missing_required:
                errors.append(f"Missing required columns: {', '.join(sorted(missing_required))}")
            
            # Check for extra columns in CSV
            extra_columns = csv_columns - table_columns
            if extra_columns:
                errors.append(f"CSV contains columns not in table: {', '.join(sorted(extra_columns))}")
            
            # Check for missing optional columns (warn but don't fail)
            missing_optional = table_columns - csv_columns - {col for col, info in schema.items() if 'auto_increment' in info['extra'].lower()}
            if missing_optional:
                print(f"Warning: CSV missing optional columns (will use defaults): {', '.join(sorted(missing_optional))}")
            
    except Exception as e:
        errors.append(f"Error reading CSV file: {str(e)}")
    
    return len(errors) == 0, errors

def convert_value_for_column(value: str, column_name: str, column_info: Dict[str, Any]) -> Any:
    """
    Convert a CSV string value to the appropriate type for the database column
    
    Args:
        value: String value from CSV
        column_name: Name of the column
        column_info: Column information from schema
        
    Returns:
        Converted value appropriate for the column type
    """
    if not value.strip():
        # Handle empty values
        if column_info['null']:
            return None
        elif column_info['default'] is not None:
            return column_info['default']
        else:
            raise ValueError(f"Column '{column_name}' cannot be NULL and has no default value")
    
    col_type = column_info['type'].lower()
    
    try:
        # Integer types
        if any(t in col_type for t in ['int', 'tinyint', 'smallint', 'mediumint', 'bigint']):
            return int(value)
        
        # Decimal/Float types
        elif any(t in col_type for t in ['decimal', 'numeric', 'float', 'double']):
            return float(value)
        
        # String types - return as-is, MySQL will handle truncation if needed
        elif any(t in col_type for t in ['varchar', 'char', 'text', 'longtext', 'mediumtext', 'tinytext']):
            return value.strip()
        
        # Date/Time types - let MySQL handle the conversion
        elif any(t in col_type for t in ['date', 'time', 'datetime', 'timestamp']):
            return value.strip()
        
        # Boolean types
        elif 'bool' in col_type or col_type == 'bit(1)':
            return value.lower() in ('1', 'true', 'yes', 'on')
        
        # Default: return as string
        else:
            return value.strip()
            
    except ValueError as e:
        raise ValueError(f"Cannot convert value '{value}' for column '{column_name}' (type: {col_type}): {str(e)}")

def load_csv_data(conn, csv_file_path: str, table_name: str, schema: Dict[str, Dict[str, Any]], 
                  batch_size: int = 1000, dry_run: bool = False) -> Dict[str, Any]:
    """
    Load CSV data into the specified table
    
    Args:
        conn: Database connection
        csv_file_path: Path to the CSV file
        table_name: Name of the target table
        schema: Table schema information
        batch_size: Number of rows to insert per batch
        dry_run: If True, validate data but don't insert
        
    Returns:
        Dict with results including success status and row counts
    """
    result = {
        'success': False,
        'rows_processed': 0,
        'rows_inserted': 0,
        'errors': [],
        'dry_run': dry_run
    }
    
    try:
        with open(csv_file_path, 'r', encoding='utf-8-sig') as csvfile:
            reader = csv.DictReader(csvfile)
            csv_columns = reader.fieldnames or []
            
            # Build column list and insert statement
            table_columns = [col for col in csv_columns if col in schema]
            placeholders = ', '.join(['%s'] * len(table_columns))
            column_list = ', '.join(table_columns)
            
            insert_sql = f"INSERT INTO {table_name} ({column_list}) VALUES ({placeholders})"
            
            if dry_run:
                print(f"DRY RUN: Would execute: {insert_sql}")
            
            batch_data = []
            
            with conn.cursor() as cursor:
                for row_num, row in enumerate(reader, 1):
                    try:
                        result['rows_processed'] += 1
                        
                        # Convert values according to column types
                        converted_values = []
                        for col_name in table_columns:
                            raw_value = row.get(col_name, '')
                            converted_value = convert_value_for_column(raw_value, col_name, schema[col_name])
                            converted_values.append(converted_value)
                        
                        batch_data.append(tuple(converted_values))
                        
                        # Execute batch when it reaches batch_size
                        if len(batch_data) >= batch_size:
                            if not dry_run:
                                cursor.executemany(insert_sql, batch_data)
                                result['rows_inserted'] += len(batch_data)
                                print(f"Inserted batch of {len(batch_data)} rows (total: {result['rows_inserted']})")
                            else:
                                print(f"DRY RUN: Would insert batch of {len(batch_data)} rows")
                            batch_data = []
                            
                    except Exception as e:
                        result['errors'].append(f"Row {row_num}: {str(e)}")
                        continue
                
                # Insert remaining batch
                if batch_data:
                    if not dry_run:
                        cursor.executemany(insert_sql, batch_data)
                        result['rows_inserted'] += len(batch_data)
                        print(f"Inserted final batch of {len(batch_data)} rows (total: {result['rows_inserted']})")
                    else:
                        print(f"DRY RUN: Would insert final batch of {len(batch_data)} rows")
        
        result['success'] = True
        if not dry_run:
            print(f"Successfully loaded {result['rows_inserted']} rows into {table_name}")
        else:
            print(f"DRY RUN: Validation successful. {result['rows_processed']} rows would be inserted.")
        
    except Exception as e:
        result['errors'].append(f"Error loading CSV data: {str(e)}")
        
    return result

def main():
    """Main function to handle command line arguments and orchestrate the loading process"""
    
    parser = argparse.ArgumentParser(
        description='Load CSV data into an existing database table',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --input data.csv --table users
  %(prog)s --input products.csv --table inventory --batch-size 500
  %(prog)s --input test.csv --table temp_data --dry-run
        """
    )
    
    parser.add_argument('--input', '-i', required=True,
                       help='Path to the CSV file to load')
    parser.add_argument('--table', '-t', required=True,
                       help='Name of the target database table')
    parser.add_argument('--batch-size', '-b', type=int, default=1000,
                       help='Number of rows to insert per batch (default: 1000)')
    parser.add_argument('--dry-run', '-d', action='store_true',
                       help='Validate data but do not insert into database')
    parser.add_argument('--verbose', '-v', action='store_true',
                       help='Enable verbose output')
    
    args = parser.parse_args()
    
    # Validate arguments
    if not os.path.exists(args.input):
        print(f"Error: CSV file '{args.input}' does not exist")
        return False
    
    if args.batch_size <= 0:
        print("Error: Batch size must be greater than 0")
        return False
    
    print(f"CSV Loader - {'DRY RUN MODE' if args.dry_run else 'LIVE MODE'}")
    print(f"Input file: {args.input}")
    print(f"Target table: {args.table}")
    print(f"Batch size: {args.batch_size}")
    
    conn = None
    try:
        # Get database connection
        print("\nConnecting to database...")
        conn = get_db_connection()
        print("Database connection established")
        
        # Get table schema
        print(f"\nValidating table '{args.table}'...")
        schema = get_table_schema(conn, args.table)
        print(f"Table has {len(schema)} columns")
        
        if args.verbose:
            print("Table schema:")
            for col_name, col_info in schema.items():
                nullable = "NULL" if col_info['null'] else "NOT NULL"
                print(f"  {col_name}: {col_info['type']} {nullable}")
        
        # Validate CSV against schema
        print(f"\nValidating CSV file against table schema...")
        is_valid, validation_errors = validate_csv_against_schema(args.input, schema)
        
        if not is_valid:
            print("ERROR: CSV validation failed:")
            for error in validation_errors:
                print(f"  - {error}")
            return False
        
        print("CSV validation successful!")
        
        # Start transaction (only if not dry run)
        if not args.dry_run:
            conn.begin()
        
        # Load data
        print(f"\n{'Validating' if args.dry_run else 'Loading'} CSV data...")
        result = load_csv_data(conn, args.input, args.table, schema, args.batch_size, args.dry_run)
        
        if not result['success']:
            if not args.dry_run:
                print("Failed to load CSV data. Rolling back transaction.")
                conn.rollback()
            return False
        
        # Commit transaction (only if not dry run)
        if not args.dry_run:
            conn.commit()
            print("Transaction committed successfully!")
        
        # Print summary
        print(f"\n=== SUMMARY ===")
        print(f"Mode: {'DRY RUN' if args.dry_run else 'LIVE'}")
        print(f"Rows processed: {result['rows_processed']}")
        if not args.dry_run:
            print(f"Rows inserted: {result['rows_inserted']}")
        print(f"Errors: {len(result['errors'])}")
        
        if result['errors']:
            print(f"\nErrors encountered:")
            for error in result['errors'][:10]:  # Show first 10 errors
                print(f"  - {error}")
            if len(result['errors']) > 10:
                print(f"  ... and {len(result['errors']) - 10} more errors")
        
        # Verify the data was loaded (only if not dry run)
        if not args.dry_run:
            print(f"\nVerifying data in {args.table}...")
            with conn.cursor() as cursor:
                cursor.execute(f"SELECT COUNT(*) as count FROM {args.table}")
                count_result = cursor.fetchone()
                print(f"Total rows in {args.table}: {count_result['count']}")
        
        return True
        
    except Exception as e:
        print(f"Unexpected error: {e}")
        if conn and not args.dry_run:
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
