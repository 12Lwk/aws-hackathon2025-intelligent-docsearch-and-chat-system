import boto3
import json
import uuid
import logging
from datetime import datetime
from django.conf import settings
from decimal import Decimal

logger = logging.getLogger(__name__)

class DynamoDBStorage:
    def __init__(self):
        """Initialize DynamoDB client and table"""
        region = getattr(settings, 'AWS_REGION', 'ap-southeast-1').strip() or 'ap-southeast-1'
        print(f"*** DYNAMODB REGION: '{region}' ***")
        
        config = {
            'aws_access_key_id': settings.AWS_ACCESS_KEY_ID,
            'aws_secret_access_key': settings.AWS_SECRET_ACCESS_KEY,
            'region_name': region
        }
        
        if hasattr(settings, 'AWS_SESSION_TOKEN') and settings.AWS_SESSION_TOKEN:
            config['aws_session_token'] = settings.AWS_SESSION_TOKEN
        
        self.dynamodb = boto3.resource('dynamodb', **config)
        self.table_name = 'Documents'
        self.table = self.dynamodb.Table(self.table_name)
        
        # Connect to existing table
        self._connect_to_existing_table()
    
    def _connect_to_existing_table(self):
        """Connect to existing DynamoDB table"""
        try:
            # Check if table exists and is accessible
            self.table.load()
            print(f"*** CONNECTED TO EXISTING DYNAMODB TABLE '{self.table_name}' ***")
            print(f"*** TABLE STATUS: {self.table.table_status} ***")
            print(f"*** ITEM COUNT: {self.table.item_count} ***")
            self.table_accessible = True
        except Exception as e:
            print(f"*** ERROR CONNECTING TO DYNAMODB TABLE: {e} ***")
            if "AccessDeniedException" in str(e):
                print(f"*** DYNAMODB ACCESS DENIED - PLEASE ADD PERMISSIONS ***")
                print(f"*** REQUIRED PERMISSIONS: dynamodb:DescribeTable, dynamodb:GetItem, dynamodb:PutItem ***")
                print(f"*** CONTINUING WITH KENDRA-ONLY MODE ***")
            else:
                print(f"*** PLEASE ENSURE TABLE '{self.table_name}' EXISTS IN REGION: ap-southeast-1 ***")
            self.table_accessible = False
    
    def store_document(self, document_id, filename, content, category, keywords, 
                      s3_key, file_size, file_type, confidence=0.0):
        """Store document metadata in DynamoDB after classification"""
        # Check if DynamoDB is accessible
        if not hasattr(self, 'table_accessible') or not self.table_accessible:
            print(f"*** DYNAMODB NOT ACCESSIBLE - SKIPPING STORAGE FOR: {document_id} ***")
            return False
            
        try:
            print(f"*** STORING DOCUMENT IN DYNAMODB: {document_id} ***")
            
            # Convert file_size to number if it's a string
            if isinstance(file_size, str):
                try:
                    file_size = int(file_size)
                except:
                    file_size = 0
            
            # Prepare item for DynamoDB (use DocumentID to match table schema)
            item = {
                'DocumentID': document_id,  # Match your table's partition key
                'filename': filename,
                'title': filename,  # Use filename as title
                'content_summary': content[:1000] if content else f"Document: {filename}",  # First 1000 chars
                'category': category,
                'keywords': keywords if keywords else [],
                's3_key': s3_key,
                'file_size': file_size,
                'file_type': file_type,
                'confidence_score': Decimal(str(confidence)),
                'upload_date': datetime.now().isoformat(),
                'status': 'completed',
                'created_at': datetime.now().isoformat(),
                'updated_at': datetime.now().isoformat()
            }
            
            # Store in DynamoDB
            response = self.table.put_item(Item=item)
            
            print(f"*** DOCUMENT STORED IN DYNAMODB SUCCESSFULLY: {document_id} ***")
            print(f"*** CATEGORY: {category}, KEYWORDS: {keywords[:3]} ***")
            
            return True
            
        except Exception as e:
            print(f"*** DYNAMODB STORAGE FAILED: {e} ***")
            logger.error(f"Failed to store document in DynamoDB: {e}")
            return False
    
    def get_document_by_id(self, document_id):
        """Retrieve document by ID from DynamoDB"""
        # Check if DynamoDB is accessible
        if not hasattr(self, 'table_accessible') or not self.table_accessible:
            print(f"*** DYNAMODB NOT ACCESSIBLE - SKIPPING RETRIEVAL FOR: {document_id} ***")
            return None
            
        try:
            print(f"*** RETRIEVING DOCUMENT FROM DYNAMODB: {document_id} ***")
            
            response = self.table.get_item(
                Key={'DocumentID': document_id}  # Match your table's partition key
            )
            
            if 'Item' in response:
                item = response['Item']
                print(f"*** DOCUMENT FOUND IN DYNAMODB: {item['filename']} ***")
                
                # Convert Decimal to float for JSON serialization
                if 'confidence_score' in item:
                    item['confidence_score'] = float(item['confidence_score'])
                
                return item
            else:
                print(f"*** DOCUMENT NOT FOUND IN DYNAMODB: {document_id} ***")
                return None
                
        except Exception as e:
            print(f"*** DYNAMODB RETRIEVAL ERROR: {e} ***")
            logger.error(f"Failed to retrieve document from DynamoDB: {e}")
            return None
    
    def list_documents_by_category(self, category, limit=50):
        """List documents by category using scan (no GSI available)"""
        # Check if DynamoDB is accessible
        if not hasattr(self, 'table_accessible') or not self.table_accessible:
            print(f"*** DYNAMODB NOT ACCESSIBLE - SKIPPING CATEGORY SCAN FOR: {category} ***")
            return []
            
        try:
            print(f"*** LISTING DOCUMENTS BY CATEGORY: {category} ***")
            
            # Since no GSI exists, use scan with filter
            response = self.table.scan(
                FilterExpression='category = :category',
                ExpressionAttributeValues={
                    ':category': category
                },
                Limit=limit
            )
            
            print(f"*** DYNAMODB SCAN RESPONSE: {response.get('Count', 0)} items found ***")
            print(f"*** SCAN FILTER: category = {category} ***")
            
            documents = response.get('Items', [])
            
            # Debug: Show what documents we found
            for i, doc in enumerate(documents):
                print(f"*** DOCUMENT {i+1}: ID={doc.get('DocumentID', 'N/A')}, category={doc.get('category', 'N/A')}, filename={doc.get('filename', 'N/A')} ***")
            
            # Convert Decimal to float for JSON serialization
            for doc in documents:
                if 'confidence_score' in doc:
                    doc['confidence_score'] = float(doc['confidence_score'])
            
            # Sort by upload_date descending (since we can't use GSI sorting)
            documents.sort(key=lambda x: x.get('upload_date', ''), reverse=True)
            
            print(f"*** FOUND {len(documents)} DOCUMENTS IN CATEGORY: {category} ***")
            return documents
            
        except Exception as e:
            print(f"*** DYNAMODB CATEGORY SCAN ERROR: {e} ***")
            logger.error(f"Failed to list documents by category: {e}")
            return []
    
    def get_all_documents(self, limit=100):
        """Get all documents with pagination"""
        # Check if DynamoDB is accessible
        if not hasattr(self, 'table_accessible') or not self.table_accessible:
            print(f"*** DYNAMODB NOT ACCESSIBLE - SKIPPING ALL DOCUMENTS SCAN ***")
            return []
            
        try:
            print(f"*** RETRIEVING ALL DOCUMENTS FROM DYNAMODB ***")
            
            response = self.table.scan(Limit=limit)
            documents = response.get('Items', [])
            
            # Debug: Show all documents in DynamoDB
            for i, doc in enumerate(documents):
                print(f"*** ALL DOCS {i+1}: ID={doc.get('DocumentID', 'N/A')}, category={doc.get('category', 'N/A')}, filename={doc.get('filename', 'N/A')} ***")
            
            # Convert Decimal to float for JSON serialization
            for doc in documents:
                if 'confidence_score' in doc:
                    doc['confidence_score'] = float(doc['confidence_score'])
            
            print(f"*** FOUND {len(documents)} TOTAL DOCUMENTS ***")
            return documents
            
        except Exception as e:
            print(f"*** DYNAMODB SCAN ERROR: {e} ***")
            logger.error(f"Failed to scan all documents: {e}")
            return []
    
    def get_category_stats(self):
        """Get document count by category using scan (no GSI available)"""
        try:
            print(f"*** CALCULATING CATEGORY STATISTICS ***")
            
            categories = ['policies_guidelines', 'operations_production', 
                         'maintenance_technical', 'training_knowledge', 'others']
            stats = {}
            
            # Get all documents and count by category
            all_documents = self.get_all_documents(1000)  # Get more for accurate stats
            
            # Initialize all categories to 0
            for category in categories:
                stats[category] = 0
            
            # Count documents by category
            for doc in all_documents:
                category = doc.get('category', 'others')
                if category in stats:
                    stats[category] += 1
                else:
                    stats['others'] += 1  # Fallback for unknown categories
            
            print(f"*** CATEGORY STATS: {stats} ***")
            return stats
            
        except Exception as e:
            print(f"*** CATEGORY STATS ERROR: {e} ***")
            logger.error(f"Failed to get category stats: {e}")
            return {}
    
    def search_documents(self, query, category_filter=None, limit=50):
        """Search documents by content or filename"""
        try:
            print(f"*** SEARCHING DOCUMENTS: '{query}' ***")
            
            # Build filter expression
            filter_expression = None
            expression_values = {}
            
            if query and query != '*':
                # Search in filename and content_summary
                filter_expression = 'contains(filename, :query) OR contains(content_summary, :query)'
                expression_values[':query'] = query
            
            if category_filter:
                if filter_expression:
                    filter_expression += ' AND category = :category'
                else:
                    filter_expression = 'category = :category'
                expression_values[':category'] = category_filter
            
            scan_params = {
                'Limit': limit
            }
            
            if filter_expression:
                scan_params['FilterExpression'] = filter_expression
                scan_params['ExpressionAttributeValues'] = expression_values
            
            response = self.table.scan(**scan_params)
            documents = response.get('Items', [])
            
            # Convert Decimal to float for JSON serialization
            for doc in documents:
                if 'confidence_score' in doc:
                    doc['confidence_score'] = float(doc['confidence_score'])
            
            print(f"*** SEARCH FOUND {len(documents)} DOCUMENTS ***")
            return documents
            
        except Exception as e:
            print(f"*** DYNAMODB SEARCH ERROR: {e} ***")
            logger.error(f"Failed to search documents: {e}")
            return []
    
    def update_document(self, document_id, updates):
        """Update document metadata"""
        try:
            print(f"*** UPDATING DOCUMENT: {document_id} ***")
            
            # Build update expression
            update_expression = "SET updated_at = :updated_at"
            expression_values = {':updated_at': datetime.now().isoformat()}
            
            for key, value in updates.items():
                if key not in ['document_id']:  # Don't update primary key
                    update_expression += f", {key} = :{key}"
                    expression_values[f':{key}'] = value
            
            response = self.table.update_item(
                Key={'DocumentID': document_id},  # Match your table's partition key
                UpdateExpression=update_expression,
                ExpressionAttributeValues=expression_values,
                ReturnValues='UPDATED_NEW'
            )
            
            print(f"*** DOCUMENT UPDATED SUCCESSFULLY: {document_id} ***")
            return True
            
        except Exception as e:
            print(f"*** DYNAMODB UPDATE ERROR: {e} ***")
            logger.error(f"Failed to update document: {e}")
            return False
    
    def delete_document(self, document_id):
        """Delete document from DynamoDB"""
        try:
            print(f"*** DELETING DOCUMENT: {document_id} ***")
            
            response = self.table.delete_item(
                Key={'DocumentID': document_id}  # Match your table's partition key
            )
            
            print(f"*** DOCUMENT DELETED SUCCESSFULLY: {document_id} ***")
            return True
            
        except Exception as e:
            print(f"*** DYNAMODB DELETE ERROR: {e} ***")
            logger.error(f"Failed to delete document: {e}")
            return False
