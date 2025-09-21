import boto3
import json
import uuid
import logging
import os
import time
from datetime import datetime
from django.conf import settings
from django.utils.text import slugify
from .kendra_database import KendraDatabase
from .dynamodb_storage import DynamoDBStorage

logger = logging.getLogger(__name__)

class DocumentPipeline:
    def __init__(self):
        base_config = {
            'aws_access_key_id': settings.AWS_ACCESS_KEY_ID,
            'aws_secret_access_key': settings.AWS_SECRET_ACCESS_KEY,
        }
        
        if hasattr(settings, 'AWS_SESSION_TOKEN') and settings.AWS_SESSION_TOKEN:
            base_config['aws_session_token'] = settings.AWS_SESSION_TOKEN
        
        s3_region = getattr(settings, 'AWS_REGION', 'ap-southeast-1').strip() or 'ap-southeast-1'
        bedrock_region = getattr(settings, 'BEDROCK_REGION', 'us-east-1').strip() or 'us-east-1'
        
        print(f"*** PIPELINE S3 REGION: '{s3_region}' ***")
        print(f"*** PIPELINE BEDROCK REGION: '{bedrock_region}' ***")
        
        s3_config = {**base_config, 'region_name': s3_region}
        bedrock_config = {**base_config, 'region_name': bedrock_region}
        
        self.s3_client = boto3.client('s3', **s3_config)
        self.bedrock_client = boto3.client('bedrock-runtime', **bedrock_config)
        self.kendra_db = KendraDatabase()  # Use Kendra for search
        self.dynamodb_storage = DynamoDBStorage()  # Use DynamoDB for storage
    
    def upload_to_s3(self, file, document_id):
        safe_filename = slugify(os.path.basename(file.name)) or f"doc_{uuid.uuid4().hex[:8]}"
        s3_key = f"documents/{document_id}/{safe_filename}"
        
        self.s3_client.upload_fileobj(
            file, settings.AWS_S3_BUCKET_NAME, s3_key,
            ExtraArgs={'ContentType': file.content_type}
        )
        return s3_key
    
    def extract_text_from_s3(self, s3_key):
        """Extract text content from S3 document using PyPDF2"""
        try:
            # Get document from S3
            response = self.s3_client.get_object(Bucket=settings.AWS_S3_BUCKET_NAME, Key=s3_key)
            document_bytes = response['Body'].read()
            
            # Use PyPDF2 to extract text from PDF
            import PyPDF2
            import io
            
            pdf_file = io.BytesIO(document_bytes)
            pdf_reader = PyPDF2.PdfReader(pdf_file)
            
            extracted_text = ""
            # Extract text from first few pages
            for page_num in range(min(3, len(pdf_reader.pages))):
                page = pdf_reader.pages[page_num]
                extracted_text += page.extract_text() + " "
            
            return extracted_text[:3000]  # Limit to first 3000 chars for Bedrock
            
        except Exception as e:
            print(f"*** PDF EXTRACTION ERROR: {e} ***")
            return None
    
    def process_with_bedrock(self, s3_key, filename):
        """Process document using Bedrock Runtime with available models"""
        try:
            model_id = getattr(settings, 'BEDROCK_MODEL_ID', None)
            print(f"*** BEDROCK MODEL ID: {model_id} ***")
            if not model_id:
                print(f"*** Using fallback classification for {filename} ***")
                return self._fallback_classification(filename, s3_key)
            
            # Extract actual document content
            document_content = self.extract_text_from_s3(s3_key)
            if document_content:
                print(f"*** EXTRACTED CONTENT: {document_content[:200]}... ***")
                content_prompt = f"Document content: {document_content}\n\n"
            else:
                print(f"*** NO CONTENT EXTRACTED, USING FILENAME ONLY ***")
                content_prompt = f"Document filename: {filename}\n\n"
            
            prompt = f"""{content_prompt}Based on the above document content, provide:
1. Extract key text content and summary
2. Identify 5-10 important keywords from the content
3. Classify into one category: policies_guidelines, operations_production, maintenance_technical, training_knowledge, or others
4. Provide confidence score (0.0-1.0)

Respond in JSON format:
{{
    "summary": "document summary",
    "keywords": ["keyword1", "keyword2"],
    "category": "category_name",
    "confidence": 0.8
}}"""
            
            # Different payload formats for different models
            if 'nova' in model_id.lower():
                body = {
                    "messages": [{"role": "user", "content": [{"text": prompt}]}],
                    "inferenceConfig": {
                        "max_new_tokens": 1000,
                        "temperature": 0.1
                    }
                }
            elif 'llama' in model_id.lower():
                body = {
                    "prompt": f"<|begin_of_text|><|start_header_id|>user<|end_header_id|>\n{prompt}<|eot_id|><|start_header_id|>assistant<|end_header_id|>",
                    "max_gen_len": 1000,
                    "temperature": 0.1,
                    "top_p": 0.9
                }
            elif 'mistral' in model_id.lower():
                body = {
                    "prompt": f"<s>[INST] {prompt} [/INST]",
                    "max_tokens": 1000,
                    "temperature": 0.1
                }
            else:  # Default format
                body = {
                    "prompt": prompt,
                    "max_tokens": 1000,
                    "temperature": 0.1
                }
            
            print(f"*** CALLING BEDROCK WITH MODEL: {model_id} ***")
            response = self.bedrock_client.invoke_model(
                modelId=model_id,
                body=json.dumps(body)
            )
            print(f"*** BEDROCK RESPONSE RECEIVED ***")
            
            result = json.loads(response['body'].read())
            
            # Extract response based on model type
            if 'nova' in model_id.lower():
                response_text = result.get('output', {}).get('message', {}).get('content', [{}])[0].get('text', '')
            elif 'llama' in model_id.lower():
                response_text = result.get('generation', '')
            elif 'mistral' in model_id.lower():
                response_text = result.get('outputs', [{}])[0].get('text', '')
            else:
                response_text = result.get('completion', result.get('text', ''))
            
            print(f"*** BEDROCK EXTRACTED TEXT: {response_text[:200]}... ***")
            
            # Parse JSON from response
            try:
                content = json.loads(response_text)
            except:
                # If JSON parsing fails, extract manually
                content = self._extract_from_text(response_text, filename)
            
            result = {
                'extracted_text': content.get('summary', f"Document: {filename}"),
                'keywords': content.get('keywords', []),
                'category': content.get('category', 'others'),
                'confidence': content.get('confidence', 0.7)
            }
            
            print(f"*** BEDROCK CLASSIFICATION: {filename} -> {result['category']} (confidence: {result['confidence']}) ***")
            print(f"*** BEDROCK KEYWORDS: {result['keywords'][:5]} ***")
            
            return result
            
        except Exception as e:
            logger.error(f"Bedrock processing failed for {s3_key}: {e}")
            return self._fallback_classification(filename, s3_key)

    def analyze_text_with_bedrock(self, text_content, filename):
        """Analyze a string of text with Bedrock to get category and keywords."""
        print(f"*** Analyzing text for filename: {filename} ***")
        try:
            model_id = getattr(settings, 'BEDROCK_MODEL_ID', None)
            if not model_id:
                print("*** No BEDROCK_MODEL_ID configured for real-time analysis. ***")
                return self._fallback_classification(filename, '')

            prompt = f"""Document content: {text_content[:3000]}\n\nBased on the document content, provide:
1. A concise summary (2-3 sentences).
2. 5-10 important keywords.
3. Classify into one category: policies_guidelines, operations_production, maintenance_technical, training_knowledge, or others.

Respond in JSON format:
{{
    "summary": "document summary",
    "keywords": ["keyword1", "keyword2"],
    "category": "category_name"
}}"""

            body = {
                "messages": [{"role": "user", "content": [{"text": prompt}]}],
                "inferenceConfig": {
                    "maxTokens": 800,
                    "temperature": 0.1,
                    "topP": 0.9
                }
            }

            response = self.bedrock_client.invoke_model(
                modelId=model_id,
                body=json.dumps(body)
            )

            result = json.loads(response['body'].read())
            response_text = result.get('output', {}).get('message', {}).get('content', [{}])[0].get('text', '')

            print(f"*** Real-time analysis response: {response_text[:200]}... ***")

            # Use regex to find the JSON block in the response
            import re
            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
            content = None

            if json_match:
                json_str = json_match.group(0)
                try:
                    content = json.loads(json_str)
                    print("*** Successfully parsed JSON from AI response. ***")
                except json.JSONDecodeError:
                    print("*** Found a JSON-like block, but failed to parse. Falling back. ***")
                    content = self._extract_from_text(response_text, filename)
            else:
                print("*** No JSON block found in AI response. Falling back. ***")
                content = self._extract_from_text(response_text, filename)

            return {
                'summary': content.get('summary', f"Analysis of {filename}"),
                'keywords': content.get('keywords', []),
                'category': content.get('category', 'others')
            }

        except Exception as e:
            logger.error(f"Real-time Bedrock analysis failed for {filename}: {e}")
            return self._fallback_classification(filename, '')
    
    def _extract_from_text(self, text, filename):
        """Extract structured data from unstructured text response"""
        try:
            keywords = []
            category = 'others'
            
            text_lower = text.lower()
            
            # Extract category
            categories = ['policies_guidelines', 'operations_production', 'maintenance_technical', 'training_knowledge']
            for cat in categories:
                if cat in text_lower:
                    category = cat
                    break
            
            # Extract keywords by looking for a line that starts with 'keywords'
            import re
            keywords_line = re.search(r'keywords[\":\s]+\[?([^\n\]]+)\]?', text_lower)
            if keywords_line:
                # Clean up the string and split into a list
                keywords_str = keywords_line.group(1).replace('"', '').replace("'", '')
                keywords = [kw.strip() for kw in keywords_str.split(',') if kw.strip()]
            else:
                # Fallback to finding quoted words if the above fails
                keyword_matches = re.findall(r'"([^"]+)"', text)
                keywords = keyword_matches[:10] if keyword_matches else []
            
            return {
                'summary': f"Analysis of {filename}",
                'keywords': keywords,
                'category': category,
                'confidence': 0.6
            }
        except:
            return {
                'summary': f"Document: {filename}",
                'keywords': [],
                'category': 'others',
                'confidence': 0.5
            }
    
    def _fallback_classification(self, filename, s3_key):
        """Simple fallback classification based on filename and path"""
        folder_map = getattr(settings, 'DOCUMENT_CATEGORIES', {
            'policies_guidelines': ['policy', 'guideline', 'procedure', 'sop'],
            'operations_production': ['operation', 'production', 'manufacturing', 'process'],
            'maintenance_technical': ['maintenance', 'technical', 'manual', 'repair'],
            'training_knowledge': ['training', 'education', 'course', 'learning'],
            'others': ['general', 'document', 'file', 'report']
        })
        
        combined_text = (filename + " " + s3_key).lower()
        
        for category, keywords in folder_map.items():
            if any(keyword in combined_text for keyword in keywords):
                return {
                    'extracted_text': f"Document: {filename}",
                    'keywords': [keyword for keyword in keywords if keyword in combined_text][:5],
                    'category': category,
                    'confidence': 0.6
                }
        
        return {
            'extracted_text': f"Document: {filename}",
            'keywords': [],
            'category': 'others',
            'confidence': 0.5
        }
    
    def process_document(self, document_id, filename, file_size, file_type, s3_key):
        """Process document and store in both Kendra and DynamoDB"""
        try:
            print(f"*** PROCESSING: {filename} ***")
            
            # Process with Bedrock for classification
            results = self.process_with_bedrock(s3_key, filename)
            
            # Store in DynamoDB after classification (primary storage)
            dynamodb_success = self.dynamodb_storage.store_document(
                document_id=document_id,
                filename=filename,
                content=results['extracted_text'],
                category=results['category'],
                keywords=results['keywords'],
                s3_key=s3_key,
                file_size=file_size,
                file_type=file_type,
                confidence=results['confidence']
            )
            
            # Also store in Kendra for search capabilities
            kendra_success = self.kendra_db.store_document(
                document_id=document_id,
                filename=filename,
                content=results['extracted_text'],
                category=results['category'],
                keywords=results['keywords'],
                s3_key=s3_key,
                file_size=file_size,
                file_type=file_type
            )
            
            # Consider success if at least one storage method works
            if dynamodb_success or kendra_success:
                print(f"*** DOCUMENT PROCESSED SUCCESSFULLY: {document_id} ***")
                print(f"*** DYNAMODB: {'✓' if dynamodb_success else '✗'}, KENDRA: {'✓' if kendra_success else '✗'} ***")
                return {
                    'status': 'completed',
                    'category': results['category'],
                    'keywords': results['keywords'],
                    'confidence': results['confidence'],
                    'storage': {
                        'dynamodb': dynamodb_success,
                        'kendra': kendra_success
                    }
                }
            else:
                print(f"*** DOCUMENT PROCESSING FAILED: {document_id} ***")
                return {'status': 'failed', 'error': 'Both DynamoDB and Kendra storage failed'}
            
        except Exception as e:
            print(f"*** PROCESSING ERROR: {e} ***")
            return {'status': 'failed', 'error': str(e)}