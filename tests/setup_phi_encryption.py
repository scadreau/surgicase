# Created: 2025-10-19
# Last Modified: 2025-10-19 23:48:34
# Author: Scott Cadreau

"""
Setup script for PHI encryption infrastructure.

This script helps you set up the prerequisites:
1. Creates AWS KMS master key if it doesn't exist
2. Runs database schema SQL
3. Guides you through the setup process

Usage:
    python tests/setup_phi_encryption.py
"""

import sys
import os
import subprocess

sys.path.insert(0, '/home/scadreau/surgicase')

import boto3
from botocore.exceptions import ClientError
from core.database import get_db_connection, close_db_connection

# ANSI colors
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
RESET = '\033[0m'
BOLD = '\033[1m'


def print_header(text):
    print(f"\n{BLUE}{BOLD}{'=' * 80}{RESET}")
    print(f"{BLUE}{BOLD}{text}{RESET}")
    print(f"{BLUE}{BOLD}{'=' * 80}{RESET}")


def print_success(text):
    print(f"{GREEN}✓ {text}{RESET}")


def print_error(text):
    print(f"{RED}✗ {text}{RESET}")


def print_warning(text):
    print(f"{YELLOW}⚠ {text}{RESET}")


def print_info(text):
    print(f"{BLUE}ℹ {text}{RESET}")


def check_kms_key():
    """Check if KMS key exists."""
    print_header("Step 1: Check AWS KMS Master Key")
    
    try:
        kms_client = boto3.client('kms', region_name='us-east-1')
        
        try:
            response = kms_client.describe_key(KeyId='alias/surgicase-phi-master')
            key_id = response['KeyMetadata']['KeyId']
            key_state = response['KeyMetadata']['KeyState']
            
            print_success(f"KMS key exists: {key_id}")
            print_info(f"Key state: {key_state}")
            
            if key_state != 'Enabled':
                print_error(f"Key is not enabled (state: {key_state})")
                return False
            
            return True
            
        except ClientError as e:
            if e.response['Error']['Code'] == 'NotFoundException':
                print_warning("KMS key 'alias/surgicase-phi-master' not found")
                return False
            raise
            
    except Exception as e:
        print_error(f"Error checking KMS key: {str(e)}")
        return False


def create_kms_key():
    """Create KMS key."""
    print("\nWould you like to create the KMS key now? (yes/no): ", end='')
    response = input().strip().lower()
    
    if response != 'yes':
        print_info("Skipping KMS key creation")
        print_info("You can create it manually with:")
        print("""
aws kms create-key \\
  --description "SurgiCase PHI field encryption master key" \\
  --key-usage ENCRYPT_DECRYPT \\
  --region us-east-1

# Then create alias (replace KEY_ID with output from above):
aws kms create-alias \\
  --alias-name alias/surgicase-phi-master \\
  --target-key-id KEY_ID \\
  --region us-east-1
        """)
        return False
    
    try:
        print_info("Creating KMS key...")
        kms_client = boto3.client('kms', region_name='us-east-1')
        
        # Get AWS account ID
        sts_client = boto3.client('sts')
        account_id = sts_client.get_caller_identity()['Account']
        
        # Create key policy
        key_policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Sid": "Enable IAM User Permissions",
                    "Effect": "Allow",
                    "Principal": {"AWS": f"arn:aws:iam::{account_id}:root"},
                    "Action": "kms:*",
                    "Resource": "*"
                }
            ]
        }
        
        # Create key
        import json
        response = kms_client.create_key(
            Description='SurgiCase PHI field encryption master key',
            KeyUsage='ENCRYPT_DECRYPT',
            KeySpec='SYMMETRIC_DEFAULT',
            Policy=json.dumps(key_policy),
            Tags=[
                {'TagKey': 'Application', 'TagValue': 'SurgiCase'},
                {'TagKey': 'Purpose', 'TagValue': 'PHIEncryption'},
                {'TagKey': 'Compliance', 'TagValue': 'HIPAA'}
            ]
        )
        
        key_id = response['KeyMetadata']['KeyId']
        print_success(f"Created KMS key: {key_id}")
        
        # Create alias
        print_info("Creating alias...")
        kms_client.create_alias(
            AliasName='alias/surgicase-phi-master',
            TargetKeyId=key_id
        )
        
        print_success("Created alias: alias/surgicase-phi-master")
        print_success("KMS key setup complete!")
        
        return True
        
    except Exception as e:
        print_error(f"Error creating KMS key: {str(e)}")
        return False


