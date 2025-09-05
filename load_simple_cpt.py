#!/usr/bin/env python3
"""
Load just CPT codes and descriptions from the cleaned CSV
"""
import csv
import sys
import os

# Add the project root to the path so we can import modules
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from core.database import get_db_connection, close_db_connection

def load_simple_cpt():
    """
    Load just CPT code and long description fields
    """
    csv_file = "/home/scadreau/surgicase/Consolidated_Code_List_final.csv"
    table_name = "cpt_codes"
    
    conn = None
    try:
        print("Connecting to database...")
        conn = get_db_connection()
        
        # Create table
        print("Creating table...")
        with conn.cursor() as cursor:
            cursor.execute("DROP TABLE IF EXISTS cpt_codes")
            
            with open("/home/scadreau/surgicase/create_simple_cpt_table.sql", 'r') as f:
                create_sql = f.read()
            cursor.execute(create_sql)
            print("Table created successfully!")
        
        print("Reading CSV file...")
        with open(csv_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            
            insert_sql = "INSERT INTO cpt_codes (cpt_code, description) VALUES (%s, %s)"
            print(f"Insert SQL: {insert_sql}")
            
            # Process in small batches
            batch_size = 100
            batch = []
            total_inserted = 0
            
            with conn.cursor() as cursor:
                for row_num, row in enumerate(reader, 1):
                    cpt_code = row.get('cpt_code', '').strip()
                    long_desc = row.get('long', '').strip()
                    
                    # Skip rows with empty CPT code
                    if not cpt_code:
                        continue
                    
                    # Handle empty description
                    if not long_desc:
                        long_desc = None
                    
                    batch.append((cpt_code, long_desc))
                    
                    # Insert batch when it reaches batch_size
                    if len(batch) >= batch_size:
                        try:
                            cursor.executemany(insert_sql, batch)
                            conn.commit()
                            total_inserted += len(batch)
                            print(f"Inserted batch: {total_inserted:,} rows total")
                            batch = []
                        except Exception as e:
                            print(f"Error inserting batch at row {row_num}: {e}")
                            # Try individual inserts to identify problem rows
                            conn.rollback()
                            for cpt, desc in batch:
                                try:
                                    cursor.execute(insert_sql, (cpt, desc))
                                    conn.commit()
                                    total_inserted += 1
                                except Exception as e2:
                                    print(f"Skipping problematic row - CPT: {cpt}, Error: {e2}")
                            batch = []
                
                # Insert final batch
                if batch:
                    try:
                        cursor.executemany(insert_sql, batch)
                        conn.commit()
                        total_inserted += len(batch)
                        print(f"Inserted final batch: {total_inserted:,} rows total")
                    except Exception as e:
                        print(f"Error inserting final batch: {e}")
                        # Try individual inserts
                        conn.rollback()
                        for cpt, desc in batch:
                            try:
                                cursor.execute(insert_sql, (cpt, desc))
                                conn.commit()
                                total_inserted += 1
                            except Exception as e2:
                                print(f"Skipping problematic row - CPT: {cpt}, Error: {e2}")
            
            print(f"\nSUCCESS: Loaded {total_inserted:,} CPT codes")
            
            # Verify and show sample data
            with conn.cursor() as cursor:
                cursor.execute(f"SELECT COUNT(*) as count FROM {table_name}")
                result = cursor.fetchone()
                print(f"Verification: Table now has {result['count']:,} rows")
                
                # Show sample records
                cursor.execute(f"SELECT cpt_code, LEFT(description, 100) as short_desc FROM {table_name} LIMIT 5")
                samples = cursor.fetchall()
                print("\nSample records:")
                for sample in samples:
                    print(f"  {sample['cpt_code']}: {sample['short_desc']}...")
            
            return True
            
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        if conn:
            conn.rollback()
        return False
        
    finally:
        if conn:
            close_db_connection(conn)

if __name__ == "__main__":
    success = load_simple_cpt()
    sys.exit(0 if success else 1)
