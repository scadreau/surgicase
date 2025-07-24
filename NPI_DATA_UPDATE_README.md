# NPI Data Update System

This document describes the NPI (National Provider Identifier) data update system for the SurgiCase Management API. The system automatically downloads the latest weekly NPI files from CMS and processes them into the database for surgeon and facility search functionality.

## Overview

The NPI data update system consists of several scripts that work together to:

1. **Download** the most recent weekly NPI files from the CMS website
2. **Process** and distribute the data into appropriate database tables based on entity types
3. **Create** optimized search tables for surgeon and facility lookups
4. **Log** all operations for monitoring and debugging

## Scripts Available

### 1. `utils/extract_npi_data.py` - Main NPI Update Script
The comprehensive script for downloading and processing NPI data with full functionality.

**Features:**
- Downloads the most recent weekly NPI file from CMS
- Processes CSV data and distributes to `npi_data_0`, `npi_data_1`, and `npi_data_2` tables
- Handles entity type classification (Individual=1, Organization=2, Other/Unknown=0)
- Optimized batch processing (10,000 records per batch)
- Creates A-Z search tables for surgeons and facilities
- Multi-threaded search table creation for faster execution
- Comprehensive error handling and logging
- Records execution statistics in `npi_update_log` and `npi_search_table_log` tables
- Performance optimizations and database indexing

### 2. `utils/npi_initial_load.py` - Initial Data Loader
Used for loading large initial NPI data files with progress tracking and chunk processing.

## Command Line Usage

### Main NPI Data Update (Recommended)

To run the complete NPI data update with search table creation:

```bash
# From the project root directory
python utils/extract_npi_data.py
```

This single command performs:
- Downloads the latest weekly NPI file to `../npi_data/`
- Updates all core NPI data tables
- Creates optimized A-Z search tables
- Archives the processed file to `../npi_data/archive/`
- Cleans up old temporary files
- Logs all operations for monitoring

### Initial Data Load

For loading large initial NPI data files:

```bash
# From the project root directory
python utils/npi_initial_load.py
```

## Prerequisites

### Required Files

Before running any NPI update script, ensure the following file exists:

```
../npi_data/new_header.csv
```

This file contains the column headers that map the NPI CSV columns to your database schema. The script will fail if this file is missing.

**Important:** The `../npi_data` directory must be writable by the user running the script, as it will create subdirectories and manage files automatically.

### Database Tables

The following tables must exist in your database:

**Core Data Tables:**
- `npi_data_0` - Unknown/Other entity types
- `npi_data_1` - Individual providers (doctors, nurses, etc.)
- `npi_data_2` - Organizations (hospitals, clinics, etc.)

**Logging Tables:**
- `npi_update_log` - Tracks main data processing operations
- `npi_search_table_log` - Tracks search table creation (if using extract_npi_data.py)

**Search Tables (created by extract_npi_data.py):**
- `search_surgeon_facility.search_surgeon_a` through `search_surgeon_facility.search_surgeon_z`
- `search_surgeon_facility.search_facility_a` through `search_surgeon_facility.search_facility_z`

### Dependencies

Install required Python packages:

```bash
pip install requests beautifulsoup4 pandas pymysql
```

## Environment Setup

### Directory Structure

The scripts will create and use the following directories:

```
project_root/
├── ../npi_data/             # Download directory (outside project, auto-created)
│   ├── new_header.csv       # Required: Column mapping file
│   └── archive/             # Archive directory (auto-created)
│       ├── npidata_pfile_20250107-20250113.csv
│       ├── npidata_pfile_20250114-20250120.csv
│       └── npidata_pfile_20250121-20250127.csv
└── utils/
    ├── extract_npi_data.py  # Main NPI update script
    └── npi_initial_load.py  # Initial data loader
```

**Note:** The `npi_data` directory is located outside the project directory (`../npi_data`) to prevent data files from being included in git operations.

### Database Configuration

