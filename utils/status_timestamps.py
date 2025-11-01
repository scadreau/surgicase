# Created: 2025-11-01
# Last Modified: 2025-11-01 01:10:48
# Author: Scott Cadreau

# utils/status_timestamps.py
"""
Shared utilities for managing case status timestamp updates.

This module provides a centralized mapping of case statuses to their corresponding
timestamp fields, ensuring consistent timestamp handling across all status update operations.
"""

# Configuration mapping for status codes to timestamp fields
# Format: status_code: timestamp_field_name
# Timestamps are updated whenever a case transitions TO the specified status
STATUS_TIMESTAMP_MAPPING = {
    7: "billable_flag_ts",
    8: "docs_needed_ts",
    10: "submitted_ts",
    15: "pending_payment_ts",
    20: "paid_to_provider_ts",
    30: "sent_to_biller_ts",
    40: "received_pmnt_ts",
    50: "sent_to_negotiation_ts",
    60: "settled_ts",
    70: "sent_to_idr_ts",
    80: "idr_decision_ts",
    400: "rejected_ts",
    500: "closed_ts",
    # Add future timestamp mappings here as needed
}


def get_timestamp_field(status: int) -> str:
    """
    Get the timestamp field name for a target status.
    
    Args:
        status: Target case status
        
    Returns:
        str: Timestamp field name or None if no mapping exists
    """
    return STATUS_TIMESTAMP_MAPPING.get(status)


def build_status_update_query(status: int) -> tuple:
    """
    Build UPDATE query for status change with optional timestamp.
    
    Args:
        status: Target case status
    
    Returns:
        tuple: (query_string, has_timestamp)
            - query_string: SQL UPDATE query with parameters for (status, case_id)
            - has_timestamp: Boolean indicating if timestamp was included
    """
    timestamp_field = get_timestamp_field(status)
    
    if timestamp_field:
        query = f"""
            UPDATE cases 
            SET case_status = %s, {timestamp_field} = CURRENT_TIMESTAMP 
            WHERE case_id = %s AND active = 1
        """
        return (query, True)
    else:
        query = """
            UPDATE cases 
            SET case_status = %s 
            WHERE case_id = %s AND active = 1
        """
        return (query, False)

