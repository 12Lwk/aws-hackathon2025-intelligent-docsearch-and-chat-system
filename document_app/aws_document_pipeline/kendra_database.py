import boto3
import json
import uuid
import logging
from datetime import datetime
from django.conf import settings

logger = logging.getLogger(__name__)

class KendraDatabase:
    def __init__(self):
        region = getattr(settings, 'AWS_REGION', 'ap-southeast-1').strip() or 'ap-southeast-1'
        print(f"*** KENDRA REGION: '{region}' ***")
        
        config = {
            'aws_access_key_id': settings.AWS_ACCESS_KEY_ID,
            'aws_secret_access_key': settings.AWS_SECRET_ACCESS_KEY,
            'region_name': region
        }
        
        if hasattr(settings, 'AWS_SESSION_TOKEN') and settings.AWS_SESSION_TOKEN:
            config['aws_session_token'] = settings.AWS_SESSION_TOKEN
        
        self.kendra_client = boto3.client('kendra', **config)
        self.sts_client = boto3.client('sts', **config)
        self.index_id = settings.AWS_KENDRA_INDEX_ID
    
    def _get_account_id(self):
        """Get AWS account ID"""
        try:
            return self.sts_client.get_caller_identity()['Account']
        except:
            return '123456789012'  # Fallback
    
    def store_document(self, document_id, filename, content, category, keywords, s3_key, file_size, file_type):
        """Store document in Kendra as primary database"""
        print(f"*** STORING IN KENDRA: {document_id} ***")
        try:
            
            document = {
                'Id': document_id,
                'Title': filename,
                'Blob': content.encode('utf-8') if content else f"Document: {filename}".encode('utf-8'),
                'ContentType': 'PLAIN_TEXT',
                'Attributes': [
                    {'Key': 'category', 'Value': {'StringValue': category}},
                    {'Key': 'keywords', 'Value': {'StringListValue': keywords[:10] if keywords else []}},
                    {'Key': 's3_key', 'Value': {'StringValue': s3_key}},
                    {'Key': 'file_size', 'Value': {'StringValue': str(file_size)}},
                    {'Key': 'file_type', 'Value': {'StringValue': file_type}},
                    {'Key': 'upload_date', 'Value': {'StringValue': datetime.now().isoformat()}},
                    {'Key': 'status', 'Value': {'StringValue': 'completed'}}
                ]
            }
            
            response = self.kendra_client.batch_put_document(
                IndexId=self.index_id,
                Documents=[document]
            )
            
            print(f"*** KENDRA STORE SUCCESS: {document_id} ***")
            print(f"*** DOCUMENT SHOULD BE SEARCHABLE IN 2-5 MINUTES ***")
            return True
            
        except Exception as e:
            print(f"*** KENDRA STORE FAILED: {e} ***")
            return False
    
    def search_documents(self, query, category_filter=None, limit=50):
        """Search documents using natural language"""
        try:
            search_params = {
                'IndexId': self.index_id,
                'QueryText': query,
                'PageSize': min(limit, 100)
            }
            
            if category_filter:
                search_params['AttributeFilter'] = {
                    'EqualsTo': {
                        'Key': 'category',
                        'Value': {'StringValue': category_filter}
                    }
                }
            
            print(f"*** KENDRA SEARCH: '{query}' ***")
            response = self.kendra_client.query(**search_params)
            print(f"*** KENDRA SEARCH RESULTS: {len(response.get('ResultItems', []))} ***")
            
            documents = []
            for item in response.get('ResultItems', []):
                doc_id = item.get('DocumentId')
                doc_title = item.get('DocumentTitle', {}).get('Text', '')
                
                # Keep the original Kendra document ID (which might be an S3 URL)
                # Don't generate fallback IDs as this causes mismatches
                if not doc_id:
                    print(f"*** WARNING: Document has no ID, skipping: {doc_title} ***")
                    continue
                
                doc = {
                    'id': doc_id,
                    'title': doc_title,
                    'excerpt': item.get('DocumentExcerpt', {}).get('Text', ''),
                    'score': item.get('ScoreAttributes', {}).get('ScoreConfidence', 'MEDIUM'),
                    'attributes': {}
                }
                
                for attr in item.get('DocumentAttributes', []):
                    key = attr.get('Key')
                    value = attr.get('Value', {})
                    if 'StringValue' in value:
                        doc['attributes'][key] = value['StringValue']
                    elif 'StringListValue' in value:
                        doc['attributes'][key] = value['StringListValue']
                
                # Only add documents with valid IDs
                if doc['id']:
                    documents.append(doc)
            
            return documents
            
        except Exception as e:
            print(f"*** KENDRA SEARCH ERROR: {e} ***")
            logger.error(f"Kendra search failed: {e}")
            return []
    
    def get_document_by_id(self, document_id):
        """Get specific document by ID"""
        try:
            print(f"*** SEARCHING FOR DOCUMENT ID: {document_id} ***")
            
            # First try direct search by document ID
            # If it's an S3 URL, also try searching by just the filename
            search_queries = [document_id]
            if document_id.startswith('s3://') and '/' in document_id:
                filename = document_id.split('/')[-1]
                search_queries.append(filename)
                print(f"*** ALSO SEARCHING BY FILENAME: {filename} ***")
            
            response = self.kendra_client.query(
                IndexId=self.index_id,
                QueryText=search_queries[0],  # Start with the full ID
                PageSize=10
            )
            
            items = response.get('ResultItems', [])
            print(f"*** FOUND {len(items)} ITEMS FOR ID SEARCH ***")
            
            # Look for exact ID match first
            for item in items:
                item_id = item.get('DocumentId')
                print(f"*** COMPARING: '{item_id}' vs '{document_id}' ***")
                
                # Try multiple ID matching strategies
                if (item_id == document_id or 
                    item_id.endswith(document_id) or 
                    document_id in item_id):
                    print(f"*** ID MATCH FOUND ***")
                    return self._format_document_item(item)
            
            # If no exact match, try title-based search
            # Clean up document_id for title search
            title_search = document_id.replace('_', ' ').replace('-', ' ')
            print(f"*** TRYING TITLE SEARCH: {title_search} ***")
            
            response = self.kendra_client.query(
                IndexId=self.index_id,
                QueryText=title_search,
                PageSize=10
            )
            
            items = response.get('ResultItems', [])
            print(f"*** FOUND {len(items)} ITEMS FOR TITLE SEARCH ***")
            
            # Look for best title match
            for item in items:
                title = item.get('DocumentTitle', {}).get('Text', '').lower()
                print(f"*** CHECKING TITLE: '{title}' against '{document_id.lower()}' ***")
                
                # Try multiple matching strategies
                if (document_id.lower() in title or 
                    title.replace(' ', '_') == document_id.lower() or
                    title.replace(' ', '') == document_id.lower().replace('_', '') or
                    any(word in title for word in document_id.lower().split('_') if len(word) > 2)):
                    print(f"*** TITLE MATCH FOUND: {title} ***")
                    return self._format_document_item(item)
            
            # Last resort: try searching for documents with similar content
            # This handles cases where the ID doesn't match but the document exists
            print(f"*** TRYING CONTENT-BASED SEARCH ***")
            
            # Create better search terms based on the document ID
            if "policy" in document_id.lower():
                content_search = "policy"
            elif "admission" in document_id.lower():
                content_search = "admission policy 2025"
            elif "interview" in document_id.lower():
                content_search = "interview process"
            elif "maintenance" in document_id.lower():
                content_search = "maintenance manual"
            else:
                content_search = document_id.replace('_', ' ').replace('-', ' ').replace('pdf', '')
            
            response = self.kendra_client.query(
                IndexId=self.index_id,
                QueryText=content_search,
                PageSize=10
            )
            
            items = response.get('ResultItems', [])
            print(f"*** FOUND {len(items)} ITEMS FOR CONTENT SEARCH ***")
            
            # Look for the best match by checking if the document_id is contained in the full ID
            for item in items:
                item_id = item.get('DocumentId', '')
                item_title = item.get('DocumentTitle', {}).get('Text', '')
                print(f"*** CHECKING CONTENT MATCH: ID='{item_id}', Title='{item_title}' ***")
                
                # More precise matching - check if the exact document ID/title matches
                if (item_id == document_id or 
                    item_title == document_id or
                    document_id in item_id or
                    # Check if the filename part matches
                    item_id.endswith(document_id) or
                    item_title == document_id.split('/')[-1] if '/' in document_id else False):
                    print(f"*** EXACT CONTENT MATCH FOUND ***")
                    return self._format_document_item(item)
            
            # Return the first result if any
            if items:
                print(f"*** RETURNING FIRST CONTENT RESULT ***")
                return self._format_document_item(items[0])
            
            print(f"*** NO DOCUMENT FOUND FOR ID: {document_id} ***")
            return None
            
        except Exception as e:
            print(f"*** ERROR IN get_document_by_id: {e} ***")
            logger.error(f"Failed to get document {document_id}: {e}")
            return None
    
    def _format_document_item(self, item):
        """Format a Kendra result item into document format"""
        doc_id = item.get('DocumentId')
        doc_title = item.get('DocumentTitle', {}).get('Text', '')
        doc_content = item.get('DocumentExcerpt', {}).get('Text', '')
        
        print(f"*** FORMATTING DOCUMENT: ID={doc_id}, Title={doc_title} ***")
        
        doc = {
            'id': doc_id,
            'title': doc_title,
            'content': doc_content,
            'excerpt': doc_content,
            'attributes': {}
        }
        
        # Extract attributes
        for attr in item.get('DocumentAttributes', []):
            key = attr.get('Key')
            value = attr.get('Value', {})
            if 'StringValue' in value:
                doc['attributes'][key] = value['StringValue']
            elif 'StringListValue' in value:
                doc['attributes'][key] = value['StringListValue']
        
        print(f"*** DOCUMENT FORMATTED WITH {len(doc_content)} CHARS OF CONTENT ***")
        print(f"*** CONTENT PREVIEW: {doc_content[:100]}... ***")
        return doc
    
    def list_documents_by_category(self, category, limit=50):
        """List all documents in a category"""
        try:
            response = self.kendra_client.query(
                IndexId=self.index_id,
                QueryText='*',
                AttributeFilter={
                    'EqualsTo': {
                        'Key': 'category',
                        'Value': {'StringValue': category}
                    }
                },
                PageSize=limit
            )
            
            documents = []
            for item in response.get('ResultItems', []):
                doc = {
                    'id': item.get('DocumentId'),
                    'title': item.get('DocumentTitle', {}).get('Text', ''),
                    'excerpt': item.get('DocumentExcerpt', {}).get('Text', ''),
                    'attributes': {}
                }
                
                for attr in item.get('DocumentAttributes', []):
                    key = attr.get('Key')
                    value = attr.get('Value', {})
                    if 'StringValue' in value:
                        doc['attributes'][key] = value['StringValue']
                    elif 'StringListValue' in value:
                        doc['attributes'][key] = value['StringListValue']
                
                documents.append(doc)
            
            return documents
            
        except Exception as e:
            logger.error(f"Failed to list documents by category: {e}")
            return []
    
    def get_category_stats(self):
        """Get document count by category"""
        try:
            categories = ['policies_guidelines', 'operations_production', 'maintenance_technical', 'training_knowledge', 'others']
            stats = {}
            
            for category in categories:
                docs = self.list_documents_by_category(category, limit=100)
                stats[category] = len(docs)
            
            return stats
            
        except Exception as e:
            logger.error(f"Failed to get category stats: {e}")
            return {}