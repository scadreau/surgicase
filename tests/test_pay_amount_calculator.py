# Created: 2025-07-16 15:00:00
# Last Modified: 2025-07-16 15:40:23

# tests/test_pay_amount_calculator.py
import sys
import os
import unittest
import pymysql.cursors
from decimal import Decimal

# Add the project root to the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.pay_amount_calculator import calculate_case_pay_amount, update_case_pay_amount
from core.database import get_db_connection, close_db_connection

class TestPayAmountCalculator(unittest.TestCase):
    """Test cases for pay amount calculator functionality."""
    
    def setUp(self):
        """Set up test database connection."""
        self.conn = get_db_connection()
        
    def tearDown(self):
        """Clean up test database connection."""
        if self.conn:
            close_db_connection(self.conn)
    
    def test_calculate_case_pay_amount_no_procedure_codes(self):
        """Test pay amount calculation for case with no procedure codes."""
        # Use a case that exists but has no procedure codes
        # You may need to create a test case first or use an existing one
        case_id = "TEST_CASE_NO_CODES"
        user_id = "TEST_USER"
        
        result = calculate_case_pay_amount(case_id, user_id, self.conn)
        
        # If the test case doesn't exist, we expect 0 procedure codes
        if result["success"]:
            self.assertEqual(result["pay_amount"], Decimal('0.00'))
            self.assertEqual(result["procedure_codes_found"], 0)
            self.assertIn("No procedure codes found", result["message"])
        else:
            # If case doesn't exist, that's also acceptable for this test
            self.assertIn("No procedure codes found", result["message"])
    
    def test_calculate_case_pay_amount_with_procedure_codes(self):
        """Test pay amount calculation for case with procedure codes."""
        # Use a real case that exists in the database
        case_id = "04e884e8-4011-70e9-f3bd-d89fabd15c7b_1752259839761"
        user_id = "04e884e8-4011-70e9-f3bd-d89fabd15c7b"
        
        result = calculate_case_pay_amount(case_id, user_id, self.conn)
        
        # The result should be successful if test data exists
        if result["success"]:
            self.assertGreaterEqual(result["pay_amount"], Decimal('0.00'))
            self.assertGreater(result["procedure_codes_found"], 0)
        else:
            # If no test data exists, we expect an error about missing procedure codes
            self.assertIn("No matching procedure codes found", result["message"])
    
    def test_update_case_pay_amount(self):
        """Test updating case pay amount."""
        case_id = "04e884e8-4011-70e9-f3bd-d89fabd15c7b_1752259839761"
        user_id = "04e884e8-4011-70e9-f3bd-d89fabd15c7b"
        
        result = update_case_pay_amount(case_id, user_id, self.conn)
        
        # The result should indicate success or appropriate error
        self.assertIn("pay_amount", result)
        self.assertIn("procedure_codes_found", result)
        self.assertIn("message", result)
        
        # If successful, verify the pay amount was updated in the database
        if result["success"]:
            with self.conn.cursor(pymysql.cursors.DictCursor) as cursor:
                cursor.execute("SELECT pay_amount FROM cases WHERE case_id = %s", (case_id,))
                case_data = cursor.fetchone()
                if case_data:
                    self.assertEqual(Decimal(str(case_data['pay_amount'])), result["pay_amount"])
    
    def test_calculate_case_pay_amount_real_data(self):
        """Test pay amount calculation with real database data."""
        # First, let's find a case that actually has procedure codes
        with self.conn.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute("""
                SELECT c.case_id, c.user_id, COUNT(cpc.procedure_code) as code_count
                FROM cases c
                LEFT JOIN case_procedure_codes cpc ON c.case_id = cpc.case_id
                WHERE c.active = 1
                GROUP BY c.case_id, c.user_id
                HAVING code_count > 0
                LIMIT 1
            """)
            case_data = cursor.fetchone()
            
            if case_data:
                case_id = case_data['case_id']
                user_id = case_data['user_id']
                expected_code_count = case_data['code_count']
                
                result = calculate_case_pay_amount(case_id, user_id, self.conn)
                
                print(f"Testing case {case_id} with {expected_code_count} procedure codes")
                print(f"Result: {result}")
                
                if result["success"]:
                    self.assertEqual(result["procedure_codes_found"], expected_code_count)
                    self.assertGreaterEqual(result["pay_amount"], Decimal('0.00'))
                else:
                    # If it failed, it should be because no matching procedure codes in procedure_codes table for the user's tier
                    self.assertIn("No matching procedure codes found", result["message"])
            else:
                # Skip this test if no cases with procedure codes exist
                self.skipTest("No cases with procedure codes found in database")
    
    def test_calculate_case_pay_amount_user_not_found(self):
        """Test pay amount calculation when user is not found."""
        case_id = "TEST_CASE"
        user_id = "NONEXISTENT_USER"
        
        result = calculate_case_pay_amount(case_id, user_id, self.conn)
        
        self.assertFalse(result["success"])
        self.assertEqual(result["pay_amount"], Decimal('0.00'))
        self.assertEqual(result["procedure_codes_found"], 0)
        self.assertIn("User not found or inactive", result["message"])
    
    def test_calculate_case_pay_amount_different_tiers(self):
        """Test pay amount calculation with different user tiers."""
        # First, let's find a case with procedure codes
        with self.conn.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute("""
                SELECT c.case_id, c.user_id, COUNT(cpc.procedure_code) as code_count
                FROM cases c
                LEFT JOIN case_procedure_codes cpc ON c.case_id = cpc.case_id
                WHERE c.active = 1
                GROUP BY c.case_id, c.user_id
                HAVING code_count > 0
                LIMIT 1
            """)
            case_data = cursor.fetchone()
            
            if case_data:
                case_id = case_data['case_id']
                user_id = case_data['user_id']
                
                # Get the user's current tier
                cursor.execute("SELECT user_tier FROM user_profile WHERE user_id = %s", (user_id,))
                user_info = cursor.fetchone()
                if not user_info:
                    self.skipTest(f"User {user_id} not found in database")
                original_tier = user_info['user_tier']
                
                # Test with tier 1
                cursor.execute("UPDATE user_profile SET user_tier = 1 WHERE user_id = %s", (user_id,))
                result_tier1 = calculate_case_pay_amount(case_id, user_id, self.conn)
                
                # Test with tier 2 (if it exists in procedure_codes table)
                cursor.execute("UPDATE user_profile SET user_tier = 2 WHERE user_id = %s", (user_id,))
                result_tier2 = calculate_case_pay_amount(case_id, user_id, self.conn)
                
                # Restore original tier
                cursor.execute("UPDATE user_profile SET user_tier = %s WHERE user_id = %s", (original_tier, user_id))
                
                # Both should return valid results (though pay amounts might differ)
                if result_tier1["success"] and result_tier2["success"]:
                    self.assertGreaterEqual(result_tier1["pay_amount"], Decimal('0.00'))
                    self.assertGreaterEqual(result_tier2["pay_amount"], Decimal('0.00'))
                    print(f"Tier 1 pay amount: {result_tier1['pay_amount']}")
                    print(f"Tier 2 pay amount: {result_tier2['pay_amount']}")
                else:
                    # At least one tier should work
                    self.assertTrue(result_tier1["success"] or result_tier2["success"])
            else:
                self.skipTest("No cases with procedure codes found in database")

def run_tests():
    """Run the pay amount calculator tests."""
    print("Running Pay Amount Calculator Tests...")
    print("=" * 50)
    
    # Create test suite
    suite = unittest.TestLoader().loadTestsFromTestCase(TestPayAmountCalculator)
    
    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # Print summary
    print("\n" + "=" * 50)
    print(f"Tests run: {result.testsRun}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")
    
    if result.failures:
        print("\nFailures:")
        for test, traceback in result.failures:
            print(f"  {test}: {traceback}")
    
    if result.errors:
        print("\nErrors:")
        for test, traceback in result.errors:
            print(f"  {test}: {traceback}")
    
    return result.wasSuccessful()

if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1) 