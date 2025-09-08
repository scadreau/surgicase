# Created: 2025-01-08 16:40:00
# Last Modified: 2025-09-08 11:55:28
# Author: Scott Cadreau

import sys
import os
import argparse
import pymysql.cursors
import logging
from decimal import Decimal

# Add the parent directory to the Python path so we can import from core
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pay_amount_calculator import calculate_case_pay_amount
from core.database import get_db_connection, close_db_connection

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def get_cases_to_process(conn, specific_case_id=None):
    """
    Get all cases with status 0 or 10, or a specific case if case_id is provided.
    
    Args:
        conn: Database connection
        specific_case_id: Optional specific case_id to process
        
    Returns:
        list: List of case dictionaries with case_id, user_id, pay_amount, pay_category
    """
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            if specific_case_id:
                cursor.execute("""
                    SELECT case_id, user_id, pay_amount, pay_category, case_status
                    FROM cases 
                    WHERE case_id = %s
                """, (specific_case_id,))
            else:
                cursor.execute("""
                    SELECT case_id, user_id, pay_amount, pay_category, case_status
                    FROM cases 
                    WHERE case_status IN (0, 10)
                    ORDER BY case_id
                """)
            
            cases = cursor.fetchall()
            logger.info(f"Found {len(cases)} cases to process")
            return cases
            
    except Exception as e:
        logger.error(f"Error fetching cases: {str(e)}")
        raise

def process_cases(conn, dry_run=False, specific_case_id=None):
    """
    Process cases and recalculate pay amounts where needed.
    
    Args:
        conn: Database connection
        dry_run: If True, only show what would be changed without updating
        specific_case_id: Optional specific case_id to process
        
    Returns:
        dict: Summary of processing results
    """
    cases = get_cases_to_process(conn, specific_case_id)
    
    if not cases:
        logger.info("No cases found to process")
        return {
            "total_cases": 0,
            "skipped": 0,
            "updated": 0,
            "errors": 0
        }
    
    stats = {
        "total_cases": len(cases),
        "skipped": 0,
        "updated": 0,
        "errors": 0
    }
    
    logger.info(f"{'DRY RUN: ' if dry_run else ''}Processing {len(cases)} cases...")
    
    for i, case in enumerate(cases, 1):
        case_id = case['case_id']
        user_id = case['user_id']
        current_pay_amount = Decimal(str(case['pay_amount'])) if case['pay_amount'] else Decimal('0.00')
        current_pay_category = case['pay_category']
        
        logger.info(f"Processing case {i}/{len(cases)}: {case_id}")
        
        try:
            # Calculate what the pay amount should be
            calc_result = calculate_case_pay_amount(case_id, user_id, conn)
            
            if not calc_result["success"]:
                logger.error(f"Failed to calculate pay amount for case {case_id}: {calc_result['message']}")
                stats["errors"] += 1
                continue
            
            new_pay_amount = calc_result["pay_amount"]
            new_pay_category = calc_result["pay_category"]
            
            # Check if values need to be updated
            amount_changed = current_pay_amount != new_pay_amount
            category_changed = current_pay_category != new_pay_category
            
            if not amount_changed and not category_changed:
                logger.info(f"  Skipped - already correct: {current_pay_amount} ({current_pay_category})")
                stats["skipped"] += 1
                continue
            
            # Log the change
            change_msg = f"  {'WOULD UPDATE' if dry_run else 'UPDATING'}: {current_pay_amount} ({current_pay_category}) → {new_pay_amount} ({new_pay_category})"
            logger.info(change_msg)
            
            if not dry_run:
                # Update the database
                with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                    cursor.execute("""
                        UPDATE cases 
                        SET pay_amount = %s, pay_category = %s
                        WHERE case_id = %s
                    """, (new_pay_amount, new_pay_category, case_id))
                    
                    if cursor.rowcount == 0:
                        logger.error(f"  Failed to update case {case_id} - case not found")
                        stats["errors"] += 1
                        continue
                    
                    conn.commit()
                    logger.info(f"  Successfully updated case {case_id}")
            
            stats["updated"] += 1
            
        except Exception as e:
            logger.error(f"Error processing case {case_id}: {str(e)}")
            stats["errors"] += 1
            if not dry_run:
                conn.rollback()
    
    return stats

def main():
    """
    Main function to handle command line arguments and run the recalculation.
    """
    parser = argparse.ArgumentParser(description='Recalculate pay amounts for cases with status 0 or 10')
    parser.add_argument('--dry-run', action='store_true', help='Preview changes without updating database')
    parser.add_argument('--case-id', type=str, help='Process only a specific case ID')
    
    args = parser.parse_args()
    
    if args.dry_run:
        logger.info("=== DRY RUN MODE - NO CHANGES WILL BE MADE ===")
    
    try:
        conn = get_db_connection()
        
        try:
            stats = process_cases(conn, dry_run=args.dry_run, specific_case_id=args.case_id)
            
            # Print summary
            logger.info("=== PROCESSING SUMMARY ===")
            logger.info(f"Total cases processed: {stats['total_cases']}")
            logger.info(f"Cases skipped (already correct): {stats['skipped']}")
            logger.info(f"Cases {'that would be ' if args.dry_run else ''}updated: {stats['updated']}")
            logger.info(f"Cases with errors: {stats['errors']}")
            
            if args.dry_run and stats['updated'] > 0:
                logger.info("Run without --dry-run to apply these changes")
                
        finally:
            close_db_connection(conn)
            
    except Exception as e:
        logger.error(f"Script failed: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()
