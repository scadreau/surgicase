# QuickBooks Export for SurgiCase Provider Payment Data

## Overview

This module provides QuickBooks-compatible export functionality for the same data used in the Provider Payment Report. It uses functional programming principles and reuses the exact same data extraction logic as the existing provider payment report.

## Available Exports

### 1. Vendors CSV Export (`/quickbooks-vendors-csv`)
Exports providers as vendors that can be imported into QuickBooks.

**What it includes:**
- Provider names (properly formatted)
- NPI numbers as Tax IDs
- Provider IDs as Account Numbers
- Total payment amounts as Opening Balances
- Vendor setup ready for 1099 reporting

### 2. Transactions IIF Export (`/quickbooks-transactions-iif`)
Exports provider payments as bill transactions in QuickBooks' native IIF format.

**What it includes:**
- Each case as a separate bill transaction
- Medical Expenses account entries
- Accounts Payable entries
- Case details in memo fields
- Procedure codes in transaction details

## Usage

### Basic Export (All Data)
```bash
# Export all providers as vendors
GET /quickbooks-vendors-csv

# Export all payment transactions
GET /quickbooks-transactions-iif
```

### Filtered Exports
```bash
# Export for specific date range
GET /quickbooks-vendors-csv?start_date=2025-01-01&end_date=2025-01-31

# Export for specific provider
GET /quickbooks-transactions-iif?user_id=provider_123

# Combined filters
GET /quickbooks-vendors-csv?user_id=provider_123&start_date=2025-01-01&end_date=2025-01-31
```

## Data Source

The exports use exactly the same data as the Provider Payment Report:
- **Cases**: `case_status = 15` (completed/paid cases)
- **Providers**: Active providers from `user_profile` table
- **Procedure Codes**: From `case_procedure_codes` table
- **Payment Information**: `pay_amount` and `pay_category` from cases

## File Formats

### CSV Format (Vendors)
Standard CSV file with QuickBooks vendor import headers:
- `Name`, `Company`, `First Name`, `Last Name`
- `Vendor Type`, `Account Number`, `Tax ID`
- `Is Vendor Eligible For 1099`, `Terms`
- `Opening Balance`, `As Of Date`

### IIF Format (Transactions)
QuickBooks Intuit Interchange Format:
- Account definitions (Medical Expenses, Accounts Payable)
- Vendor definitions
- Bill transactions with split entries
- Proper double-entry bookkeeping format

## Import Instructions

### Importing Vendors to QuickBooks

1. **Download the vendors CSV file** from `/quickbooks-vendors-csv`
2. **In QuickBooks:**
   - Go to `File → Utilities → Import → Intuit Interchange Format (IIF)`
   - Or use `File → Import → Vendors` for CSV format
3. **Select the downloaded file**
4. **Review and import** the vendor data
5. **Verify** that vendors appear in your Vendor List

### Importing Transactions to QuickBooks

1. **Download the transactions IIF file** from `/quickbooks-transactions-iif`
2. **In QuickBooks:**
   - Go to `File → Utilities → Import → Intuit Interchange Format (IIF)`
3. **Select the downloaded IIF file**
4. **QuickBooks will automatically:**
   - Create the necessary accounts (Medical Expenses, Accounts Payable)
   - Import all vendor records
   - Import all bill transactions
5. **Review** the imported transactions in your Vendor Bills

## Account Structure

The IIF export creates this account structure in QuickBooks:

```
Chart of Accounts:
├── Accounts Payable (AP)
└── Medical Expenses (EXP)
    └── Medical Provider Payments
```

Each transaction creates:
- **Debit**: Medical Expenses (+)
- **Credit**: Accounts Payable (+)

## Functional Programming Design

The module follows functional programming principles:

### Pure Functions
- `format_provider_name()` - Name formatting with capitalization
- `format_patient_name()` - Patient name formatting
- `format_case_date()` - Date formatting for QB compatibility
- `format_procedures()` - Procedure code formatting
- `format_amount()` - Monetary amount formatting

### Data Transformation
- `get_provider_payment_data()` - Raw data extraction (same as report)
- `transform_cases_for_quickbooks()` - Transform raw data for QB format
- `create_vendors_csv()` - Generate CSV vendor file
- `create_transactions_iif()` - Generate IIF transaction file

### Benefits
- **Reusability**: Same data extraction logic as provider payment report
- **Maintainability**: Pure functions are easy to test and modify
- **Consistency**: Same data transformations across all exports
- **Scalability**: Easy to add new export formats

## File Storage

All exported files are:
1. **Saved locally** in the `exports/` directory
2. **Uploaded to S3** with detailed metadata
3. **Available for download** via the API response
4. **Tracked** for monitoring and cleanup

## Response Headers

Each export includes helpful headers:
- `X-Export-Type`: Type of export (vendors/transactions)
- `X-Record-Count`: Number of records exported
- `X-S3-URL`: S3 location of the file
- `Content-Disposition`: Proper filename for download

## Error Handling

The exports include comprehensive error handling:
- **404**: No data found matching criteria
- **500**: Database or file system errors
- **Validation**: Invalid date formats or parameters

## Monitoring

All exports are monitored with:
- **Success/failure tracking** via business metrics
- **S3 upload monitoring** with detailed metadata
- **Request logging** for audit trails
- **Performance tracking** for optimization

## Future Enhancements

The functional design makes it easy to add:
- Additional QuickBooks formats (QBO, QBW)
- Other accounting software exports (Xero, FreshBooks)
- Custom export templates
- Batch processing capabilities

## Technical Notes

- **Character Encoding**: UTF-8 for international characters
- **Date Format**: MM/DD/YYYY for QuickBooks compatibility
- **Decimal Precision**: 2 decimal places for monetary amounts
- **File Size**: Automatic handling of large datasets
- **Memory Usage**: Streaming for large exports to minimize memory usage 