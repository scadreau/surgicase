# Pay Amount Calculation Documentation

## Overview

The pay amount calculation functionality automatically calculates and updates the `pay_amount` field in the `cases` table based on the procedure codes associated with each case.

## How It Works

### 1. Trigger Points
The pay amount calculation is automatically triggered during:
- **Case Creation**: When a new case is created with procedure codes
- **Case Update**: When procedure codes are updated for an existing case

### 2. Calculation Logic

1. **Check for Procedure Codes**: The system first checks if the case has any procedure codes in the `case_procedure_codes` table
2. **No Procedure Codes**: If no procedure codes are found, the pay amount is set to `0.00`
3. **With Procedure Codes**: If procedure codes exist:
   - Query the `procedure_codes` table for `code_pay_amount` values
   - Filter by `user_id` and the case's procedure codes
   - Take the **maximum** `code_pay_amount` value
   - Update the case's `pay_amount` field with this value

### 3. Error Handling

- **Missing Procedure Codes**: If procedure codes exist in `case_procedure_codes` but no matching records are found in the `procedure_codes` table, an error is logged
- **Database Errors**: Any database errors are caught and logged
- **Non-blocking**: Pay amount calculation errors do not prevent case creation/update from succeeding

## Database Tables Involved

### `cases` Table
- `pay_amount` (decimal(14,2)): The calculated pay amount for the case

### `case_procedure_codes` Table
- `case_id` (varchar(100)): Links to the case
- `procedure_code` (varchar(10)): The procedure code

### `procedure_codes` Table
- `procedure_code` (varchar(10)): The procedure code
- `user_id` (varchar(64)): The user who owns this procedure code
- `code_pay_amount` (decimal(10,2)): The pay amount for this procedure code

## API Response Changes

### Create Case Response
```json
{
  "message": "Case and procedure codes created successfully",
  "user_id": "user123",
  "case_id": "case456",
  "procedure_codes": ["12345", "67890"],
  "status_update": { ... },
  "pay_amount_update": {
    "success": true,
    "pay_amount": "1500.00",
    "procedure_codes_found": 2,
    "message": "Successfully calculated pay amount from 2 procedure codes"
  }
}
```

### Update Case Response
```json
{
  "statusCode": 200,
  "body": {
    "message": "Case updated successfully",
    "case_id": "case456",
    "updated_fields": ["procedure_codes", "pay_amount"],
    "status_update": { ... },
    "pay_amount_update": {
      "success": true,
      "pay_amount": "2000.00",
      "procedure_codes_found": 3,
      "message": "Successfully updated pay_amount to 2000.00 for case case456"
    }
  }
}
```

## Implementation Details

### Files Modified
1. **`utils/pay_amount_calculator.py`** (new): Contains the calculation logic
2. **`endpoints/case/create_case.py`**: Integrated pay amount calculation
3. **`endpoints/case/update_case.py`**: Integrated pay amount calculation
4. **`tests/test_pay_amount_calculator.py`** (new): Unit tests for the functionality

### Key Functions

#### `calculate_case_pay_amount(case_id, user_id, conn)`
- Calculates the maximum pay amount for a case
- Returns a dictionary with success status, pay amount, and metadata

#### `update_case_pay_amount(case_id, user_id, conn)`
- Calculates and updates the pay amount in the database
- Returns the same result as `calculate_case_pay_amount` plus update status

## Testing

Run the pay amount calculator tests:
```bash
python tests/test_pay_amount_calculator.py
```

## Performance Considerations

- The calculation uses efficient SQL queries with `MAX()` function
- Designed for cases with 1-5 procedure codes (typical usage)
- All operations happen within existing database transactions
- Errors are logged but don't block the main operation

## Future Enhancements

- Support for tiered procedure codes (tier1-5 tables)
- Caching of frequently used pay amounts
- Batch processing for multiple cases
- Audit trail for pay amount changes 