#!/usr/bin/env python
import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'document_project.settings')
django.setup()

from document_app.models import Document

def check_document_classification():
    docs = Document.objects.all().order_by('-upload_date')[:5]
    
    print("Recent Document Classifications:")
    print("-" * 50)
    
    for doc in docs:
        print(f"File: {doc.file_name}")
        print(f"Category: {doc.category}")
        print(f"Confidence: {doc.confidence_score}")
        print(f"Status: {doc.processing_status}")
        print("-" * 30)

if __name__ == "__main__":
    check_document_classification()