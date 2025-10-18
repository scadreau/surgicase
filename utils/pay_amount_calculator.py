# Created: 2025-07-16 14:50:43
# Last Modified: 2025-10-18 17:39:40
# Author: Scott Cadreau

# utils/pay_amount_calculator.py
import pymysql.cursors
import logging
from decimal import Decimal

logger = logging.getLogger(__name__)

def calculate_case_pay_amount(case_id: str, user_id: str, conn) -> dict:
    """
    Calculate the maximum non-zero pay amount for a case based on its procedure codes.
    Uses the user's tier to determine which procedure codes to use for pay calculation.
    Skips any procedure codes with 0.00 pay amounts to avoid edge cases.
    
    Args:
        case_id: The case ID to calculate pay amount for
        user_id: The user ID to get the user's tier
        conn: Database connection object
        
    Returns:
        dict: {
            "success": bool,
            "pay_amount": Decimal,
            "pay_category": str,
            "procedure_codes_found": int,
            "message": str
        }
    """
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            # First, get the user's tier from user_profile
            cursor.execute("""
                SELECT user_tier 
                FROM user_profile 
                WHERE user_id = %s AND active = 1
            """, (user_id,))
            
            user_data = cursor.fetchone()
            if not user_data:
                error_msg = f"User not found or inactive: {user_id}"
                logger.error(error_msg)
                return {
                    "success": False,
                    "pay_amount": Decimal('0.00'),
                    "pay_category": None,
                    "procedure_codes_found": 0,
                    "message": error_msg
                }
            
            user_tier = user_data['user_tier']
            logger.info(f"User {user_id} has tier {user_tier}")
            
            # Check if the case has any procedure codes
            cursor.execute("""
                SELECT procedure_code 
                FROM case_procedure_codes 
                WHERE case_id = %s
            """, (case_id,))
            
            procedure_codes = cursor.fetchall()
            
            if not procedure_codes:
                # No procedure codes found, return 0.00
                return {
                    "success": True,
                    "pay_amount": Decimal('0.00'),
                    "pay_category": None,
                    "procedure_codes_found": 0,
                    "message": "No procedure codes found for case"
                }
            
            # Extract procedure codes from the result
            codes = [row['procedure_code'] for row in procedure_codes]
            logger.info(f"Found {len(codes)} procedure codes for case {case_id}: {codes}")
            
            # Query procedure_codes table for the maximum non-zero pay amount and its category using tier
            # Use placeholders for the IN clause
            placeholders = ','.join(['%s'] * len(codes))
            query = f"""
                SELECT code_pay_amount, code_category
                FROM procedure_codes 
                WHERE tier = %s AND procedure_code IN ({placeholders}) AND code_pay_amount > 0
                ORDER BY code_pay_amount DESC, procedure_code ASC
                LIMIT 1
            """
            # Build parameters: tier first, then all procedure codes
            params = [user_tier] + codes
            cursor.execute(query, params)
            
            result = cursor.fetchone()
            
            if result is None:
                # Procedure codes exist but no matching records found in procedure_codes table for this tier
                error_msg = f"No matching procedure codes found in procedure_codes table for case {case_id}, user {user_id} (tier {user_tier}), codes: {codes}"
                logger.error(error_msg)
                return {
                    "success": False,
                    "pay_amount": Decimal('0.00'),
                    "pay_category": None,
                    "procedure_codes_found": len(codes),
                    "message": error_msg
                }
            
            # Convert to Decimal for consistency
            pay_amount = Decimal(str(result['code_pay_amount']))
            pay_category = result['code_category']
            
            logger.info(f"Calculated maximum non-zero pay amount {pay_amount} with category '{pay_category}' for case {case_id} with {len(codes)} procedure codes (tier {user_tier})")
            
            return {
                "success": True,
                "pay_amount": pay_amount,
                "pay_category": pay_category,
                "procedure_codes_found": len(codes),
                "message": f"Successfully calculated maximum non-zero pay amount {pay_amount} with category '{pay_category}' from {len(codes)} procedure codes (tier {user_tier})"
            }
            
    except Exception as e:
        error_msg = f"Error calculating pay amount for case {case_id}: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return {
            "success": False,
            "pay_amount": Decimal('0.00'),
            "pay_category": None,
            "procedure_codes_found": 0,
            "message": error_msg
        }

