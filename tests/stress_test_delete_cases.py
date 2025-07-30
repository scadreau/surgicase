# Created: 2025-07-30 05:33:42
# Last Modified: 2025-07-30 06:09:16
# Author: Scott Cadreau

"""
Stress test script for deleting cases in the SurgiCase API.
This script reads case IDs from a JSON file (created by the create stress test)
and deletes each case, tracking performance and success rates.
"""

import argparse
import json
import time
import requests
import sys
import os
from datetime import datetime
from typing import List, Dict, Any


def load_case_ids_from_file(filename: str) -> List[str]:
    """
    Load case IDs from the JSON results file.
    
    Args:
        filename: Path to the JSON results file from create stress test
        
    Returns:
        List of case IDs to delete
        
    Raises:
        FileNotFoundError: If the input file doesn't exist
        ValueError: If the file format is invalid
    """
    if not os.path.exists(filename):
        raise FileNotFoundError(f"Input file not found: {filename}")
    
    try:
        with open(filename, 'r') as f:
            data = json.load(f)
        
        # Extract case IDs from the successful_case_ids list
        if "successful_case_ids" not in data:
            raise ValueError("No 'successful_case_ids' found in input file")
        
        case_ids = data["successful_case_ids"]
        
        if not isinstance(case_ids, list):
            raise ValueError("'successful_case_ids' must be a list")
        
        if not case_ids:
            raise ValueError("No case IDs found in input file")
        
        return case_ids
        
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON format in input file: {e}")


def delete_single_case(api_url: str, case_id: str) -> Dict[str, Any]:
    """
    Delete a single case via API call.
    
    Args:
        api_url: The API base URL
        case_id: The case ID to delete
        
    Returns:
        Dictionary containing success status, response data, and timing info
    """
    start_time = time.time()
    
    try:
        headers = {
            "Accept": "application/json"
        }
        
        # The delete endpoint expects case_id as a query parameter
        delete_url = f"{api_url}/case"
        params = {"case_id": case_id}
        
        response = requests.delete(
            delete_url,
            params=params,
            headers=headers,
            timeout=30
        )
        
        end_time = time.time()
        execution_time = (end_time - start_time) * 1000  # Convert to milliseconds
        
        result = {
            "success": response.status_code in [200, 201],
            "case_id": case_id,
            "status_code": response.status_code,
            "execution_time_ms": round(execution_time, 2),
            "timestamp": datetime.now().isoformat()
        }
        
        if result["success"]:
            try:
                result["response"] = response.json()
            except json.JSONDecodeError:
                # Some successful responses might not be JSON
                result["response"] = {"raw_response": response.text}
        else:
            result["error"] = response.text
            
        return result
        
    except requests.exceptions.RequestException as e:
        end_time = time.time()
        execution_time = (end_time - start_time) * 1000
        
        return {
            "success": False,
            "case_id": case_id,
            "status_code": None,
            "execution_time_ms": round(execution_time, 2),
            "timestamp": datetime.now().isoformat(),
            "error": str(e)
        }


def save_delete_results_to_file(results: List[Dict[str, Any]], input_filename: str, output_filename: str) -> None:
    """
    Save delete test results to a JSON file.
    
    Args:
        results: List of delete test results
        input_filename: Name of the input file used
        output_filename: Output filename for results
    """
    # Extract successful and failed case IDs
    successful_deletions = [
        result["case_id"] for result in results 
        if result["success"]
    ]
    
    failed_deletions = [
        {
            "case_id": result["case_id"],
            "error": result.get("error", "Unknown error"),
            "status_code": result.get("status_code")
        }
        for result in results 
        if not result["success"]
    ]
    
    # Calculate average response time for successful deletions
    if successful_deletions:
        avg_response_time = sum(
            r["execution_time_ms"] for r in results if r["success"]
        ) / len(successful_deletions)
    else:
        avg_response_time = 0
    
    output_data = {
        "delete_test_run_timestamp": datetime.now().isoformat(),
        "input_file_used": input_filename,
        "total_cases_attempted": len(results),
        "successful_deletions": len(successful_deletions),
        "failed_deletions": len(failed_deletions),
        "average_response_time_ms": round(avg_response_time, 2),
        "successful_deleted_case_ids": successful_deletions,
        "failed_deletion_details": failed_deletions,
        "detailed_results": results
    }
    
    with open(output_filename, 'w') as f:
        json.dump(output_data, f, indent=2)
    
    print(f"\nDelete test results saved to: {output_filename}")
    print(f"Successfully deleted: {len(successful_deletions)} cases")
    print(f"Failed to delete: {len(failed_deletions)} cases")


