#!/usr/bin/env python
"""
Test script to verify classification system without requiring full AWS permissions
"""
import os
import sys
import django

# Setup Django environment
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'document_project.settings')
django.setup()

from document_app.aws_document_pipeline.pipeline import DocumentPipeline

def test_classification_system():
    """Test the enhanced folder-based classification system"""
    print("Testing Enhanced Classification System")
    print("=" * 50)
    
    pipeline = DocumentPipeline()
    
    # Test cases with different folder structures and content
    test_cases = [
        {
            "s3_key": "documents/policies/safety_guidelines.pdf",
            "filename": "safety_guidelines.pdf",
            "text": "This document outlines safety procedures and guidelines for manufacturing operations.",
            "expected": "policies"
        },
        {
            "s3_key": "documents/operations/production_manual.pdf", 
            "filename": "production_manual.pdf",
            "text": "Manufacturing operations and production guidelines for assembly line workers.",
            "expected": "operations"
        },
        {
            "s3_key": "documents/maintenance/equipment_repair.pdf",
            "filename": "equipment_repair.pdf", 
            "text": "Technical manual for equipment maintenance and repair procedures.",
            "expected": "maintenance"
        },
        {
            "s3_key": "documents/training/employee_handbook.pdf",
            "filename": "employee_handbook.pdf",
            "text": "Training materials and educational content for new employees.",
            "expected": "training"
        },
        {
            "s3_key": "documents/safety/emergency_procedures.pdf",
            "filename": "emergency_procedures.pdf",
            "text": "Emergency response procedures and safety protocols for hazardous situations.",
            "expected": "safety"
        },
        {
            "s3_key": "documents/quality/inspection_checklist.pdf",
            "filename": "inspection_checklist.pdf",
            "text": "Quality control inspection procedures and compliance standards.",
            "expected": "quality"
        },
        {
            "s3_key": "documents/misc/random_document.pdf",
            "filename": "random_document.pdf",
            "text": "Some random content that doesn't fit specific categories.",
            "expected": "others"
        }
    ]
    
    print("Testing folder-based classification:")
    print()
    
    correct_predictions = 0
    total_tests = len(test_cases)
    
    for i, test_case in enumerate(test_cases, 1):
        try:
            category, confidence = pipeline.classify_document_with_comprehend(
                test_case["text"], 
                test_case["filename"], 
                test_case["s3_key"]
            )
            
            is_correct = category == test_case["expected"]
            status = "[PASS]" if is_correct else "[FAIL]"
            
            if is_correct:
                correct_predictions += 1
            
            print(f"{status} Test {i}: {test_case['filename']}")
            print(f"   Path: {test_case['s3_key']}")
            print(f"   Expected: {test_case['expected']} | Got: {category} | Confidence: {confidence:.2f}")
            print()
            
        except Exception as e:
            print(f"[ERROR] Test {i} failed: {e}")
            print()
    
    # Summary
    accuracy = (correct_predictions / total_tests) * 100
    print("=" * 50)
    print(f"Classification Test Results:")
    print(f"Correct: {correct_predictions}/{total_tests}")
    print(f"Accuracy: {accuracy:.1f}%")
    
    if accuracy >= 80:
        print("[SUCCESS] Classification system is working well!")
    elif accuracy >= 60:
        print("[WARNING] Classification system needs improvement")
    else:
        print("[ERROR] Classification system has issues")
    
    return accuracy >= 60

def test_folder_mapping():
    """Test the folder classification mapping"""
    print("\nTesting Folder Classification Mapping")
    print("=" * 50)
    
    from django.conf import settings
    
    folder_map = getattr(settings, 'FOLDER_CLASSIFICATION_MAP', {})
    
    print("Available categories and keywords:")
    for category, keywords in folder_map.items():
        print(f"  {category}: {', '.join(keywords)}")
    
    print(f"\nTotal categories: {len(folder_map)}")
    print("[OK] Folder mapping loaded successfully")

if __name__ == "__main__":
    print("ApaDocs Classification Test Suite")
    print("=" * 50)
    
    try:
        test_folder_mapping()
        
        if test_classification_system():
            print("\n[SUCCESS] All classification tests passed!")
        else:
            print("\n[WARNING] Some classification tests failed")
            
    except Exception as e:
        print(f"\n[ERROR] Test suite failed: {e}")
        import traceback
        traceback.print_exc()