def update_case_pay_amount(case_id: str, user_id: str, conn) -> dict:
    """
    Calculate and update the pay_amount and pay_category fields for a case.
    
    Args:
        case_id: The case ID to update
        user_id: The user ID for procedure code lookup
        conn: Database connection object
        
    Returns:
        dict: Result from calculate_case_pay_amount plus update status
    """
    try:
        # Calculate the pay amount and category
        calc_result = calculate_case_pay_amount(case_id, user_id, conn)
        
        if not calc_result["success"]:
            return calc_result
        
        # Update the case with the calculated pay amount and category
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute("""
                UPDATE cases 
                SET pay_amount = %s, pay_category = %s
                WHERE case_id = %s
            """, (calc_result["pay_amount"], calc_result["pay_category"], case_id))
            
            if cursor.rowcount == 0:
                return {
                    "success": False,
                    "pay_amount": calc_result["pay_amount"],
                    "pay_category": calc_result["pay_category"],
                    "procedure_codes_found": calc_result["procedure_codes_found"],
                    "message": f"Failed to update pay_amount and pay_category for case {case_id} - case not found"
                }
            
            logger.info(f"Updated pay_amount to {calc_result['pay_amount']} and pay_category to '{calc_result['pay_category']}' for case {case_id}")
            
            return {
                "success": True,
                "pay_amount": calc_result["pay_amount"],
                "pay_category": calc_result["pay_category"],
                "procedure_codes_found": calc_result["procedure_codes_found"],
                "message": f"Successfully updated pay_amount to {calc_result['pay_amount']} and pay_category to '{calc_result['pay_category']}' for case {case_id}"
            }
            
    except Exception as e:
        error_msg = f"Error updating pay amount and category for case {case_id}: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return {
            "success": False,
            "pay_amount": Decimal('0.00'),
            "pay_category": None,
            "procedure_codes_found": 0,
            "message": error_msg
        }

