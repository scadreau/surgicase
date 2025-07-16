# Pay Amount Calculation Documentation

## Overview

The pay amount calculation functionality automatically calculates and updates the `pay_amount` field in the `cases` table based on the procedure codes associated with each case. The system now uses a **tier-based approach** where pay amounts are determined by the user's tier level.

## How It Works

### 1. Trigger Points
The pay amount calculation is automatically triggered during:
- **Case Creation**: When a new case is created with procedure codes
- **Case Update**: When procedure codes are updated for an existing case

### 2. Calculation Logic

1. **Get User Tier**: The system first retrieves the user's `user_tier` from the `user_profile` table
2. **Check for Procedure Codes**: The system checks if the case has any procedure codes in the `case_procedure_codes` table
3. **No Procedure Codes**: If no procedure codes are found, the pay amount is set to `0.00`
4. **With Procedure Codes**: If procedure codes exist:
   - Query the `procedure_codes` table for `code_pay_amount` values
   - Filter by `tier` (user's tier) and the case's procedure codes
   - Take the **maximum** `code_pay_amount` value
   - Update the case's `pay_amount` field with this value

### 3. Error Handling

- **User Not Found**: If the user doesn't exist or is inactive, an error is returned
- **Missing Procedure Codes**: If procedure codes exist in `case_procedure_codes` but no matching records are found in the `procedure_codes` table for the user's tier, an error is logged
- **Database Errors**: Any database errors are caught and logged
- **Non-blocking**: Pay amount calculation errors do not prevent case creation/update from succeeding

## Database Tables Involved

### `cases` Table
- `pay_amount` (decimal(14,2)): The calculated pay amount for the case

### `case_procedure_codes` Table
- `case_id` (varchar(100)): Links to the case
- `procedure_code` (varchar(10)): The procedure code

### `user_profile` Table
- `user_id` (varchar(100)): The user ID
- `user_tier` (int): The user's tier level (default: 1)

### `procedure_codes` Table
- `procedure_code` (varchar(10)): The procedure code
- `procedure_desc` (varchar(1000)): Description of the procedure
- `code_category` (varchar(20)): Category of the procedure code
- `code_status` (varchar(20)): Status of the procedure code
- `code_pay_amount` (decimal(10,2)): The pay amount for this procedure code
- `tier` (int): The tier level this procedure code belongs to

### Tier Tables (Source Data)
- `procedure_codes_tier1`, `procedure_codes_tier2`, etc.: Source tables containing tier-specific procedure codes

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
    "message": "Successfully calculated pay amount from 2 procedure codes (tier 1)"
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
1. **`utils/pay_amount_calculator.py`**: Updated to use tier-based lookup
2. **`utils/user_procedure_codes.py`** (new): Utilities for managing user procedure codes and tiers
3. **`endpoints/case/create_case.py`**: Integrated pay amount calculation
4. **`endpoints/case/update_case.py`**: Integrated pay amount calculation
5. **`tests/test_pay_amount_calculator.py`**: Updated tests for tier-based approach
6. **`tests/test_user_procedure_codes.py`** (new): Tests for user procedure code utilities
7. **`migrate_procedure_codes.py`** (new): Migration script for populating procedure_codes table

### Key Functions

#### `calculate_case_pay_amount(case_id, user_id, conn)`
- Gets the user's tier from `user_profile`
- Calculates the maximum pay amount for a case based on user's tier
- Returns a dictionary with success status, pay amount, and metadata

#### `update_case_pay_amount(case_id, user_id, conn)`
- Calculates and updates the pay amount in the database
- Returns the same result as `calculate_case_pay_amount` plus update status

#### `populate_procedure_codes_from_tiers(conn, max_tier)`
- Populates the `procedure_codes` table from tier tables
- Should be run once during migration

#### `get_user_procedure_codes(user_id, conn)`
- Gets all procedure codes available for a user based on their tier

#### `update_user_tier(user_id, new_tier, conn)`
- Updates a user's tier level

## Migration Process

### 1. Database Schema Changes
The `procedure_codes` table has been updated to include a `tier` field:
```sql
ALTER TABLE procedure_codes 
ADD COLUMN tier INT NOT NULL DEFAULT 1;
```

### 2. Data Migration
Run the migration script to populate the `procedure_codes` table:
```bash
python migrate_procedure_codes.py
```

### 3. Verification
After migration, verify that:
- All tier tables have been processed
- Procedure codes are correctly associated with tiers
- Pay amount calculations work with the new structure

## Testing

Run the pay amount calculator tests:
```bash
python tests/test_pay_amount_calculator.py
```

Run the user procedure codes tests:
```bash
python tests/test_user_procedure_codes.py
```

## Performance Considerations

- The calculation uses efficient SQL queries with `MAX()` function
- Tier-based filtering reduces the search space
- Designed for cases with 1-5 procedure codes (typical usage)
- All operations happen within existing database transactions
- Errors are logged but don't block the main operation

## Tier System Benefits

1. **Scalability**: Single `procedure_codes` table regardless of user count
2. **Efficiency**: No data duplication across users
3. **Flexibility**: Easy to add new tiers or modify existing ones
4. **Performance**: Faster queries with proper indexing on `tier` and `procedure_code`
5. **Maintainability**: Tier tables remain the source of truth

## Future Enhancements

- Support for dynamic tier creation
- Caching of frequently used pay amounts by tier
- Batch processing for multiple cases
- Audit trail for pay amount changes
- Tier-based analytics and reporting 