def check_database_schema():
    """Check if database schema is set up."""
    print_header("Step 2: Check Database Schema")
    
    try:
        conn = get_db_connection()
        
        with conn.cursor() as cursor:
            # Check if user_encryption_keys table exists
            cursor.execute("""
                SELECT COUNT(*) FROM information_schema.TABLES 
                WHERE TABLE_SCHEMA = DATABASE() 
                AND TABLE_NAME = 'user_encryption_keys'
            """)
            
            if cursor.fetchone()[0] > 0:
                print_success("user_encryption_keys table exists")
                
                # Check if encryption_key_audit exists
                cursor.execute("""
                    SELECT COUNT(*) FROM information_schema.TABLES 
                    WHERE TABLE_SCHEMA = DATABASE() 
                    AND TABLE_NAME = 'encryption_key_audit'
                """)
                
                if cursor.fetchone()[0] > 0:
                    print_success("encryption_key_audit table exists")
                else:
                    print_warning("encryption_key_audit table missing")
                    return False
                
                # Check phi_encrypted column
                cursor.execute("""
                    SELECT COUNT(*) FROM information_schema.COLUMNS 
                    WHERE TABLE_SCHEMA = DATABASE() 
                    AND TABLE_NAME = 'cases' 
                    AND COLUMN_NAME = 'phi_encrypted'
                """)
                
                if cursor.fetchone()[0] > 0:
                    print_success("cases.phi_encrypted column exists")
                else:
                    print_warning("cases.phi_encrypted column missing")
                    return False
                
                close_db_connection(conn)
                return True
            else:
                print_warning("user_encryption_keys table not found")
                close_db_connection(conn)
                return False
                
    except Exception as e:
        print_error(f"Error checking database schema: {str(e)}")
        return False


def run_database_schema():
    """Run database schema SQL."""
    print("\nWould you like to run the database schema now? (yes/no): ", end='')
    response = input().strip().lower()
    
    if response != 'yes':
        print_info("Skipping database schema setup")
        print_info("You can run it manually with:")
        print("  mysql -h <host> -u <user> -p surgicase < database_phi_encryption_schema.sql")
        return False
    
    try:
        print_info("Running database schema...")
        
        # Get database connection info
        conn = get_db_connection()
        close_db_connection(conn)
        
        # Run SQL file
        sql_file = '/home/scadreau/surgicase/database_phi_encryption_schema.sql'
        
        if not os.path.exists(sql_file):
            print_error(f"SQL file not found: {sql_file}")
            return False
        
        # Execute SQL commands
        with open(sql_file, 'r') as f:
            sql_commands = f.read()
        
        conn = get_db_connection()
        
        # Split by semicolon and execute each statement
        for statement in sql_commands.split(';'):
            statement = statement.strip()
            if statement and not statement.startswith('--'):
                with conn.cursor() as cursor:
                    cursor.execute(statement)
        
        conn.commit()
        close_db_connection(conn)
        
        print_success("Database schema created successfully!")
        return True
        
    except Exception as e:
        print_error(f"Error running database schema: {str(e)}")
        return False


def main():
    """Main setup flow."""
    print(f"\n{BOLD}{'=' * 80}{RESET}")
    print(f"{BOLD}PHI ENCRYPTION SETUP{RESET}")
    print(f"{BOLD}{'=' * 80}{RESET}")
    
    print_info("This script will help you set up PHI encryption infrastructure")
    print_info("Prerequisites: AWS credentials configured, database access")
    
    # Step 1: Check KMS key
    has_kms = check_kms_key()
    if not has_kms:
        created_kms = create_kms_key()
        if not created_kms:
            print_error("\nSetup incomplete: KMS key not created")
            print_info("Please create the KMS key manually and run this script again")
            return 1
    
    # Step 2: Check database schema
    has_schema = check_database_schema()
    if not has_schema:
        created_schema = run_database_schema()
        if not created_schema:
            print_error("\nSetup incomplete: Database schema not created")
            print_info("Please run the SQL file manually and run this script again")
            return 1
    
    # Success!
    print_header("Setup Complete!")
    print_success("All prerequisites are in place")
    print_info("\nNext steps:")
    print("  1. Run tests: python tests/test_phi_encryption.py")
    print("  2. Generate keys: python utils/generate_encryption_keys.py --dry-run")
    print("  3. Review results before proceeding to Phase 3")
    
    return 0


if __name__ == '__main__':
    sys.exit(main())

