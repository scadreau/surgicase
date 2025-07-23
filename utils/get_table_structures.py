# Created: 2025-07-16 12:20:00
# Last Modified: 2025-07-23 11:59:02

# utils/get_table_structures.py
"""
Script to fetch all CREATE TABLE statements from the database.
This will provide a complete view of the current table structures.
Usage: python get_table_structures.py --save <filename>
Example: python get_table_structures.py --save my_tables.sql
If no filename is provided, the script will save to a file named table_structures_<timestamp>.sql
"""

import sys
import os
from datetime import datetime

# Add the project root to the Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(project_root)

from core.database import get_db_connection, close_db_connection
import pymysql.cursors

def get_all_table_structures():
    """
    Fetch all CREATE TABLE statements from the database.
    """
    conn = None
    try:
        print("Connecting to database...")
        conn = get_db_connection()
        
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            # Get all table names in the database
            cursor.execute("SHOW TABLES")
            tables = cursor.fetchall()
            
            if not tables:
                print("No tables found in the database.")
                return
            
            print(f"Found {len(tables)} tables in the database.")
            print("=" * 80)
            
            # Get CREATE TABLE statements for each table
            for table_info in tables:
                table_name = list(table_info.values())[0]  # Get the table name from the dict
                print(f"\n-- Table: {table_name}")
                print("-" * 60)
                
                # Get the CREATE TABLE statement
                cursor.execute(f"SHOW CREATE TABLE `{table_name}`")
                create_statement = cursor.fetchone()
                
                if create_statement:
                    # The CREATE TABLE statement is in the 'Create Table' column
                    create_sql = create_statement['Create Table']
                    print(create_sql)
                    print(";")
                else:
                    print(f"Could not retrieve CREATE TABLE statement for {table_name}")
                
                # Also get table information
                cursor.execute(f"DESCRIBE `{table_name}`")
                columns = cursor.fetchall()
                
                print(f"\n-- Column details for {table_name}:")
                for col in columns:
                    field = col['Field']
                    field_type = col['Type']
                    null = col['Null']
                    key = col['Key']
                    default = col['Default']
                    extra = col['Extra']
                    
                    # Handle None values for formatting
                    field_str = str(field) if field is not None else "NULL"
                    field_type_str = str(field_type) if field_type is not None else "NULL"
                    null_str = str(null) if null is not None else "NULL"
                    key_str = str(key) if key is not None else "NULL"
                    default_str = str(default) if default is not None else "NULL"
                    extra_str = str(extra) if extra is not None else "NULL"
                    
                    print(f"  {field_str:<20} {field_type_str:<20} {null_str:<4} {key_str:<4} {default_str:<10} {extra_str}")
                
                print("\n" + "=" * 80)
            
            # Get database information
            cursor.execute("SELECT DATABASE() as current_db")
            db_info = cursor.fetchone()
            db_name = db_info['current_db'] if db_info else "unknown"
            print(f"\n-- Database: {db_name}")
            
            # Get MySQL version
            cursor.execute("SELECT VERSION() as version")
            version_info = cursor.fetchone()
            version = version_info['version'] if version_info else "unknown"
            print(f"-- MySQL Version: {version}")
            
    except Exception as e:
        print(f"Error fetching table structures: {e}")
        raise
    finally:
        if conn:
            close_db_connection(conn)

def save_table_structures_to_file(filename=None):
    """
    Save all CREATE TABLE statements to a file.
    """
    if not filename:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"table_structures_{timestamp}.sql"
    
    conn = None
    try:
        print(f"Saving table structures to {filename}...")
        conn = get_db_connection()
        
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            # Get all table names
            cursor.execute("SHOW TABLES")
            tables = cursor.fetchall()
            
            # Get database and version info for the header
            cursor.execute("SELECT DATABASE() as current_db")
            db_info = cursor.fetchone()
            db_name = db_info['current_db'] if db_info else "unknown"
            
            cursor.execute("SELECT VERSION() as version")
            version_info = cursor.fetchone()
            version = version_info['version'] if version_info else "unknown"
            
            with open(filename, 'w') as f:
                f.write(f"-- Database Table Structures\n")
                f.write(f"-- Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"-- Database: {db_name}\n")
                f.write(f"-- MySQL Version: {version}\n\n")
                
                for table_info in tables:
                    table_name = list(table_info.values())[0]
                    
                    # Get CREATE TABLE statement
                    cursor.execute(f"SHOW CREATE TABLE `{table_name}`")
                    create_statement = cursor.fetchone()
                    
                    if create_statement:
                        create_sql = create_statement['Create Table']
                        f.write(f"-- Table: {table_name}\n")
                        f.write(f"{create_sql};\n\n")
        
        print(f"Table structures saved to {filename}")
        
    except Exception as e:
        print(f"Error saving table structures: {e}")
        raise
    finally:
        if conn:
            close_db_connection(conn)

if __name__ == "__main__":
    print("SurgiCase Database Table Structure Extractor")
    print("=" * 50)
    
    # Check command line arguments  
    if len(sys.argv) > 1 and sys.argv[1] == "--save":
        # Save to file
        filename = sys.argv[2] if len(sys.argv) > 2 else None
        save_table_structures_to_file(filename)
    else:
        # Display to console
        get_all_table_structures()
    
    print("\nDone!") 