def calculate_case_pay_amount_v2(case_id: str, user_id: str, conn) -> dict:
    """
    Calculate the maximum non-zero pay amount for a case based on its procedure codes.
    Uses normalized table structure: joins procedure_codes with procedure_code_buckets2
    to get pay amounts based on code_category and user tier.
    Skips any procedure codes with 0.00 pay amounts to avoid edge cases.
    
    This is the V2 implementation using proper database normalization:
    - procedure_codes: contains code metadata (code_category, description, status)
    - procedure_code_buckets2: contains pay amounts by code_bucket and tier
    - Join on: code_category = code_bucket AND tier from user_profile
    
    Args:
        case_id: The case ID to calculate pay amount for
        user_id: The user ID to get the user's tier
        conn: Database connection object
        
    Returns:
        dict: {
            "success": bool,
            "pay_amount": Decimal,
            "pay_category": str,
            "procedure_codes_found": int,
            "message": str
        }
    """
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            # Single query to get pay amount using normalized structure
            # Joins: case_procedure_codes -> procedure_codes -> procedure_code_buckets2
            # Also gets user_tier from user_profile
            cursor.execute("""
                SELECT 
                    pcb2.pay_amount as code_pay_amount,
                    pc.code_category,
                    COUNT(DISTINCT cpc.procedure_code) as total_codes
                FROM case_procedure_codes cpc
                JOIN procedure_codes pc ON cpc.procedure_code = pc.procedure_code
                JOIN user_profile up ON up.user_id = %s AND up.active = 1
                JOIN procedure_code_buckets2 pcb2 
                    ON pc.code_category = pcb2.code_bucket 
                    AND pcb2.tier = up.user_tier
                WHERE cpc.case_id = %s 
                    AND pcb2.pay_amount > 0
                ORDER BY pcb2.pay_amount DESC, pc.procedure_code ASC
                LIMIT 1
            """, (user_id, case_id))
            
            result = cursor.fetchone()
            
            if result is None:
                # Check if user exists and is active
                cursor.execute("""
                    SELECT user_tier 
                    FROM user_profile 
                    WHERE user_id = %s AND active = 1
                """, (user_id,))
                
                user_data = cursor.fetchone()
                if not user_data:
                    error_msg = f"User not found or inactive: {user_id}"
                    logger.error(error_msg)
                    return {
                        "success": False,
                        "pay_amount": Decimal('0.00'),
                        "pay_category": None,
                        "procedure_codes_found": 0,
                        "message": error_msg
                    }
                
                # Check if case has any procedure codes
                cursor.execute("""
                    SELECT COUNT(*) as code_count
                    FROM case_procedure_codes 
                    WHERE case_id = %s
                """, (case_id,))
                
                code_check = cursor.fetchone()
                code_count = code_check['code_count'] if code_check else 0
                
                if code_count == 0:
                    # No procedure codes found, return 0.00
                    return {
                        "success": True,
                        "pay_amount": Decimal('0.00'),
                        "pay_category": None,
                        "procedure_codes_found": 0,
                        "message": "No procedure codes found for case"
                    }
                else:
                    # Procedure codes exist but no matching records found
                    error_msg = f"No matching pay amounts found for case {case_id}, user {user_id} (tier {user_data['user_tier']}) in procedure_code_buckets2"
                    logger.error(error_msg)
                    return {
                        "success": False,
                        "pay_amount": Decimal('0.00'),
                        "pay_category": None,
                        "procedure_codes_found": code_count,
                        "message": error_msg
                    }
            
            # Convert to Decimal for consistency
            pay_amount = Decimal(str(result['code_pay_amount']))
            pay_category = result['code_category']
            total_codes = result['total_codes']
            
            logger.info(f"Calculated maximum non-zero pay amount {pay_amount} with category '{pay_category}' for case {case_id} with {total_codes} procedure codes")
            
            return {
                "success": True,
                "pay_amount": pay_amount,
                "pay_category": pay_category,
                "procedure_codes_found": total_codes,
                "message": f"Successfully calculated maximum non-zero pay amount {pay_amount} with category '{pay_category}' from {total_codes} procedure codes"
            }
            
    except Exception as e:
        error_msg = f"Error calculating pay amount for case {case_id}: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return {
            "success": False,
            "pay_amount": Decimal('0.00'),
            "pay_category": None,
            "procedure_codes_found": 0,
            "message": error_msg
        }

def update_case_pay_amount_v2(case_id: str, user_id: str, conn) -> dict:
    """
    Calculate and update the pay_amount and pay_category fields for a case.
    Uses V2 normalized query approach with procedure_code_buckets2.
    
    Args:
        case_id: The case ID to update
        user_id: The user ID for procedure code lookup
        conn: Database connection object
        
    Returns:
        dict: Result from calculate_case_pay_amount_v2 plus update status
    """
    try:
        # Calculate the pay amount and category using v2
        calc_result = calculate_case_pay_amount_v2(case_id, user_id, conn)
        
        if not calc_result["success"]:
            return calc_result
        
        # Update the case with the calculated pay amount and category
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute("""
                UPDATE cases 
                SET pay_amount = %s, pay_category = %s
                WHERE case_id = %s
            """, (calc_result["pay_amount"], calc_result["pay_category"], case_id))
            
            if cursor.rowcount == 0:
                return {
                    "success": False,
                    "pay_amount": calc_result["pay_amount"],
                    "pay_category": calc_result["pay_category"],
                    "procedure_codes_found": calc_result["procedure_codes_found"],
                    "message": f"Failed to update pay_amount and pay_category for case {case_id} - case not found"
                }
            
            logger.info(f"Updated pay_amount to {calc_result['pay_amount']} and pay_category to '{calc_result['pay_category']}' for case {case_id}")
            
            return {
                "success": True,
                "pay_amount": calc_result["pay_amount"],
                "pay_category": calc_result["pay_category"],
                "procedure_codes_found": calc_result["procedure_codes_found"],
                "message": f"Successfully updated pay_amount to {calc_result['pay_amount']} and pay_category to '{calc_result['pay_category']}' for case {case_id}"
            }
            
    except Exception as e:
        error_msg = f"Error updating pay amount and category for case {case_id}: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return {
            "success": False,
            "pay_amount": Decimal('0.00'),
            "pay_category": None,
            "procedure_codes_found": 0,
            "message": error_msg
        } 