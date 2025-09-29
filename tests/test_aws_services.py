#!/usr/bin/env python
"""
Test script to verify AWS Textract and Comprehend services are working
"""
import os
import sys
import django

# Setup Django environment
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'document_project.settings')
django.setup()

import boto3
from django.conf import settings
from document_app.aws_document_pipeline.pipeline import DocumentPipeline

def test_aws_services():
    """Test AWS services connectivity and functionality"""
    print("Testing AWS Services...")
    print(f"Region: {settings.AWS_REGION}")
    print(f"S3 Bucket: {settings.AWS_S3_BUCKET_NAME}")
    
    try:
        # Initialize pipeline
        pipeline = DocumentPipeline()
        print("[OK] Pipeline initialized successfully")
        
        # Test S3 connectivity
        try:
            response = pipeline.s3_client.head_bucket(Bucket=settings.AWS_S3_BUCKET_NAME)
            print("[OK] S3 connection successful")
        except Exception as e:
            print(f"[ERROR] S3 connection failed: {e}")
            return False
        
        # Test Textract connectivity
        try:
            # Test with a simple operation
            pipeline.textract_client.get_document_analysis(JobId='test-job-id')
        except pipeline.textract_client.exceptions.InvalidJobIdException:
            print("[OK] Textract service accessible (expected InvalidJobId error)")
        except Exception as e:
            if 'InvalidJobIdException' in str(e):
                print("[OK] Textract service accessible")
            else:
                print(f"[ERROR] Textract connection failed: {e}")
                return False
        
        # Test Comprehend connectivity
        try:
            # Test with sample text
            test_text = "This is a test document for manufacturing operations."
            response = pipeline.comprehend_client.detect_key_phrases(
                Text=test_text,
                LanguageCode='en'
            )
            print(f"[OK] Comprehend service working - Found {len(response.get('KeyPhrases', []))} key phrases")
            
            # Test entity detection
            entities_response = pipeline.comprehend_client.detect_entities(
                Text=test_text,
                LanguageCode='en'
            )
            print(f"[OK] Comprehend entity detection working - Found {len(entities_response.get('Entities', []))} entities")
            
        except Exception as e:
            print(f"[ERROR] Comprehend connection failed: {e}")
            return False
        
        # Test Kendra connectivity
        try:
            response = pipeline.kendra_client.describe_index(IndexId=settings.AWS_KENDRA_INDEX_ID)
            print(f"[OK] Kendra index accessible - Status: {response.get('Status', 'Unknown')}")
        except Exception as e:
            print(f"[WARNING] Kendra connection issue: {e}")
        
        print("\n[SUCCESS] All core services are working!")
        return True
        
    except Exception as e:
        print(f"[ERROR] Pipeline initialization failed: {e}")
        return False

def test_classification():
    """Test the enhanced classification system"""
    print("\nTesting Classification System...")
    
    pipeline = DocumentPipeline()
    
    test_cases = [
        ("documents/policies/safety_policy.pdf", "Safety Policy Document", "This document outlines safety procedures"),
        ("documents/operations/production_manual.pdf", "Production Manual", "Manufacturing operations and production guidelines"),
        ("documents/maintenance/repair_guide.pdf", "Repair Guide", "Technical manual for equipment maintenance"),
        ("documents/training/course_material.pdf", "Training Course", "Educational material for employee training"),
    ]
    
    for s3_key, filename, text in test_cases:
        category, confidence = pipeline.classify_document_with_comprehend(text, filename, s3_key)
        print(f"[CLASSIFY] {s3_key} -> {category} (confidence: {confidence:.2f})")
    
    print("[OK] Classification system tested")

if __name__ == "__main__":
    print("AWS Services Test Suite")
    print("=" * 50)
    
    if test_aws_services():
        test_classification()
        print("\n[SUCCESS] All tests completed successfully!")
    else:
        print("\n[ERROR] Some tests failed. Check your AWS configuration.")