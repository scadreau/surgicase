#!/usr/bin/env python3
# Created: 2025-09-14 09:39:53
# Last Modified: 2025-09-14 09:40:30
# Author: Scott Cadreau

"""
Direct Case Status Relegation Script - Assistant Surgeon Billing Logic

This script:
1. Finds all cases with case_status = 10 (ready for submission)
2. Checks each case's procedure codes for billable assistant surgeon procedures (asst_surg = 2)
3. Relegates cases WITHOUT billable procedures to status 7 (needs review)
4. Leaves cases WITH billable procedures at status 10 (ready for submission)

CRITICAL: This affects payment processing scheduled for Monday morning.
Always run in dry-run mode first to review changes before executing live.

This script uses DIRECT SQL updates and bypasses the complex update_case_status logic
for a clean, predictable one-time migration.

Usage:
    python relegate_status_10_cases.py --dry-run    # Safe preview mode
    python relegate_status_10_cases.py --live       # Execute changes
"""

import sys
import os
import json
import csv
import argparse
from datetime import datetime
from typing import List, Dict, Any

# Add the project root to the path so we can import modules
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from core.database import get_db_connection, close_db_connection

def analyze_status_10_cases(conn) -> Dict[str, Any]:
    """
    Analyze all cases in status 10 to determine which need relegation
    
    Args:
        conn: Database connection
        
    Returns:
        Dict with analysis results and case lists
    """
    try:
        with conn.cursor() as cursor:
            # Get all cases in status 10 with their billable procedure counts
            cursor.execute("""
                SELECT 
                    c.case_id,
                    c.user_id,
                    c.case_date,
                    c.patient_first,
                    c.patient_last,
                    COALESCE(billable.billable_count, 0) as billable_procedures
                FROM cases c
                LEFT JOIN (
                    SELECT 
                        case_id,
                        COUNT(*) as billable_count
                    FROM case_procedure_codes 
                    WHERE asst_surg = 2
                    GROUP BY case_id
                ) billable ON c.case_id = billable.case_id
                WHERE c.case_status = 10 AND c.active = 1
                ORDER BY c.case_date DESC, c.case_id
            """)
            
            all_cases = cursor.fetchall()
            
            # Separate cases into those that stay vs. those that get relegated
            cases_staying_10 = []
            cases_to_relegate = []
            
            for case in all_cases:
                case_data = {
                    'case_id': case['case_id'],
                    'user_id': case['user_id'],
                    'case_date': case['case_date'].isoformat() if case['case_date'] else None,
                    'patient_first': case['patient_first'],
                    'patient_last': case['patient_last'],
                    'billable_procedures': case['billable_procedures']
                }
                
                if case['billable_procedures'] > 0:
                    # Has billable procedures - stays at status 10
                    cases_staying_10.append(case_data)
                else:
                    # No billable procedures - needs relegation to status 7
                    cases_to_relegate.append(case_data)
            
            analysis = {
                'total_cases': len(all_cases),
                'cases_staying_status_10': len(cases_staying_10),
                'cases_to_relegate': len(cases_to_relegate),
                'staying_cases': cases_staying_10,
                'relegation_cases': cases_to_relegate
            }
            
            return analysis
            
    except Exception as e:
        raise Exception(f"Error analyzing status 10 cases: {str(e)}")

