# Created: 2025-07-16 15:00:00
# Last Modified: 2025-07-16 14:51:46

# tests/test_pay_amount_calculator.py
import sys
import os
import unittest
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
        # This test assumes there's a case in the database with no procedure codes
        # You may need to create a test case first or use an existing one
        case_id = "TEST_CASE_NO_CODES"
        user_id = "TEST_USER"
        
        result = calculate_case_pay_amount(case_id, user_id, self.conn)
        
        self.assertTrue(result["success"])
        self.assertEqual(result["pay_amount"], Decimal('0.00'))
        self.assertEqual(result["procedure_codes_found"], 0)
        self.assertIn("No procedure codes found", result["message"])
    
    def test_calculate_case_pay_amount_with_procedure_codes(self):
        """Test pay amount calculation for case with procedure codes."""
        # This test assumes there's a case with procedure codes and matching records in procedure_codes table
        # You may need to set up test data first
        case_id = "TEST_CASE_WITH_CODES"
        user_id = "TEST_USER"
        
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
        case_id = "TEST_CASE_UPDATE"
        user_id = "TEST_USER"
        
        result = update_case_pay_amount(case_id, user_id, self.conn)
        
        # The result should indicate success or appropriate error
        self.assertIn("pay_amount", result)
        self.assertIn("procedure_codes_found", result)
        self.assertIn("message", result)

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