Ensure your database connection is properly configured in `core/database.py`. The scripts use:
- `get_db_connection()` - Get database connection
- `close_db_connection(conn)` - Close database connection

## Monitoring and Logging

### Execution Logs

Each run creates entries in the `npi_update_log` table with:
- `execution_ts` - Timestamp of execution
- `filename_processed` - Name of the processed file
- `total_rows` - Total number of records processed
- `total_0_rows`, `total_1_rows`, `total_2_rows` - Records by entity type

### Search Table Logs

When using `extract_npi_data.py`, search table creation is logged in `npi_search_table_log`:
- `execution_ts` - Timestamp
- `table_type` - 'surgeon' or 'facility'
- `table_name` - Name of the created table
- `records_inserted` - Number of records
- `execution_time_seconds` - Time taken
- `status` - 'success' or 'error'
- `error_message` - Error details if applicable

### Console Output

The scripts provide real-time progress information:

```
Starting NPI data update process...
Downloading NPI data file...
Downloaded and extracted: https://download.cms.gov/nppes/...
Processing NPI data file: npidata_pfile_...csv
Main NPI data processing completed:
  Total rows processed: 45,123
  Entity type 0 inserted: 1,234
  Entity type 1 inserted: 35,678
  Entity type 2 inserted: 8,211
Starting creation of search tables...
Creating surgeon search tables...
All surgeon tables created. Starting facility tables...
All search tables created in 42.3 seconds
Cleaning up old files and archiving current file...
  Archived: npidata_pfile_20250121-20250127.csv -> archive/npidata_pfile_20250121-20250127.csv
  Deleted: old_file.zip
Cleanup completed: 1 old files removed, current file archived

Complete NPI data update process finished successfully!
Total execution time: 125.4 seconds (2.1 minutes)
```

## Scheduling Regular Updates

### Weekly Updates (Recommended)

Set up a weekly cron job to get the latest NPI updates:

```bash
# Add to crontab (runs every Sunday at 2 AM)
0 2 * * 0 cd /path/to/surgicase && python utils/extract_npi_data.py >> /var/log/npi_update.log 2>&1
```

This single scheduled job handles:
- Weekly data downloads
- Database updates
- Search table refresh
- Complete logging

## Performance Considerations

### Batch Size

The scripts use optimized batch sizes:
- `extract_npi_data.py`: 10,000 records per batch (optimized for RDS performance)
- `npi_initial_load.py`: 1,000 records per batch with chunk processing

### Memory Usage

- Weekly files: ~50-100MB, minimal memory impact
- Full files: 1GB+, requires adequate system memory

### Database Load

- Uses batch inserts to minimize database load
- Includes transaction management and error recovery
- Search table creation uses threading for faster execution
- Automatic file archiving and cleanup to manage disk space

## Troubleshooting

### Common Issues

**1. Missing header file:**
```
Error: Header file not found: ../npi_data/new_header.csv
```
Solution: Ensure the `new_header.csv` file exists in the `../npi_data` directory.

**2. Database connection errors:**
```
Error inserting batch into npi_data_1: ...
```
Solution: Check database connectivity and table schemas.

**3. Download failures:**
```
No weekly files found.
```
Solution: Check internet connectivity and CMS website availability.

### Debug Mode

For detailed debugging, modify the scripts to include additional logging or run with Python's verbose mode:

```bash
python -v utils/extract_npi_data.py
```

## Integration with API

The updated NPI data is used by the following API endpoints:

- `/search_surgeon` - Searches individual providers (npi_data_1)
- `/search_facility` - Searches organizations (npi_data_2)  
- `/check_npi` - Validates NPI numbers against the registry

The search functionality uses the optimized search tables created by `extract_npi_data.py` for faster query performance.

## Data Sources

**CMS NPI Registry:** https://download.cms.gov/nppes/NPI_Files.html

The system downloads from:
- **Weekly files:** Incremental updates (recommended for regular use)
- **Full files:** Complete dataset (for initial loads or full refreshes)

Updates are published weekly by CMS, typically on Sundays. 