# Log Request Endpoint Test Suite

This test suite provides comprehensive testing for the `/log_request` endpoint in the SurgiCase application.

## Overview

The test script (`test_log_request.py`) includes the following test scenarios:

1. **Valid Log Request** - Tests a complete log request with all fields and a comprehensive JSON payload
2. **Log Request with Error** - Tests logging requests that resulted in errors
3. **Minimal Fields Log Request** - Tests logging with only required fields
4. **Large Payload Log Request** - Tests handling of very large JSON payloads (1000+ records)
5. **Special Characters Log Request** - Tests handling of special characters, unicode, and potential injection attempts
6. **Performance Test** - Tests multiple concurrent requests to check performance
7. **Invalid Log Request** - Tests validation of required fields

## Prerequisites

1. Ensure your FastAPI server is running on `http://localhost:8000` (or update the `BASE_URL` in the test script)
2. Install the required dependencies:

```bash
# From the project root directory
pip install -r tests/test_requirements.txt

# Or from within the tests directory
cd tests
pip install -r test_requirements.txt
```

## Running the Tests

### Run All Tests
```bash
# From the project root directory
python tests/test_log_request.py

# Or from within the tests directory
cd tests
python test_log_request.py
```

### Run Individual Tests
You can modify the `main()` function in the test script to run only specific tests by commenting out the tests you don't want to run.

## Test Data

The test script includes realistic test data that covers:

- **Medical case data** with patient information, procedure codes, and file attachments
- **Query parameters** for filtering and pagination
- **Response payloads** with success/error scenarios
- **Special characters** including unicode, SQL injection attempts, and XSS attempts
- **Large datasets** with 1000+ records to test performance

## Expected Results

### Successful Tests
- Valid log requests should return HTTP 200
- All required fields should be properly validated
- Large payloads should be handled without errors
- Special characters should be properly escaped/stored

### Validation Tests
- Missing required fields should return HTTP 422 (Validation Error)
- Invalid data types should be rejected

## Configuration

### Update Server URL
If your server is running on a different URL, update the `BASE_URL` variable in the test script:

```python
BASE_URL = "http://your-server-url:port"
```

### Database Requirements
Ensure your database has the `request_logs` table with the following schema:

```sql
CREATE TABLE request_logs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    timestamp DATETIME,
    user_id VARCHAR(255),
    endpoint VARCHAR(500),
    method VARCHAR(10),
    request_payload TEXT,
    query_params TEXT,
    response_status INT,
    response_payload TEXT,
    execution_time_ms INT,
    error_message TEXT,
    client_ip VARCHAR(45)
);
```

## Test Output

The test script provides detailed output including:

- Individual test results with status codes and responses
- Performance metrics for bulk operations
- Summary of all test results
- Clear pass/fail indicators

## Troubleshooting

### Common Issues

1. **Connection Refused**: Ensure your FastAPI server is running
2. **Validation Errors**: Check that your database schema matches the expected structure
3. **Timeout Errors**: Large payload tests may take longer; adjust timeout settings if needed

### Debug Mode
To see more detailed output, you can add debug prints to individual test functions or modify the error handling to show more information.

## Security Considerations

The test script includes tests for:
- SQL injection attempts
- XSS attempts
- Special character handling
- Large payload validation

These tests help ensure your logging endpoint is secure and robust.

## Performance Notes

- The large payload test creates 1000 records and may take several seconds
- The performance test runs 10 concurrent requests
- Monitor your database performance during these tests
- Consider adjusting the number of records in large payload tests based on your system capabilities 