def relegate_cases(conn, cases_to_relegate: List[Dict[str, Any]], dry_run: bool = True) -> Dict[str, Any]:
    """
    Relegate specified cases from status 10 to status 7
    
    Args:
        conn: Database connection
        cases_to_relegate: List of cases that need relegation
        dry_run: If True, don't make actual changes
        
    Returns:
        Dict with results
    """
    results = {
        'dry_run': dry_run,
        'timestamp': datetime.now().isoformat(),
        'total_cases_to_relegate': len(cases_to_relegate),
        'cases_successfully_relegated': 0,
        'cases_with_errors': 0,
        'relegated_cases': [],
        'error_cases': []
    }
    
    if len(cases_to_relegate) == 0:
        print("ℹ️  No cases need relegation - all cases have billable procedures")
        return results
    
    print(f"\n{'DRY RUN MODE' if dry_run else 'LIVE MODE'} - Relegating {len(cases_to_relegate)} cases...")
    
    try:
        if not dry_run:
            # Start transaction for live mode
            conn.begin()
        
        for i, case in enumerate(cases_to_relegate, 1):
            case_id = case['case_id']
            
            try:
                # Print progress every 5 cases
                if i % 5 == 0 or i == len(cases_to_relegate):
                    print(f"Progress: {i}/{len(cases_to_relegate)} cases processed...")
                
                if dry_run:
                    # Dry run - just record what would happen
                    results['cases_successfully_relegated'] += 1
                    results['relegated_cases'].append({
                        **case,
                        'action': 'Would relegate from status 10 to status 7',
                        'reason': f'No billable assistant surgeon procedures (found {case["billable_procedures"]} billable procedures)'
                    })
                else:
                    # Live mode - actually update the database
                    with conn.cursor() as cursor:
                        cursor.execute("""
                            UPDATE cases 
                            SET case_status = 7 
                            WHERE case_id = %s AND case_status = 10 AND active = 1
                        """, (case_id,))
                        
                        if cursor.rowcount == 1:
                            # Successfully updated
                            results['cases_successfully_relegated'] += 1
                            results['relegated_cases'].append({
                                **case,
                                'action': 'Successfully relegated from status 10 to status 7',
                                'reason': f'No billable assistant surgeon procedures (found {case["billable_procedures"]} billable procedures)'
                            })
                        elif cursor.rowcount == 0:
                            # No rows updated - case might have changed status or been deactivated
                            results['error_cases'].append({
                                **case,
                                'error': 'Case not found or no longer in status 10'
                            })
                            results['cases_with_errors'] += 1
                        else:
                            # Multiple rows updated - should never happen with proper case_id
                            results['error_cases'].append({
                                **case,
                                'error': f'Unexpected: {cursor.rowcount} rows updated'
                            })
                            results['cases_with_errors'] += 1
                        
            except Exception as e:
                results['error_cases'].append({
                    **case,
                    'error': f'Exception during processing: {str(e)}'
                })
                results['cases_with_errors'] += 1
                continue
        
        if not dry_run:
            # Commit changes in live mode
            conn.commit()
            print(f"\n✅ COMMITTED changes to database")
        
        print(f"\n{'DRY RUN' if dry_run else 'LIVE'} COMPLETED:")
        print(f"  Cases to relegate: {results['total_cases_to_relegate']}")
        print(f"  Cases successfully relegated: {results['cases_successfully_relegated']}")
        print(f"  Cases with errors: {results['cases_with_errors']}")
        
        return results
        
    except Exception as e:
        if not dry_run:
            try:
                conn.rollback()
                print(f"\n❌ ROLLED BACK transaction due to error")
            except:
                pass
        raise Exception(f"Error during case relegation: {str(e)}")

