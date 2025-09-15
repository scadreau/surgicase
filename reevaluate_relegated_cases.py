#!/usr/bin/env python3
# Created: 2025-09-15 01:59:45
# Last Modified: 2025-09-15 02:04:20
# Author: Scott Cadreau

"""
Re-evaluate Relegated Cases Script - After Procedure Code Corrections

This script:
1. Loads the 22 cases that were previously relegated to status 7
2. Re-evaluates them using the update_case_status() function
3. Expected outcome: Cases should move back to status 10 due to corrected procedure codes
4. Provides detailed reporting on status changes

Background:
- 22 cases were relegated from status 10 to status 7 due to no billable assistant surgeon procedures
- Root cause: Providers using 59510 (C-section full care) instead of 59514 (C-section surgical only)
- Solution: Database updated to use 59514 which has asst_surg = 2 (billable)
- This script re-evaluates those cases to move them back to status 10

Usage:
    python reevaluate_relegated_cases.py --dry-run    # Safe preview mode
    python reevaluate_relegated_cases.py --live       # Execute changes
"""

import sys
import os
import json
import argparse
from datetime import datetime
from typing import List, Dict, Any

# Add the project root to the path so we can import modules
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from core.database import get_db_connection, close_db_connection
from utils.case_status import update_case_status

def load_relegated_cases(json_file_path: str) -> List[Dict[str, Any]]:
    """
    Load the list of cases that were previously relegated from the JSON results file
    
    Args:
        json_file_path: Path to the relegation results JSON file
        
    Returns:
        List of case dictionaries that were relegated
    """
    try:
        with open(json_file_path, 'r') as f:
            results = json.load(f)
        
        # Extract the relegated cases from the results
        relegated_cases = results.get('relegation_results', {}).get('relegated_cases', [])
        
        if not relegated_cases:
            raise Exception("No relegated cases found in the JSON file")
        
        print(f"✅ Loaded {len(relegated_cases)} cases from {json_file_path}")
        return relegated_cases
        
    except FileNotFoundError:
        raise Exception(f"JSON file not found: {json_file_path}")
    except json.JSONDecodeError:
        raise Exception(f"Invalid JSON format in file: {json_file_path}")
    except Exception as e:
        raise Exception(f"Error loading relegated cases: {str(e)}")

def get_current_case_status(conn, case_ids: List[str]) -> Dict[str, Dict[str, Any]]:
    """
    Get current status and procedure code information for the specified cases
    
    Args:
        conn: Database connection
        case_ids: List of case IDs to check
        
    Returns:
        Dict mapping case_id to current case information
    """
    try:
        case_info = {}
        
        with conn.cursor() as cursor:
            # Get current case status and procedure codes for each case
            for case_id in case_ids:
                # Get case status
                cursor.execute("""
                    SELECT case_id, case_status, patient_first, patient_last, case_date
                    FROM cases 
                    WHERE case_id = %s AND active = 1
                """, (case_id,))
                case_data = cursor.fetchone()
                
                if case_data:
                    # Get procedure codes and their asst_surg values
                    cursor.execute("""
                        SELECT procedure_code, asst_surg
                        FROM case_procedure_codes 
                        WHERE case_id = %s
                        ORDER BY procedure_code
                    """, (case_id,))
                    procedures = cursor.fetchall()
                    
                    # Count billable procedures
                    billable_count = sum(1 for proc in procedures if proc['asst_surg'] == 2)
                    
                    case_info[case_id] = {
                        'case_id': case_data['case_id'],
                        'current_status': case_data['case_status'],
                        'patient_first': case_data['patient_first'],
                        'patient_last': case_data['patient_last'],
                        'case_date': case_data['case_date'].isoformat() if case_data['case_date'] else None,
                        'procedures': [{'code': p['procedure_code'], 'asst_surg': p['asst_surg']} for p in procedures],
                        'billable_procedures': billable_count
                    }
                else:
                    case_info[case_id] = {
                        'case_id': case_id,
                        'error': 'Case not found or inactive'
                    }
        
        return case_info
        
    except Exception as e:
        raise Exception(f"Error getting current case status: {str(e)}")

