# Created: 2025-07-27 02:34:55
# Last Modified: 2025-07-27 02:34:56
# Author: Scott Cadreau

# Quick test for case_dashboard_data endpoint
import requests
import json

def test_dashboard_endpoint():
    """
    Test the case_dashboard_data endpoint with no date filters
    """
    # Endpoint URL (assuming FastAPI is running on localhost:8000)
    url = "http://localhost:8000/case_dashboard_data"
    
    # Parameters
    params = {
        "user_id": "64180458-6071-7031-c9e5-26ea8ce1434b"
        # No start_date or end_date - testing without date filters
    }
    
    try:
        print("Testing case_dashboard_data endpoint...")
        print(f"URL: {url}")
        print(f"Parameters: {params}")
        print("-" * 50)
        
        # Make the request
        response = requests.get(url, params=params)
        
        print(f"Status Code: {response.status_code}")
        print("-" * 50)
        
        if response.status_code == 200:
            # Parse and pretty print the JSON response
            data = response.json()
            print("Response Data:")
            print(json.dumps(data, indent=2))
            
            # Print summary information
            print("\n" + "=" * 50)
            print("DASHBOARD SUMMARY:")
            print("=" * 50)
            
            if "dashboard_data" in data:
                for item in data["dashboard_data"]:
                    print(f"Status {item['case_status']} ({item['case_status_desc']}): "
                          f"{item['cases']} cases, ${item['total_amount']:,.2f}")
            
            if "summary" in data:
                summary = data["summary"]
                print(f"\nTOTAL: {summary['total_cases']} cases, ${summary['total_amount']:,.2f}")
                
        else:
            print("Error Response:")
            print(response.text)
            
    except requests.exceptions.ConnectionError:
        print("ERROR: Could not connect to the API server.")
        print("Make sure the FastAPI server is running on localhost:8000")
        print("You can start it with: python main.py")
    except Exception as e:
        print(f"ERROR: {str(e)}")

if __name__ == "__main__":
    test_dashboard_endpoint() 