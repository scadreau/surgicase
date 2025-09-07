-- Database Index Optimization for Case Export Performance
-- Created: 2025-01-27
-- Purpose: Improve query performance for large case exports

-- Add composite index on case_procedure_codes for better JOIN performance
-- This index will significantly speed up the LEFT JOIN in the export query
CREATE INDEX idx_case_procedure_codes_case_id_procedure ON case_procedure_codes(case_id, procedure_code);

-- Add index on cases.case_id for better IN clause performance (if not already primary key)
-- This should already exist as PRIMARY KEY, but adding comment for completeness
-- The existing PRIMARY KEY on case_id should handle this efficiently

-- Optional: Add covering index for common case export fields
-- This can eliminate the need to access the main table data for exports
CREATE INDEX idx_cases_export_covering ON cases(case_id, user_id, case_date, patient_first, patient_last, case_status, pay_amount);

-- Analyze tables to update statistics after index creation
ANALYZE TABLE cases;
ANALYZE TABLE case_procedure_codes;

-- Query to check current indexes
-- Run this to verify indexes are in place:
-- SHOW INDEX FROM cases;
-- SHOW INDEX FROM case_procedure_codes;
