#!/usr/bin/env python
import boto3
from document_app.aws_credential_keys.config import *

def test_kendra_search():
    kendra = boto3.client(
        'kendra',
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
        aws_session_token=AWS_SESSION_TOKEN,
        region_name=AWS_REGION
    )
    
    try:
        response = kendra.query(
            IndexId=AWS_KENDRA_INDEX_ID,
            QueryText='maintenance manual',
            PageSize=5
        )
        
        print(f"Found {len(response['ResultItems'])} results:")
        for item in response['ResultItems']:
            print(f"- {item['DocumentTitle']['Text']}")
            
    except Exception as e:
        print(f"Kendra search failed: {e}")

if __name__ == "__main__":
    test_kendra_search()