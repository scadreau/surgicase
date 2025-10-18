#!/usr/bin/env python3
"""
Test script for pay_amount_calculator function
Tests the specific case: 14f824b8-40e1-7004-ff6b-a89f7356cd56_1756492391684
"""

import sys
import os
# Add parent directory to path so we can import from core and utils
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.database import get_db_connection, close_db_connection
from utils.pay_amount_calculator import calculate_case_pay_amount_v2, update_case_pay_amount_v2
from decimal import Decimal
import pymysql.cursors

def get_case_info(case_id: str, conn):
    """Get basic case information including current pay_amount and user_id"""
    with conn.cursor(pymysql.cursors.DictCursor) as cursor:
        cursor.execute("""
            SELECT case_id, user_id, pay_amount, pay_category, case_create_ts
            FROM cases 
            WHERE case_id = %s
        """, (case_id,))
        return cursor.fetchone()

def get_case_procedure_codes(case_id: str, conn):
    """Get procedure codes for the case"""
    with conn.cursor(pymysql.cursors.DictCursor) as cursor:
        cursor.execute("""
            SELECT procedure_code
            FROM case_procedure_codes 
            WHERE case_id = %s
        """, (case_id,))
        return cursor.fetchall()

def get_user_tier(user_id: str, conn):
    """Get user tier information"""
    with conn.cursor(pymysql.cursors.DictCursor) as cursor:
        cursor.execute("""
            SELECT user_id, user_tier, active
            FROM user_profile 
            WHERE user_id = %s
        """, (user_id,))
        return cursor.fetchone()

def get_procedure_code_pay_amounts(codes: list, user_tier: int, conn):
    """Get pay amounts for procedure codes at specific tier"""
    if not codes:
        return []
    
    with conn.cursor(pymysql.cursors.DictCursor) as cursor:
        placeholders = ','.join(['%s'] * len(codes))
        query = f"""
            SELECT procedure_code, code_pay_amount, code_category, tier
            FROM procedure_codes 
            WHERE tier = %s AND procedure_code IN ({placeholders})
            ORDER BY code_pay_amount DESC
        """
        params = [user_tier] + codes
        cursor.execute(query, params)
        return cursor.fetchall()

def test_pay_calculator():
    """Test the pay_amount_calculator with the specified case"""
    case_id = "14f824b8-40e1-7004-ff6b-a89f7356cd56_1756492391684"
    
    # Extract user_id from case_id (first 36 bytes)
    user_id = case_id[:36]
    
    conn = None
    try:
        # Get database connection
        conn = get_db_connection()
        
        print(f"Testing pay_amount_calculator for case: {case_id}")
        print(f"Extracted user_id: {user_id}")
        print("=" * 80)
        
        # 1. Get case information
        print("\n1. Case Information:")
        case_info = get_case_info(case_id, conn)
        if not case_info:
            print(f"❌ Case {case_id} not found!")
            return
        
        print(f"   Case ID: {case_info['case_id']}")
        print(f"   User ID from DB: {case_info['user_id']}")
        print(f"   User ID extracted: {user_id}")
        print(f"   Current Pay Amount: ${case_info['pay_amount']}")
        print(f"   Current Pay Category: {case_info['pay_category']}")
        print(f"   Created At: {case_info['case_create_ts']}")
        
        # Verify the extracted user_id matches the one in the database
        if case_info['user_id'] != user_id:
            print(f"   ⚠️  WARNING: Extracted user_id doesn't match database user_id!")
        
        current_pay_amount = case_info['pay_amount']
        
        # 2. Get user tier
        print("\n2. User Information:")
        user_info = get_user_tier(user_id, conn)
        if not user_info:
            print(f"❌ User {user_id} not found!")
            return
        
        print(f"   User ID: {user_info['user_id']}")
        print(f"   User Tier: {user_info['user_tier']}")
        print(f"   Active: {user_info['active']}")
        
        # 3. Get procedure codes
        print("\n3. Procedure Codes:")
        procedure_codes = get_case_procedure_codes(case_id, conn)
        if not procedure_codes:
            print("   No procedure codes found for this case")
        else:
            codes = [row['procedure_code'] for row in procedure_codes]
            print(f"   Found {len(codes)} procedure codes: {codes}")
            
            # 4. Get pay amounts for these codes at user's tier
            print("\n4. Procedure Code Pay Amounts (at user's tier):")
            pay_amounts = get_procedure_code_pay_amounts(codes, user_info['user_tier'], conn)
            if not pay_amounts:
                print(f"   ❌ No pay amounts found for these codes at tier {user_info['user_tier']}")
            else:
                print(f"   Found {len(pay_amounts)} matching procedure codes:")
                for pa in pay_amounts:
                    print(f"      Code: {pa['procedure_code']}, Pay: ${pa['code_pay_amount']}, Category: {pa['code_category']}, Tier: {pa['tier']}")
        
        # 5. Test the calculator function
        print("\n5. Testing calculate_case_pay_amount_v2 function:")
        calc_result = calculate_case_pay_amount_v2(case_id, user_id, conn)
        
        print(f"   Success: {calc_result['success']}")
        print(f"   Calculated Pay Amount: ${calc_result['pay_amount']}")
        print(f"   Pay Category: {calc_result['pay_category']}")
        print(f"   Procedure Codes Found: {calc_result['procedure_codes_found']}")
        print(f"   Message: {calc_result['message']}")
        
        # 6. Compare with current stored value
        print("\n6. Comparison:")
        if current_pay_amount is not None:
            current_decimal = Decimal(str(current_pay_amount))
            calculated_decimal = calc_result['pay_amount']
            
            print(f"   Current stored pay amount: ${current_decimal}")
            print(f"   Calculated pay amount:     ${calculated_decimal}")
            
            if current_decimal == calculated_decimal:
                print("   ✅ Values match - calculator and database are consistent!")
            else:
                difference = calculated_decimal - current_decimal
                print(f"   ❌ Values differ by ${difference}")
                print("   This suggests the database still has incorrect data")
                
                # Check if calculated amount is $1000 as expected
                if calculated_decimal == Decimal('1000.00'):
                    print("   ✅ Calculator produces expected $1000.00")
                else:
                    print(f"   ❌ Calculator produces ${calculated_decimal}, not the expected $1000.00")
        else:
            print("   Current stored pay amount is NULL")
        
        # 7. Expected value check
        print("\n7. Expected Value Check:")
        expected_amount = Decimal('1000.00')
        if calc_result['pay_amount'] == expected_amount:
            print(f"   ✅ Calculator correctly produces expected ${expected_amount}")
        else:
            print(f"   ❌ Calculator produces ${calc_result['pay_amount']}, expected ${expected_amount}")
            print("   This indicates the procedure code data may still be incorrect")
        
    except Exception as e:
        print(f"\n❌ Error during testing: {str(e)}")
        if conn:
            conn.rollback()
            print("   Database changes rolled back")
        raise
    finally:
        if conn:
            close_db_connection(conn)

if __name__ == "__main__":
    test_pay_calculator()
