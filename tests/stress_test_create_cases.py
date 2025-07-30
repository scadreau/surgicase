# Created: 2025-07-30 05:29:18
# Last Modified: 2025-07-30 06:22:06
# Author: Scott Cadreau

"""
Stress test script for creating cases in the SurgiCase API.
This script creates multiple cases with the specified test data and logs
all case IDs for later deletion testing.
"""

import argparse
import json
import time
import requests
import sys
from datetime import datetime
from typing import List, Dict, Any


def get_millisecond_timestamp() -> int:
    """Get current timestamp in milliseconds."""
    return int(time.time() * 1000)


def generate_case_id(user_id: str) -> str:
    """Generate case ID using the format: user_id_<ms_timestamp>."""
    timestamp = get_millisecond_timestamp()
    return f"{user_id}_{timestamp}"


def create_case_payload(user_id: str) -> Dict[str, Any]:
    """
    Create the case payload with specified test data.
    
    Args:
        user_id: The user ID to use for the case
        
    Returns:
        Dictionary containing the case data
    """
    case_id = generate_case_id(user_id)
    
    payload = {
        "user_id": user_id,
        "case_id": case_id,
        "case_date": "2025-01-01",
        "surgeon_id": "100059",
        "facility_id": "1000046",
        "patient": {
            "first": "Johnathan",
            "last": "Thompson",
            "ins_provider": "UHC Individual Exchange"
        },
        "demo_file": None,
        "note_file": None,
        "misc_file": None,
        "procedure_codes": ["63047"]
    }
    
    return payload


def create_single_case(api_url: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create a single case via API call.
    
    Args:
        api_url: The API endpoint URL
        payload: The case data payload
        
    Returns:
        Dictionary containing success status, response data, and timing info
    """
    start_time = time.time()
    
    try:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        
        response = requests.post(
            api_url,
            json=payload,
            headers=headers,
            timeout=30
        )
        
        end_time = time.time()
        execution_time = (end_time - start_time) * 1000  # Convert to milliseconds
        
        result = {
            "success": response.status_code in [200, 201],
            "case_id": payload["case_id"],
            "status_code": response.status_code,
            "execution_time_ms": round(execution_time, 2),
            "timestamp": datetime.now().isoformat()
        }
        
        if result["success"]:
            result["response"] = response.json()
        else:
            result["error"] = response.text
            
        return result
        
    except requests.exceptions.RequestException as e:
        end_time = time.time()
        execution_time = (end_time - start_time) * 1000
        
        return {
            "success": False,
            "case_id": payload["case_id"],
            "status_code": None,
            "execution_time_ms": round(execution_time, 2),
            "timestamp": datetime.now().isoformat(),
            "error": str(e)
        }


def save_results_to_file(results: List[Dict[str, Any]], filename: str) -> None:
    """
    Save test results to a JSON file.
    
    Args:
        results: List of test results
        filename: Output filename
    """
    # Extract successful case IDs for easy access
    successful_case_ids = [
        result["case_id"] for result in results 
        if result["success"]
    ]
    
    # Calculate average response time for successful requests
    if successful_case_ids:
        avg_response_time = sum(
            r["execution_time_ms"] for r in results if r["success"]
        ) / len(successful_case_ids)
    else:
        avg_response_time = 0
    
    output_data = {
        "test_run_timestamp": datetime.now().isoformat(),
        "total_cases_attempted": len(results),
        "successful_cases": len(successful_case_ids),
        "failed_cases": len(results) - len(successful_case_ids),
        "average_response_time_ms": round(avg_response_time, 2),
        "successful_case_ids": successful_case_ids,
        "detailed_results": results
    }
    
    with open(filename, 'w') as f:
        json.dump(output_data, f, indent=2)
    
    print(f"\nResults saved to: {filename}")
    print(f"Successful case IDs saved for deletion testing: {len(successful_case_ids)} cases")


def print_summary(results: List[Dict[str, Any]]) -> None:
    """
    Print a summary of the test results.
    
    Args:
        results: List of test results
    """
    total_cases = len(results)
    successful_cases = sum(1 for r in results if r["success"])
    failed_cases = total_cases - successful_cases
    
    if successful_cases > 0:
        avg_response_time = sum(
            r["execution_time_ms"] for r in results if r["success"]
        ) / successful_cases
    else:
        avg_response_time = 0
    
    print(f"\n{'='*60}")
    print("STRESS TEST SUMMARY")
    print(f"{'='*60}")
    print(f"Total cases attempted: {total_cases}")
    print(f"Successful cases: {successful_cases}")
    print(f"Failed cases: {failed_cases}")
    print(f"Success rate: {(successful_cases/total_cases)*100:.1f}%")
    print(f"Average response time: {avg_response_time:.2f}ms")
    
    if failed_cases > 0:
        print(f"\nFailed case details:")
        for result in results:
            if not result["success"]:
                print(f"  Case ID: {result['case_id']}")
                print(f"  Status Code: {result['status_code']}")
                print(f"  Error: {result.get('error', 'Unknown error')}")


def main():
    """Main function to run the stress test."""
    parser = argparse.ArgumentParser(
        description="Stress test script for creating cases in SurgiCase API"
    )
    parser.add_argument(
        "--count",
        type=int,
        required=True,
        help="Number of cases to create"
    )
    parser.add_argument(
        "--output",
        type=str,
        default="stress_test_results.json",
        help="Output file for test results (default: stress_test_results.json)"
    )
    parser.add_argument(
        "--useaws",
        action="store_true",
        help="Use AWS API Gateway instead of direct server (default: direct server)"
    )
    
    args = parser.parse_args()
    
    if args.count <= 0:
        print("Error: --count must be a positive integer")
        sys.exit(1)
    
    # Configuration
    USER_ID = "04e884e8-4011-70e9-f3bd-d89fabd15c7b"
    
    if args.useaws:
        API_BASE_URL = "https://k4fr1uz3h1.execute-api.us-east-1.amazonaws.com/v1"
        endpoint_type = "AWS API Gateway"
    else:
        API_BASE_URL = "https://allstarsapi1.metoraymedical.com"
        endpoint_type = "Direct Server"
        
    API_ENDPOINT = f"{API_BASE_URL}/case"
    
    print(f"Starting stress test...")
    print(f"Endpoint Type: {endpoint_type}")
    print(f"Target URL: {API_ENDPOINT}")
    print(f"Number of cases to create: {args.count}")
    print(f"User ID: {USER_ID}")
    print(f"Results will be saved to: {args.output}")
    print(f"{'='*60}")
    
    results = []
    start_total_time = time.time()
    
    for i in range(args.count):
        print(f"Creating case {i+1}/{args.count}...", end=" ", flush=True)
        
        # Generate case payload
        payload = create_case_payload(USER_ID)
        
        # Create the case
        result = create_single_case(API_ENDPOINT, payload)
        results.append(result)
        
        # Print immediate feedback
        if result["success"]:
            print(f"✓ Success ({result['execution_time_ms']:.0f}ms)")
        else:
            print(f"✗ Failed - {result.get('error', 'Unknown error')}")
        
        # Small delay to avoid overwhelming the server
        time.sleep(0.01)
    
    end_total_time = time.time()
    total_execution_time = (end_total_time - start_total_time)
    
    print(f"\nTotal execution time: {total_execution_time:.2f} seconds")
    
    # Print summary
    print_summary(results)
    
    # Save results to file
    save_results_to_file(results, args.output)
    
    print(f"\nStress test completed!")


if __name__ == "__main__":
    main()