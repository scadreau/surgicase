# Test script to bulk update cases from status 15 to 20
# This will test the new timestamp functionality for paid_to_provider_ts

import sys
import os
import requests
import json

# Add the project root to the Python path
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.append(project_root)

from core.database import get_db_connection, close_db_connection
import pymysql.cursors

def find_cases_with_status_15():
    """Find all case IDs with status 15"""
    conn = None
    try:
        print("Connecting to database to find cases with status 15...")
        conn = get_db_connection()
        
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute("""
                SELECT case_id, user_id, case_date, patient_first, patient_last, case_status
                FROM cases 
                WHERE case_status = 15 AND active = 1
                ORDER BY case_create_ts
            """)
            cases = cursor.fetchall()
            
            print(f"Found {len(cases)} cases with status 15:")
            for case in cases:
                print(f"  - {case['case_id']}: {case['patient_first']} {case['patient_last']} (User: {case['user_id']}, Date: {case['case_date']})")
            
            return [case['case_id'] for case in cases]
            
    except Exception as e:
        print(f"Error finding cases: {e}")
        return []
    finally:
        if conn:
            close_db_connection(conn)

def test_bulk_update(case_ids):
    """Test the bulk update API"""
    if not case_ids:
        print("No cases to update.")
        return
    
    # Prepare the request payload
    payload = {
        "case_ids": case_ids,
        "new_status": 20,
        "force": False
    }
    
    print(f"\nTesting bulk update for {len(case_ids)} cases...")
    print(f"Request payload: {json.dumps(payload, indent=2)}")
    
    try:
        # Make the API request (assuming the server is running on localhost:8000)
        response = requests.patch(
            "http://localhost:8000/bulkupdatecasestatus",
            json=payload,
            headers={"Content-Type": "application/json"}
        )
        
        print(f"\nResponse Status: {response.status_code}")
        print(f"Response Body: {json.dumps(response.json(), indent=2)}")
        
        if response.status_code == 200:
            result = response.json()
            print(f"\n✅ SUCCESS: Updated {result['total_updated']} cases")
            print(f"   Processed: {result['total_processed']}")
            print(f"   Exceptions: {result['total_exceptions']}")
            
            # Show details for each updated case
            for case in result['updated_cases']:
                if 'timestamp_updated' in case:
                    print(f"   📅 {case['case_id']}: {case['previous_status']} → {case['new_status']} (Updated {case['timestamp_updated']['field']})")
                else:
                    print(f"   📄 {case['case_id']}: {case['previous_status']} → {case['new_status']} (No timestamp update)")
        else:
            print(f"❌ FAILED: {response.json()}")
            
    except requests.exceptions.ConnectionError:
        print("❌ ERROR: Could not connect to the API server. Make sure it's running on localhost:8000")
    except Exception as e:
        print(f"❌ ERROR: {e}")

def verify_updates(case_ids):
    """Verify the updates in the database"""
    if not case_ids:
        return
        
    conn = None
    try:
        print("\nVerifying updates in database...")
        conn = get_db_connection()
        
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            placeholders = ",".join(["%s"] * len(case_ids))
            cursor.execute(f"""
                SELECT case_id, case_status, paid_to_provider_ts, case_updated_ts
                FROM cases 
                WHERE case_id IN ({placeholders}) AND active = 1
                ORDER BY case_id
            """, case_ids)
            cases = cursor.fetchall()
            
            print(f"Database verification for {len(cases)} cases:")
            for case in cases:
                print(f"  - {case['case_id']}: Status={case['case_status']}, paid_to_provider_ts={case['paid_to_provider_ts']}")
            
    except Exception as e:
        print(f"Error verifying updates: {e}")
    finally:
        if conn:
            close_db_connection(conn)

if __name__ == "__main__":
    print("🧪 Testing Bulk Update Case Status (15 → 20)")
    print("=" * 50)
    
    # Step 1: Find cases with status 15
    case_ids = find_cases_with_status_15()
    
    if not case_ids:
        print("No cases found with status 15. Creating a test case...")
        # You could add code here to create a test case if needed
        print("Please manually set some cases to status 15 first.")
        sys.exit(1)
    
    # Step 2: Test the bulk update
    test_bulk_update(case_ids)
    
    # Step 3: Verify the results
    verify_updates(case_ids)
    
    print("\n✅ Test completed!") 