def reevaluate_cases(conn, relegated_cases: List[Dict[str, Any]], dry_run: bool = True) -> Dict[str, Any]:
    """
    Re-evaluate the relegated cases using update_case_status function
    
    Args:
        conn: Database connection
        relegated_cases: List of cases that were previously relegated
        dry_run: If True, don't make actual changes
        
    Returns:
        Dict with results
    """
    results = {
        'dry_run': dry_run,
        'timestamp': datetime.now().isoformat(),
        'total_cases_evaluated': len(relegated_cases),
        'cases_moved_to_status_10': 0,
        'cases_remaining_status_7': 0,
        'cases_with_errors': 0,
        'status_changes': [],
        'error_cases': []
    }
    
    case_ids = [case['case_id'] for case in relegated_cases]
    
    print(f"\n{'DRY RUN MODE' if dry_run else 'LIVE MODE'} - Re-evaluating {len(case_ids)} cases...")
    
    try:
        # Get current status of all cases before re-evaluation
        print("📊 Getting current case status...")
        current_info = get_current_case_status(conn, case_ids)
        
        if not dry_run:
            # Start transaction for live mode
            conn.begin()
        
        for i, case in enumerate(relegated_cases, 1):
            case_id = case['case_id']
            
            try:
                # Print progress every 5 cases
                if i % 5 == 0 or i == len(relegated_cases):
                    print(f"Progress: {i}/{len(relegated_cases)} cases processed...")
                
                current_case = current_info.get(case_id, {})
                
                if 'error' in current_case:
                    results['error_cases'].append({
                        **case,
                        'error': current_case['error']
                    })
                    results['cases_with_errors'] += 1
                    continue
                
                original_status = current_case['current_status']
                
                if dry_run:
                    # For dry run, simulate what would happen
                    billable_count = current_case['billable_procedures']
                    
                    if billable_count > 0:
                        # Would move to status 10
                        predicted_status = 10
                        results['cases_moved_to_status_10'] += 1
                    else:
                        # Would stay at status 7
                        predicted_status = 7
                        results['cases_remaining_status_7'] += 1
                    
                    results['status_changes'].append({
                        **case,
                        'current_status': original_status,
                        'predicted_new_status': predicted_status,
                        'billable_procedures': billable_count,
                        'procedures': current_case['procedures'],
                        'action': f'Would change from status {original_status} to {predicted_status}' if original_status != predicted_status else f'Would remain at status {original_status}'
                    })
                
                else:
                    # Live mode - actually call update_case_status
                    status_result = update_case_status(case_id, conn)
                    
                    if status_result['success']:
                        new_status = status_result.get('case_status', original_status)
                        
                        if new_status == 10:
                            results['cases_moved_to_status_10'] += 1
                        elif new_status == 7:
                            results['cases_remaining_status_7'] += 1
                        
                        results['status_changes'].append({
                            **case,
                            'original_status': original_status,
                            'new_status': new_status,
                            'billable_procedures': status_result.get('billable_procedures', current_case['billable_procedures']),
                            'procedures': current_case['procedures'],
                            'status_result': status_result,
                            'action': f'Changed from status {original_status} to {new_status}' if original_status != new_status else f'Remained at status {original_status}'
                        })
                    else:
                        results['error_cases'].append({
                            **case,
                            'error': status_result.get('message', 'Unknown error'),
                            'status_result': status_result
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
        print(f"  Cases evaluated: {results['total_cases_evaluated']}")
        print(f"  Cases moved to status 10: {results['cases_moved_to_status_10']}")
        print(f"  Cases remaining at status 7: {results['cases_remaining_status_7']}")
        print(f"  Cases with errors: {results['cases_with_errors']}")
        
        return results
        
    except Exception as e:
        if not dry_run:
            try:
                conn.rollback()
                print(f"\n❌ ROLLED BACK transaction due to error")
            except:
                pass
        raise Exception(f"Error during case re-evaluation: {str(e)}")

def save_results(results: Dict[str, Any], output_format: str = 'json'):
    """
    Save results to file for review
    
    Args:
        results: Results dictionary from reevaluate_cases
        output_format: 'json' or 'csv'
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    mode = "dry_run" if results['dry_run'] else "live"
    
    filename = f"case_reevaluation_{mode}_{timestamp}.json"
    with open(filename, 'w') as f:
        json.dump(results, f, indent=2)
    print(f"\n📄 Results saved to: {filename}")
    
    return filename

def main():
    """Main function to handle command line arguments and orchestrate the re-evaluation process"""
    
    parser = argparse.ArgumentParser(
        description='Re-evaluate cases that were previously relegated to status 7 after procedure code corrections',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --dry-run                    # Preview changes without executing
  %(prog)s --live                       # Execute changes to database
  %(prog)s --live --force               # Execute without confirmation prompt
        """
    )
    
    parser.add_argument('--dry-run', action='store_true',
                       help='Preview mode - show what would change without making database changes')
    parser.add_argument('--live', action='store_true',
                       help='Live mode - execute actual database changes')
    parser.add_argument('--force', action='store_true',
                       help='Skip confirmation prompt in live mode')
    parser.add_argument('--json-file', default='case_relegation_live_20250914_094053.json',
                       help='Path to the JSON file containing relegated cases (default: case_relegation_live_20250914_094053.json)')
    
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
    print("CASE RE-EVALUATION SCRIPT - After Procedure Code Corrections")
    print("="*80)
    print(f"Mode: {'DRY RUN (safe preview)' if dry_run_mode else 'LIVE (will modify database)'}")
    print(f"Target: Cases previously relegated to status 7")
    print(f"Expected: Cases should move back to status 10 due to corrected procedure codes")
    print(f"Source: {args.json_file}")
    print("="*80)
    
    if not dry_run_mode and not args.force:
        print("\n⚠️  WARNING: LIVE MODE WILL MODIFY PRODUCTION DATABASE")
        confirmation = input("\nType 'CONFIRM' to proceed with live changes: ")
        if confirmation != 'CONFIRM':
            print("❌ Operation cancelled")
            return False
    elif not dry_run_mode and args.force:
        print("\n⚠️  WARNING: LIVE MODE WITH --force FLAG")
        print("⚠️  Skipping confirmation prompt - proceeding with database changes")
    
    conn = None
    try:
        # Load the relegated cases from JSON file
        print(f"\n📋 Loading relegated cases from {args.json_file}...")
        relegated_cases = load_relegated_cases(args.json_file)
        
        # Get database connection
        print(f"\n🔌 Connecting to database...")
        conn = get_db_connection()
        print("✅ Database connection established")
        
        # Re-evaluate cases
        print(f"\n🔄 Starting case re-evaluation...")
        results = reevaluate_cases(conn, relegated_cases, dry_run=dry_run_mode)
        
        # Save results
        print(f"\n💾 Saving results...")
        filename = save_results(results)
        
        # Final summary
        print(f"\n" + "="*80)
        print("FINAL SUMMARY")
        print("="*80)
        print(f"Mode: {'DRY RUN' if dry_run_mode else 'LIVE EXECUTION'}")
        print(f"Cases evaluated: {results['total_cases_evaluated']}")
        print(f"Cases moved to status 10: {results['cases_moved_to_status_10']}")
        print(f"Cases remaining at status 7: {results['cases_remaining_status_7']}")
        print(f"Cases with errors: {results['cases_with_errors']}")
        print(f"Results file: {filename}")
        
        if dry_run_mode:
            if results['cases_moved_to_status_10'] > 0:
                print(f"\n✅ {results['cases_moved_to_status_10']} cases would be moved back to status 10")
            if results['cases_remaining_status_7'] > 0:
                print(f"⚠️  {results['cases_remaining_status_7']} cases would remain at status 7")
            print("⚠️  Review the results file before running in --live mode")
        elif not dry_run_mode:
            print(f"\n✅ Database changes have been committed")
            if results['cases_moved_to_status_10'] > 0:
                print(f"✅ {results['cases_moved_to_status_10']} cases moved back to status 10 (ready for payment)")
            if results['cases_remaining_status_7'] > 0:
                print(f"⚠️  {results['cases_remaining_status_7']} cases remain at status 7 (may need further review)")
        
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
