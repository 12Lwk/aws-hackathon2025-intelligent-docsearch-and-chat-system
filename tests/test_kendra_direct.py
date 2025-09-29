#!/usr/bin/env python
"""
Test script to check Kendra documents directly
"""
import os
import sys
import django

# Setup Django environment
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'document_project.settings')
django.setup()

from document_app.aws_document_pipeline.kendra_database import KendraDatabase

def test_kendra_direct():
    """Test Kendra directly"""
    print("Testing Kendra Direct Access...")
    
    kendra_db = KendraDatabase()
    
    # Test 1: Try to search for any documents
    print("\n1. Searching for any documents with '*':")
    docs = kendra_db.search_documents('*', limit=10)
    print(f"Found {len(docs)} documents")
    
    # Test 2: Try to search for recent document
    print("\n2. Searching for 'maintenance':")
    docs = kendra_db.search_documents('maintenance', limit=10)
    print(f"Found {len(docs)} documents")
    
    # Test 3: Try to get specific document by ID
    print("\n3. Testing document by ID (87a8fa8f-8bcf-412a-9c2d-edb229dec8a9):")
    doc = kendra_db.get_document_by_id('87a8fa8f-8bcf-412a-9c2d-edb229dec8a9')
    if doc:
        print(f"Found document: {doc['title']}")
    else:
        print("Document not found")
    
    # Test 4: Check index status
    print("\n4. Checking Kendra index status:")
    try:
        response = kendra_db.kendra_client.describe_index(Id=kendra_db.index_id)
        print(f"Index Status: {response.get('Status')}")
        print(f"Document Count: {response.get('DocumentMetadataConfigurations', 'N/A')}")
    except Exception as e:
        print(f"Error checking index: {e}")

if __name__ == "__main__":
    test_kendra_direct()