def print_delete_summary(results: List[Dict[str, Any]]) -> None:
    """
    Print a summary of the delete test results.
    
    Args:
        results: List of delete test results
    """
    total_cases = len(results)
    successful_deletions = sum(1 for r in results if r["success"])
    failed_deletions = total_cases - successful_deletions
    
    if successful_deletions > 0:
        avg_response_time = sum(
            r["execution_time_ms"] for r in results if r["success"]
        ) / successful_deletions
    else:
        avg_response_time = 0
    
    print(f"\n{'='*60}")
    print("DELETE STRESS TEST SUMMARY")
    print(f"{'='*60}")
    print(f"Total cases attempted: {total_cases}")
    print(f"Successful deletions: {successful_deletions}")
    print(f"Failed deletions: {failed_deletions}")
    print(f"Success rate: {(successful_deletions/total_cases)*100:.1f}%")
    print(f"Average response time: {avg_response_time:.2f}ms")
    
    if failed_deletions > 0:
        print(f"\nFailed deletion details:")
        for result in results:
            if not result["success"]:
                print(f"  Case ID: {result['case_id']}")
                print(f"  Status Code: {result['status_code']}")
                print(f"  Error: {result.get('error', 'Unknown error')}")


def main():
    """Main function to run the delete stress test."""
    parser = argparse.ArgumentParser(
        description="Stress test script for deleting cases in SurgiCase API"
    )
    parser.add_argument(
        "--input",
        type=str,
        required=True,
        help="JSON file containing case IDs to delete (from create stress test)"
    )
    parser.add_argument(
        "--output",
        type=str,
        default="stress_test_delete_results.json",
        help="Output file for delete test results (default: stress_test_delete_results.json)"
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.1,
        help="Delay between delete requests in seconds (default: 0.1)"
    )
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Skip confirmation prompt (use with caution)"
    )
    parser.add_argument(
        "--useaws",
        action="store_true",
        help="Use AWS API Gateway instead of direct server (default: direct server)"
    )
    
    args = parser.parse_args()
    
    if args.delay < 0:
        print("Error: --delay must be non-negative")
        sys.exit(1)
    
    try:
        # Load case IDs from input file
        print(f"Loading case IDs from: {args.input}")
        case_ids = load_case_ids_from_file(args.input)
        print(f"Found {len(case_ids)} case IDs to delete")
        
    except (FileNotFoundError, ValueError) as e:
        print(f"Error loading input file: {e}")
        sys.exit(1)
    
    # Safety confirmation
    if not args.confirm:
        print(f"\n⚠️  WARNING: This will DELETE {len(case_ids)} cases!")
        print("This action cannot be undone.")
        response = input("Are you sure you want to continue? (yes/no): ").lower().strip()
        if response not in ['yes', 'y']:
            print("Delete operation cancelled.")
            sys.exit(0)
    
    # Configuration
    if args.useaws:
        API_BASE_URL = "https://k4fr1uz3h1.execute-api.us-east-1.amazonaws.com/v1"
        endpoint_type = "AWS API Gateway"
    else:
        API_BASE_URL = "https://allstarsapi1.metoraymedical.com"
        endpoint_type = "Direct Server"
    
    print(f"\nStarting delete stress test...")
    print(f"Endpoint Type: {endpoint_type}")
    print(f"Target URL: {API_BASE_URL}/case")
    print(f"Number of cases to delete: {len(case_ids)}")
    print(f"Delay between requests: {args.delay}s")
    print(f"Results will be saved to: {args.output}")
    print(f"{'='*60}")
    
    results = []
    start_total_time = time.time()
    
    for i, case_id in enumerate(case_ids):
        print(f"Deleting case {i+1}/{len(case_ids)} ({case_id})...", end=" ", flush=True)
        
        # Delete the case
        result = delete_single_case(API_BASE_URL, case_id)
        results.append(result)
        
        # Print immediate feedback
        if result["success"]:
            print(f"✓ Success ({result['execution_time_ms']:.0f}ms)")
        else:
            print(f"✗ Failed - {result.get('error', 'Unknown error')}")
        
        # Delay between requests
        if args.delay > 0:
            time.sleep(args.delay)
    
    end_total_time = time.time()
    total_execution_time = (end_total_time - start_total_time)
    
    print(f"\nTotal execution time: {total_execution_time:.2f} seconds")
    
    # Print summary
    print_delete_summary(results)
    
    # Save results to file
    save_delete_results_to_file(results, args.input, args.output)
    
    print(f"\nDelete stress test completed!")


if __name__ == "__main__":
    main()