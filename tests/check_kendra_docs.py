#!/usr/bin/env python
import os
import sys
import django

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'document_project.settings')
django.setup()

from document_app.aws_document_pipeline.kendra_database import KendraDatabase

def check_kendra():
    kendra_db = KendraDatabase()
    
    # Try different search approaches
    print("1. Searching with empty query:")
    docs = kendra_db.search_documents('', limit=10)
    print(f"Found: {len(docs)}")
    
    print("\n2. Searching with 'document':")
    docs = kendra_db.search_documents('document', limit=10)
    print(f"Found: {len(docs)}")
    
    print("\n3. Checking data sources:")
    try:
        response = kendra_db.kendra_client.list_data_sources(IndexId=kendra_db.index_id)
        for ds in response.get('SummaryItems', []):
            print(f"Data Source: {ds.get('Name')} - Status: {ds.get('Status')}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_kendra()