def save_results(analysis: Dict[str, Any], results: Dict[str, Any], output_format: str = 'json'):
    """
    Save analysis and results to file for review
    
    Args:
        analysis: Analysis results from analyze_status_10_cases
        results: Results from relegate_cases
        output_format: 'json' or 'csv'
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    mode = "dry_run" if results['dry_run'] else "live"
    
    # Combine analysis and results
    combined_results = {
        'analysis': analysis,
        'relegation_results': results
    }
    
    if output_format == 'json':
        filename = f"case_relegation_{mode}_{timestamp}.json"
        with open(filename, 'w') as f:
            json.dump(combined_results, f, indent=2)
        print(f"\n📄 Results saved to: {filename}")
        
    elif output_format == 'csv' and results['relegated_cases']:
        filename = f"relegated_cases_{mode}_{timestamp}.csv"
        with open(filename, 'w', newline='') as f:
            if results['relegated_cases']:
                fieldnames = results['relegated_cases'][0].keys()
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(results['relegated_cases'])
                print(f"\n📄 Relegated cases saved to: {filename}")
    
    return filename

def main():
    """Main function to handle command line arguments and orchestrate the relegation process"""
    
    parser = argparse.ArgumentParser(
        description='Relegate status 10 cases without billable assistant surgeon procedures to status 7',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --dry-run                    # Preview changes without executing
  %(prog)s --live                       # Execute changes to database
  %(prog)s --live --force               # Execute without confirmation prompt
  %(prog)s --dry-run --format csv       # Save relegated cases as CSV
        """
    )
    
    parser.add_argument('--dry-run', action='store_true',
                       help='Preview mode - show what would change without making database changes')
    parser.add_argument('--live', action='store_true',
                       help='Live mode - execute actual database changes')
    parser.add_argument('--force', action='store_true',
                       help='Skip confirmation prompt in live mode')
    parser.add_argument('--format', choices=['json', 'csv'], default='json',
                       help='Output format for results (default: json)')
    
    args = parser.parse_args()
    
    # Validate arguments
    if not args.dry_run and not args.live:
        print("ERROR: Must specify either --dry-run or --live mode")
        return False
    
    if args.dry_run and args.live:
        print("ERROR: Cannot specify both --dry-run and --live modes")
        return False
    
    dry_run_mode = args.dry_run
    
    print("="*80)
    print("CASE STATUS RELEGATION SCRIPT")
    print("="*80)
    print(f"Mode: {'DRY RUN (safe preview)' if dry_run_mode else 'LIVE (will modify database)'}")
    print(f"Target: Cases with case_status = 10 WITHOUT billable assistant surgeon procedures")
    print(f"Action: Relegate to status 7 (needs review)")
    print(f"Output: {args.format.upper()} format")
    print("="*80)
    
    if not dry_run_mode and not args.force:
        print("\n⚠️  WARNING: LIVE MODE WILL MODIFY PRODUCTION DATABASE")
        print("⚠️  This affects payment processing scheduled for Monday morning")
        confirmation = input("\nType 'CONFIRM' to proceed with live changes: ")
        if confirmation != 'CONFIRM':
            print("❌ Operation cancelled")
            return False
    elif not dry_run_mode and args.force:
        print("\n⚠️  WARNING: LIVE MODE WITH --force FLAG")
        print("⚠️  Skipping confirmation prompt - proceeding with database changes")
    
    conn = None
    try:
        # Get database connection
        print(f"\n🔌 Connecting to database...")
        conn = get_db_connection()
        print("✅ Database connection established")
        
        # Analyze all cases in status 10
        print(f"\n📊 Analyzing cases with status 10...")
        analysis = analyze_status_10_cases(conn)
        print(f"✅ Analysis complete:")
        print(f"   Total cases in status 10: {analysis['total_cases']}")
        print(f"   Cases staying status 10 (have billable procedures): {analysis['cases_staying_status_10']}")
        print(f"   Cases to relegate to status 7 (no billable procedures): {analysis['cases_to_relegate']}")
        
        if analysis['cases_to_relegate'] == 0:
            print("ℹ️  No cases need relegation. All cases have billable assistant surgeon procedures.")
            # Still save the analysis results
            results = {
                'dry_run': dry_run_mode,
                'timestamp': datetime.now().isoformat(),
                'total_cases_to_relegate': 0,
                'cases_successfully_relegated': 0,
                'cases_with_errors': 0,
                'relegated_cases': [],
                'error_cases': []
            }
        else:
            # Perform relegation
            print(f"\n🔄 Starting case relegation...")
            results = relegate_cases(conn, analysis['relegation_cases'], dry_run=dry_run_mode)
        
        # Save results
        print(f"\n💾 Saving results...")
        filename = save_results(analysis, results, args.format)
        
        # Final summary
        print(f"\n" + "="*80)
        print("FINAL SUMMARY")
        print("="*80)
        print(f"Mode: {'DRY RUN' if dry_run_mode else 'LIVE EXECUTION'}")
        print(f"Total cases in status 10: {analysis['total_cases']}")
        print(f"Cases staying status 10: {analysis['cases_staying_status_10']}")
        print(f"Cases relegated to status 7: {results['cases_successfully_relegated']}")
        print(f"Cases with errors: {results['cases_with_errors']}")
        print(f"Results file: {filename}")
        
        if dry_run_mode and results['total_cases_to_relegate'] > 0:
            print(f"\n⚠️  {results['total_cases_to_relegate']} cases would be relegated to status 7")
            print("⚠️  Review the results file before running in --live mode")
        elif not dry_run_mode and results['cases_successfully_relegated'] > 0:
            print(f"\n✅ Database changes have been committed")
            print(f"✅ {results['cases_successfully_relegated']} cases were relegated to status 7 for review")
        
        return True
        
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        return False
        
    finally:
        # Always close the database connection
        if conn:
            close_db_connection(conn)
            print(f"\n🔌 Database connection closed")

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
