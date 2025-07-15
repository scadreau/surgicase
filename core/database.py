# Created: 2025-07-15 09:20:13
# Last Modified: 2025-07-15 11:10:30

# core/database.py
import boto3
import json
import pymysql
import pymysql.cursors
import os

def get_db_credentials(secret_name):
    """
    Function to fetch database credentials from AWS Secrets Manager
    """
    region = os.environ.get("AWS_REGION", "us-east-1")
    client = boto3.client("secretsmanager", region_name=region)
    response = client.get_secret_value(SecretId=secret_name)
    secret = json.loads(response["SecretString"])
    return secret

def get_db_connection():
    """
    Helper function to establish database connection
    """
    # Fetch DB info from Secrets Manager
    secretdb = get_db_credentials("arn:aws:secretsmanager:us-east-1:002118831669:secret:prod/rds/serverinfo-MyhF8S")
    rds_host = secretdb["rds_address"]
    db_name = secretdb["db_name"]    
    secretdb = get_db_credentials("arn:aws:secretsmanager:us-east-1:002118831669:secret:rds!cluster-9376049b-abee-46d9-9cdb-95b95d6cdda0-fjhTNH")
    db_user = secretdb["username"]
    db_pass = secretdb["password"]
    
    return pymysql.connect(host=rds_host, user=db_user, password=db_pass, db=db_name)