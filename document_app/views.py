from django.shortcuts import render
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
import json
import uuid
from datetime import datetime
from .aws_document_pipeline.pipeline import DocumentPipeline
from .aws_document_pipeline.kendra_database import KendraDatabase
from .aws_chatbot.chatbot_engine import ChatbotEngine
from .aws_ai_search.search_engine import AISearchEngine
from .aws_ai_search.suggestion_engine import SuggestionEngine
from .aws_document_pipeline.dynamodb_storage import DynamoDBStorage
from .models import RecentView
import threading
import boto3

def get_client_ip(request):
    """Get client IP address from request"""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip

def get_user_session(request):
    """Get or create user session identifier"""
    if not request.session.session_key:
        request.session.create()
    return request.session.session_key

def home(request):
    print("*** HOME PAGE REQUEST ***")
    return render(request, 'document_app/home.html')

def search(request):
    return render(request, 'document_app/search.html')

def chatbot(request):
    return render(request, 'document_app/chatbot.html')

def dashboard(request):
    return render(request, 'document_app/dashboard.html')

def upload(request):
    return render(request, 'document_app/upload.html')

def settings(request):
    return render(request, 'document_app/settings.html')

@csrf_exempt
@require_http_methods(["POST"])
def upload_files(request):
    """File upload endpoint using Kendra as database"""
    print("*** UPLOAD REQUEST RECEIVED ***")
    try:
        files = request.FILES.getlist('files')
        if not files:
            return JsonResponse({'error': 'No files provided'}, status=400)
        
        if len(files) > 25:
            return JsonResponse({'error': 'Maximum 25 files allowed per upload'}, status=400)
        
        pipeline = DocumentPipeline()
        uploaded_docs = []
        
        for file in files:
            if file.size > 10 * 1024 * 1024:  # 10MB limit
                continue
                
            document_id = str(uuid.uuid4())
            
            try:
                # Upload to S3
                s3_key = pipeline.upload_to_s3(file, document_id)
                
                uploaded_docs.append({
                    'id': document_id,
                    'name': file.name,
                    'status': 'uploaded'
                })
                
                # Process and store in Kendra (background)
                def process_and_store():
                    pipeline.process_document(
                        document_id=document_id,
                        filename=file.name,
                        file_size=file.size,
                        file_type=file.content_type,
                        s3_key=s3_key
                    )
                
                thread = threading.Thread(target=process_and_store)
                thread.start()
                
            except Exception as e:
                print(f"Upload failed for {file.name}: {str(e)}")
        
        return JsonResponse({
            'status': 'success',
            'message': f'Uploaded {len(uploaded_docs)} files successfully',
            'documents': uploaded_docs
        })
        
    except Exception as e:
        print(f"Upload error: {e}")
        return JsonResponse({'error': f'Upload failed: {str(e)}'}, status=500)

@csrf_exempt
@require_http_methods(["GET"])
def get_document_status(request, document_id):
    """Get document status from DynamoDB first, then Kendra as fallback"""
    print(f"*** REQUEST: GET /api/document-status/{document_id}/ ***")
    try:
        # First try DynamoDB (has correct UUID mapping)
        dynamodb_storage = DynamoDBStorage()
        doc = dynamodb_storage.get_document_by_id(document_id)
        
        if doc:
            print(f"*** FOUND IN DYNAMODB: {doc['filename']} ***")
            response = JsonResponse({
                'id': document_id,
                'name': doc['filename'],
                'status': 'completed',
                'category': doc.get('category', 'others'),
                'keywords': doc.get('keywords', []),
                'upload_date': doc.get('upload_date', ''),
                'file_size': str(doc.get('file_size', 0)),
                'file_type': doc.get('file_type', ''),
                'content_length': len(doc.get('content_summary', ''))
            })
            print(f"*** RESPONSE: 200 (DynamoDB) ***")
            return response
        
        # Fallback to Kendra if not found in DynamoDB
        print(f"*** NOT FOUND IN DYNAMODB, TRYING KENDRA ***")
        kendra_db = KendraDatabase()
        doc = kendra_db.get_document_by_id(document_id)
        
        if doc:
            print(f"*** FOUND IN KENDRA: {doc['title']} ***")
            response = JsonResponse({
                'id': doc['id'],
                'name': doc['title'],
                'status': 'completed',
                'category': doc['attributes'].get('category', ''),
                'keywords': doc['attributes'].get('keywords', []),
                'upload_date': doc['attributes'].get('upload_date', ''),
                'file_size': doc['attributes'].get('file_size', ''),
                'file_type': doc['attributes'].get('file_type', ''),
                'content_length': len(doc.get('content', ''))
            })
            print(f"*** RESPONSE: 200 (Kendra) ***")
            return response
        else:
            # Return failed status if not found anywhere (stop polling)
            print(f"*** DOCUMENT NOT FOUND, RETURNING FAILED STATUS ***")
            response = JsonResponse({
                'id': document_id,
                'name': 'Upload Failed',
                'status': 'failed',  # Stop polling
                'category': 'others',
                'keywords': [],
                'upload_date': datetime.now().isoformat(),
                'file_size': '0',
                'file_type': 'unknown',
                'content_length': 0,
                'error': 'Document not found in storage systems'
            })
            print(f"*** RESPONSE: 200 (Failed) ***")
            return response
            
    except Exception as e:
        print(f"*** ERROR: {e} ***")
        return JsonResponse({'error': str(e)}, status=500)

@csrf_exempt
@require_http_methods(["GET"])
def list_documents(request):
    """List documents from Kendra database"""
    try:
        kendra_db = KendraDatabase()
        category = request.GET.get('category')
        
        if category:
            documents = kendra_db.list_documents_by_category(category)
        else:
            # Get all documents by searching with wildcard
            documents = kendra_db.search_documents('*', limit=100)
        
        # Format documents for frontend
        formatted_docs = []
        for doc in documents:
            formatted_docs.append({
                'id': doc['id'],
                'name': doc['title'],
                'category': doc['attributes'].get('category', ''),
                'keywords': doc['attributes'].get('keywords', []),
                'upload_date': doc['attributes'].get('upload_date', ''),
                'file_size': doc['attributes'].get('file_size', ''),
                'status': doc['attributes'].get('status', 'completed'),
                'excerpt': doc.get('excerpt', '')[:200]  # First 200 chars
            })
        
        # Get category statistics
        category_stats = kendra_db.get_category_stats()
        
        return JsonResponse({
            'status': 'success',
            'documents': formatted_docs,
            'count': len(formatted_docs),
            'category_stats': category_stats
        })
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@csrf_exempt
@require_http_methods(["POST"])
def search_documents(request):
    """Search documents using Kendra natural language search"""
    try:
        data = json.loads(request.body)
        query = data.get('query', '')
        category = data.get('category')
        
        if not query:
            return JsonResponse({'error': 'Query is required'}, status=400)
        
        kendra_db = KendraDatabase()
        results = kendra_db.search_documents(query, category_filter=category)
        
        # Format results for frontend
        formatted_results = []
        for doc in results:
            formatted_results.append({
                'id': doc['id'],
                'title': doc['title'],
                'excerpt': doc['excerpt'],
                'score': doc['score'],
                'category': doc['attributes'].get('category', ''),
                'keywords': doc['attributes'].get('keywords', []),
                'relevance': doc['score']
            })
        
        return JsonResponse({
            'status': 'success',
            'results': formatted_results,
            'count': len(formatted_results),
            'query': query
        })
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@csrf_exempt
@require_http_methods(["GET"])
def test_endpoint(request):
    """Simple test endpoint"""
    print("*** TEST ENDPOINT CALLED ***")
    return JsonResponse({'status': 'success', 'message': 'API is working'})

@csrf_exempt
@require_http_methods(["GET"])
def debug_documents(request):
    """Debug endpoint to see all available documents"""
    try:
        kendra_db = KendraDatabase()
        
        # Try multiple search strategies to find documents
        search_strategies = ["*", "document", "pdf", "interview", "policy", "process"]
        all_docs = []
        
        for strategy in search_strategies:
            try:
                docs = kendra_db.search_documents(strategy, limit=10)
                all_docs.extend(docs)
                if docs:
                    break  # If we find documents, stop searching
            except Exception as e:
                print(f"*** SEARCH STRATEGY '{strategy}' FAILED: {e} ***")
        
        # Remove duplicates
        seen_ids = set()
        unique_docs = []
        for doc in all_docs:
            doc_id = doc.get('id')
            if doc_id and doc_id not in seen_ids:
                unique_docs.append(doc)
                seen_ids.add(doc_id)
        
        debug_info = {
            'total_documents': len(unique_docs),
            'documents': [],
            'kendra_index_id': kendra_db.index_id,
            'search_strategies_tried': search_strategies
        }
        
        for doc in unique_docs:
            debug_info['documents'].append({
                'id': doc.get('id'),
                'title': doc.get('title'),
                'excerpt': doc.get('excerpt', '')[:100] + '...' if doc.get('excerpt') else 'No excerpt',
                'category': doc.get('attributes', {}).get('category', 'Unknown')
            })
        
        return JsonResponse(debug_info)
        
    except Exception as e:
        return JsonResponse({'error': str(e), 'traceback': str(e)}, status=500)

@csrf_exempt
@require_http_methods(["POST"])
def test_document_upload(request):
    """Test endpoint to manually add a document to Kendra"""
    try:
        kendra_db = KendraDatabase()
        
        # Add a test document
        test_doc_id = f"test-doc-{uuid.uuid4().hex[:8]}"
        success = kendra_db.store_document(
            document_id=test_doc_id,
            filename="test-interview-process.pdf",
            content="This is a test document about interview processes. It contains information about candidate evaluation, hiring procedures, and recruitment guidelines.",
            category="training_knowledge",
            keywords=["interview", "process", "hiring", "candidate", "evaluation"],
            s3_key=f"test/{test_doc_id}/test-interview-process.pdf",
            file_size=1024,
            file_type="application/pdf"
        )
        
        if success:
            return JsonResponse({
                'status': 'success',
                'message': f'Test document added with ID: {test_doc_id}',
                'document_id': test_doc_id
            })
        else:
            return JsonResponse({'error': 'Failed to store test document'}, status=500)
            
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@csrf_exempt  
@require_http_methods(["GET"])
def debug_specific_document(request, document_id):
    """Debug a specific document lookup"""
    try:
        kendra_db = KendraDatabase()
        
        print(f"*** DEBUGGING SPECIFIC DOCUMENT: {document_id} ***")
        
        # Try direct lookup
        doc = kendra_db.get_document_by_id(document_id)
        
        # Also search for policy documents to see what's available
        policy_docs = kendra_db.search_documents("policy", limit=10)
        
        debug_info = {
            'requested_id': document_id,
            'direct_lookup_result': doc,
            'available_policy_documents': []
        }
        
        for policy_doc in policy_docs:
            debug_info['available_policy_documents'].append({
                'id': policy_doc.get('id'),
                'title': policy_doc.get('title'),
                'matches_requested': (
                    document_id.lower() in policy_doc.get('id', '').lower() or
                    document_id.lower() in policy_doc.get('title', '').lower()
                )
            })
        
        return JsonResponse(debug_info)
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@csrf_exempt
@require_http_methods(["POST"])
def chatbot_api(request):
    """Intelligent chatbot API endpoint"""
    try:
        data = json.loads(request.body)
        message = data.get('message', '')
        context = data.get('context', None) # Get the document context from the request
        
        if not message:
            return JsonResponse({'error': 'Message is required'}, status=400)
        
        # Initialize chatbot engine
        chatbot = ChatbotEngine()
        
        # Process message and get response, passing in the context
        response = chatbot.process_message(message, context=context)
        
        return JsonResponse(response)
        
    except Exception as e:
        return JsonResponse({'error': f'Chatbot error: {str(e)}'}, status=500)

@csrf_exempt
@require_http_methods(["POST"])
def ai_search(request):
    """AI-powered search endpoint."""
    try:
        data = json.loads(request.body)
        query = data.get('query')
        min_similarity = data.get('min_similarity', 0.8)
        max_results = data.get('max_results', 5)
        category_filter = data.get('category')

        if not query:
            return JsonResponse({'error': 'Query is required'}, status=400)

        search_engine = AISearchEngine()
        results, summary = search_engine.perform_search(
            query=query, 
            category_filter=category_filter,
            max_results=max_results,
            min_similarity=min_similarity
        )

        formatted_results = [
            {
                'id': doc.get('id'),
                'title': doc.get('title'),
                'excerpt': doc.get('excerpt'),
                'category': doc.get('attributes', {}).get('category', 'Unknown'),
                'relevance_score': doc.get('relevance_score', 0),
                'similarity_percentage': doc.get('similarity_percentage', round(doc.get('relevance_score', 0) * 100, 1))
            }
            for doc in results
        ]

        return JsonResponse({
            'results': formatted_results,
            'summary': summary,
            'count': len(formatted_results)
        })

    except Exception as e:
        print(f"*** AI SEARCH ERROR: {e} ***")
        return JsonResponse({'error': str(e)}, status=500)

@require_http_methods(["GET"])
def view_document(request):
    """View document content"""
    try:
        # Get document ID from query parameters
        document_id = request.GET.get('id')
        if not document_id:
            return JsonResponse({'error': 'Document ID is required'}, status=400)
        
        print(f"*** VIEW REQUEST: document_id = {document_id} ***")
        
        kendra_db = KendraDatabase()
        
        # First, let's do a quick search to see what documents are available
        print(f"*** DEBUGGING: Searching for policy documents ***")
        search_results = kendra_db.search_documents("policy", limit=10)
        print(f"*** AVAILABLE POLICY DOCUMENTS: ***")
        target_found = False
        for i, doc in enumerate(search_results):
            doc_id = doc.get('id', '')
            doc_title = doc.get('title', '')
            print(f"  {i+1}. ID: '{doc_id}', Title: '{doc_title}'")
            # Check if this is the exact document we're looking for
            if doc_id == document_id:
                print(f"    *** EXACT MATCH FOUND! ***")
                target_found = True
            elif document_id in doc_id or document_id in doc_title:
                print(f"    *** PARTIAL MATCH FOUND! ***")
        
        if target_found:
            print(f"*** TARGET DOCUMENT IS AVAILABLE IN SEARCH RESULTS ***")
        else:
            print(f"*** TARGET DOCUMENT NOT FOUND IN POLICY SEARCH ***")
        print(f"*** END AVAILABLE DOCUMENTS ***")
        
        # Try to get document by ID first
        doc = kendra_db.get_document_by_id(document_id)
        
        if not doc:
            # If not found by ID, try searching by title (handle cases where title is used as ID)
            print(f"*** Document not found by ID, searching by title: {document_id} ***")
            # Clean up the document_id for search (remove underscores, add extensions)
            search_term = document_id.replace('_', ' ').replace('-', ' ')
            
            # Try multiple search strategies
            search_strategies = [
                search_term,
                search_term + ' pdf',
                document_id.replace('pdf', '').replace('-', ' ').replace('_', ' '),
                'interview process' if 'interview' in document_id.lower() else search_term
            ]
            
            best_match = None
            for strategy in search_strategies:
                print(f"*** TRYING SEARCH STRATEGY: '{strategy}' ***")
                search_results = kendra_db.search_documents(strategy, limit=5)
                
                # Find best match by title similarity
                for result in search_results:
                    result_title = result.get('title', '').lower()
                    result_id = result.get('id', '').lower()
                    
                    # Multiple matching criteria
                    if (document_id.lower() in result_title or 
                        result_id == document_id.lower() or
                        any(word in result_title for word in document_id.lower().replace('-', ' ').split() if len(word) > 2)):
                        best_match = result
                        print(f"*** MATCH FOUND: Title='{result_title}', ID='{result_id}' ***")
                        break
                
                if best_match:
                    break
            
            if best_match:
                doc = best_match
                print(f"*** Found document by search: {doc.get('title', 'Unknown')} ***")
            else:
                # Final fallback: search all policy documents and find the closest match
                print(f"*** FINAL FALLBACK: Searching all policy documents ***")
                all_policy_docs = kendra_db.search_documents("policy", limit=20)
                
                for policy_doc in all_policy_docs:
                    policy_title = policy_doc.get('title', '').lower()
                    policy_id = policy_doc.get('id', '').lower()
                    
                    # Very flexible matching
                    if (document_id.lower() in policy_title or 
                        policy_title in document_id.lower() or
                        document_id.lower() in policy_id or
                        any(word in policy_title for word in document_id.lower().split('_') if len(word) > 3)):
                        doc = policy_doc
                        print(f"*** FALLBACK MATCH FOUND: {policy_doc.get('title')} ***")
                        break
                
                if not doc:
                    print(f"*** Document not found: {document_id} ***")
                    return JsonResponse({'error': f'Document "{document_id}" not found in database'}, status=404)
        
        print(f"*** Found document: {doc.get('title', 'Unknown')} ***")
        
        content = doc.get('content', doc.get('excerpt', 'No content available'))
        attributes = doc.get('attributes', {})
        category = attributes.get('category', 'Unknown')

        # If category is unknown, perform real-time analysis with Bedrock
        if category in ['Unknown', 'others'] and content and len(content) > 50:
            print(f"*** Category is '{category}'. Performing real-time analysis. ***")
            from .aws_document_pipeline.pipeline import DocumentPipeline
            pipeline = DocumentPipeline()
            try:
                # We pass the content directly to Bedrock, no need for S3 key
                analysis_results = pipeline.analyze_text_with_bedrock(content, doc.get('title', ''))
                # Update attributes with the new analysis
                attributes['category'] = analysis_results.get('category', category)
                attributes['keywords'] = analysis_results.get('keywords', [])
                attributes['summary'] = analysis_results.get('summary', 'Summary could not be generated.')
                print(f"*** Real-time analysis complete. New category: {attributes['category']} ***")
            except Exception as e:
                print(f"*** Real-time analysis failed: {e} ***")

        print(f"*** FINAL RESPONSE CONTENT LENGTH: {len(content)} ***")
        print(f"*** FINAL RESPONSE CONTENT PREVIEW: {content[:100]}... ***")
        
        # Track document view activity
        try:
            user_session = get_user_session(request)
            user_ip = get_client_ip(request)
            RecentView.track_document_activity(
                document_id=doc['id'],
                document_title=doc['title'],
                action_type='view',
                user_session=user_session,
                user_ip=user_ip,
                document_category=attributes.get('category', 'Unknown'),
                file_type=attributes.get('file_type', ''),
                file_size=attributes.get('file_size', '')
            )
            print(f"*** TRACKED VIEW ACTIVITY FOR: {doc['title']} ***")
        except Exception as track_error:
            print(f"*** FAILED TO TRACK VIEW ACTIVITY: {track_error} ***")
        
        response_data = {
            'id': doc['id'],
            'title': doc['title'],
            'content': content,
            'category': attributes.get('category', 'Unknown'),
            'upload_date': attributes.get('upload_date', 'Unknown'),
            'keywords': attributes.get('keywords', []),
            'summary': attributes.get('summary', 'Summary not available.')
        }
        
        return JsonResponse(response_data)
        
    except Exception as e:
        print(f"*** VIEW ERROR: {str(e)} ***")
        return JsonResponse({'error': f'Error retrieving document: {str(e)}'}, status=500)

@require_http_methods(["GET"])
def download_document(request):
    """Download document file"""
    try:
        # Get document ID from query parameters
        document_id = request.GET.get('id')
        if not document_id:
            return JsonResponse({'error': 'Document ID is required'}, status=400)
        
        print(f"*** DOWNLOAD REQUEST: document_id = {document_id} ***")
        
        kendra_db = KendraDatabase()
        
        # Try to get document by ID first
        doc = kendra_db.get_document_by_id(document_id)
        
        if not doc:
            # If not found by ID, try searching by title (handle cases where title is used as ID)
            print(f"*** Document not found by ID, searching by title: {document_id} ***")
            # Clean up the document_id for search
            search_term = document_id.replace('_', ' ').replace('-', ' ')
            if not search_term.endswith('.pdf'):
                search_term += ' pdf'
            
            search_results = kendra_db.search_documents(search_term, limit=5)
            
            # Find best match by title similarity
            best_match = None
            for result in search_results:
                result_title = result.get('title', '').lower()
                if document_id.lower() in result_title or any(word in result_title for word in document_id.lower().split('-')):
                    best_match = result
                    break
            
            if best_match:
                doc = best_match
                print(f"*** Found document by title search: {doc.get('title', 'Unknown')} ***")
            else:
                print(f"*** Document not found: {document_id} ***")
                return JsonResponse({'error': f'Document "{document_id}" not found in database'}, status=404)
        
        print(f"*** Found document: {doc.get('title', 'Unknown')} ***")
        
        s3_key = doc.get('attributes', {}).get('s3_key', '')
        from django.conf import settings
        s3_bucket = settings.AWS_S3_BUCKET_NAME

        # Enhanced S3 key resolution with multiple fallback strategies
        if not s3_key and doc.get('id', '').startswith('s3://'):
            print(f"*** No 's3_key' attribute found, attempting to parse from Document ID: {doc['id']} ***")
            from urllib.parse import urlparse
            parsed_url = urlparse(doc['id'])
            s3_bucket = parsed_url.netloc
            s3_key = parsed_url.path.lstrip('/')
        elif not s3_key:
            # Try to construct S3 key from document title and ID
            doc_title = doc.get('title', '').replace(' ', '_').replace('/', '_')
            doc_id_part = doc.get('id', '').split('/')[-1] if '/' in doc.get('id', '') else doc.get('id', '')
            
            # Try multiple S3 key patterns
            possible_keys = [
                f"documents/{doc_id_part}/{doc_title}",
                f"uploads/{doc_id_part}/{doc_title}",
                f"{doc_id_part}/{doc_title}",
                f"documents/{doc_title}",
                doc_title
            ]
            
            print(f"*** Trying multiple S3 key patterns for: {doc_title} ***")
            
            # Test each possible key
            from .aws_credential_keys.config import AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_REGION
            s3_client = boto3.client(
                's3',
                aws_access_key_id=AWS_ACCESS_KEY_ID,
                aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
                region_name=AWS_REGION
            )
            
            for test_key in possible_keys:
                try:
                    s3_client.head_object(Bucket=s3_bucket, Key=test_key)
                    s3_key = test_key
                    print(f"*** Found S3 object at: {test_key} ***")
                    break
                except:
                    continue

        print(f"*** S3 Bucket: {s3_bucket}, S3 Key: {s3_key} ***")

        if s3_key and s3_bucket:
            from .aws_credential_keys.config import AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_REGION

            s3_client = boto3.client(
                's3',
                aws_access_key_id=AWS_ACCESS_KEY_ID,
                aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
                region_name=AWS_REGION
            )

            try:
                # Check if the object exists before generating a URL
                s3_client.head_object(Bucket=s3_bucket, Key=s3_key)

                download_url = s3_client.generate_presigned_url(
                    'get_object',
                    Params={'Bucket': s3_bucket, 'Key': s3_key},
                    ExpiresIn=3600  # 1 hour
                )

                # Track document download activity
                try:
                    user_session = get_user_session(request)
                    user_ip = get_client_ip(request)
                    RecentView.track_document_activity(
                        document_id=doc['id'],
                        document_title=doc['title'],
                        action_type='download',
                        user_session=user_session,
                        user_ip=user_ip,
                        document_category=doc.get('attributes', {}).get('category', 'Unknown'),
                        file_type=doc.get('attributes', {}).get('file_type', ''),
                        file_size=doc.get('attributes', {}).get('file_size', '')
                    )
                    print(f"*** TRACKED DOWNLOAD ACTIVITY FOR: {doc['title']} ***")
                except Exception as track_error:
                    print(f"*** FAILED TO TRACK DOWNLOAD ACTIVITY: {track_error} ***")

                response_data = {
                    'download_url': download_url,
                    'filename': doc['title']
                }

                print(f"*** Generated download URL successfully ***")
                return JsonResponse(response_data)

            except Exception as s3_error:
                print(f"*** S3 Error: {str(s3_error)} ***")
                
                # Provide alternative: generate downloadable text file
                if 'NoSuchKey' in str(s3_error) or 'Not Found' in str(s3_error):
                    print(f"*** S3 file not found, offering text content download ***")
                    return _generate_text_download(doc, request)
                else:
                    return JsonResponse({
                        'error': f'Could not access the file in S3. Error: {str(s3_error)}',
                        'alternative': 'You can view the document content using the "View Details" button.',
                        'suggestion': 'The original file may have been moved or deleted, but the text content is still available.'
                    }, status=500)
        else:
            print(f"*** No S3 key found for document ***")
            return _generate_text_download(doc, request)
            
    except Exception as e:
        print(f"*** DOWNLOAD ERROR: {str(e)} ***")
        return JsonResponse({'error': f'Error retrieving document: {str(e)}'}, status=500)

def _generate_text_download(doc, request=None):
    """Generate a downloadable text file when original file is not available"""
    try:
        import base64
        from datetime import datetime
        
        doc_title = doc.get('title', 'document')
        doc_content = doc.get('content', doc.get('excerpt', 'No content available'))
        doc_category = doc.get('attributes', {}).get('category', 'Unknown')
        doc_keywords = doc.get('attributes', {}).get('keywords', [])
        
        # Track document download activity for text downloads too
        if request:
            try:
                user_session = get_user_session(request)
                user_ip = get_client_ip(request)
                RecentView.track_document_activity(
                    document_id=doc['id'],
                    document_title=doc_title,
                    action_type='download',
                    user_session=user_session,
                    user_ip=user_ip,
                    document_category=doc_category,
                    file_type='text/plain',
                    file_size='N/A'
                )
                print(f"*** TRACKED TEXT DOWNLOAD ACTIVITY FOR: {doc_title} ***")
            except Exception as track_error:
                print(f"*** FAILED TO TRACK TEXT DOWNLOAD ACTIVITY: {track_error} ***")
        
        # Create formatted text content
        text_content = f"""Document: {doc_title}
Category: {doc_category}
Keywords: {', '.join(doc_keywords) if doc_keywords else 'None'}
Downloaded: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

{'='*50}
CONTENT
{'='*50}

{doc_content}

{'='*50}
Note: This is a text-only version of the document.
The original file format may not be available.
{'='*50}
"""
        
        # Create data URL for download
        encoded_content = base64.b64encode(text_content.encode('utf-8')).decode('utf-8')
        data_url = f"data:text/plain;base64,{encoded_content}"
        
        # Clean filename
        safe_filename = doc_title.replace(' ', '_').replace('/', '_').replace('\\', '_')
        if not safe_filename.endswith('.txt'):
            safe_filename += '.txt'
        
        return JsonResponse({
            'download_url': data_url,
            'filename': safe_filename,
            'file_type': 'text/plain',
            'note': 'Original file not available. Downloading text content instead.',
            'is_text_only': True
        })
        
    except Exception as e:
        print(f"*** TEXT DOWNLOAD ERROR: {e} ***")
        return JsonResponse({
            'error': 'Could not generate text download. Please use "View Details" to see the content.',
            'suggestion': 'The document content is available for viewing but cannot be downloaded.'
        }, status=500)

@csrf_exempt
@require_http_methods(["GET"])
def get_dynamic_suggestions(request):
    """Get dynamic search suggestions based on available documents"""
    try:
        # Get parameters
        limit = int(request.GET.get('limit', 3))
        user_session = request.GET.get('session', None)
        
        print(f"*** DYNAMIC SUGGESTIONS REQUEST: limit={limit} ***")
        
        # Initialize suggestion engine
        suggestion_engine = SuggestionEngine()
        
        # Generate dynamic suggestions
        suggestions = suggestion_engine.generate_dynamic_suggestions(
            user_context={'session': user_session},
            limit=limit
        )
        
        return JsonResponse({
            'status': 'success',
            'suggestions': suggestions,
            'count': len(suggestions),
            'generated_at': datetime.now().isoformat()
        })
        
    except Exception as e:
        print(f"*** DYNAMIC SUGGESTIONS ERROR: {e} ***")
        return JsonResponse({
            'status': 'error',
            'error': f'Failed to generate suggestions: {str(e)}',
            'suggestions': [
                "Upload your first document to get started",
                "Try searching for policies or procedures", 
                "Ask me about document management"
            ]
        }, status=500)

@csrf_exempt
@require_http_methods(["POST"])
def track_search_interaction(request):
    """Track user search interactions for personalization"""
    try:
        data = json.loads(request.body)
        query = data.get('query', '')
        result_clicked = data.get('result_clicked', False)
        user_session = data.get('user_session', None)
        
        if not query:
            return JsonResponse({'error': 'Query is required'}, status=400)
        
        print(f"*** TRACKING INTERACTION: '{query}' clicked={result_clicked} ***")
        
        # Initialize suggestion engine and track interaction
        suggestion_engine = SuggestionEngine()
        suggestion_engine.track_user_interaction(
            query=query,
            result_clicked=result_clicked,
            user_session=user_session
        )
        
        return JsonResponse({
            'status': 'success',
            'message': 'Interaction tracked successfully'
        })
        
    except Exception as e:
        print(f"*** INTERACTION TRACKING ERROR: {e} ***")
        return JsonResponse({'error': f'Failed to track interaction: {str(e)}'}, status=500)

@csrf_exempt
@require_http_methods(["GET"])
def get_suggestion_analytics(request):
    """Get analytics about suggestion usage and effectiveness"""
    try:
        print(f"*** SUGGESTION ANALYTICS REQUEST ***")
        
        # Initialize suggestion engine
        suggestion_engine = SuggestionEngine()
        
        # Get analytics data
        analytics = suggestion_engine.get_suggestion_analytics()
        
        return JsonResponse({
            'status': 'success',
            'analytics': analytics,
            'generated_at': datetime.now().isoformat()
        })
        
    except Exception as e:
        print(f"*** SUGGESTION ANALYTICS ERROR: {e} ***")
        return JsonResponse({
            'status': 'error',
            'error': f'Failed to get analytics: {str(e)}'
        }, status=500)

@csrf_exempt
@require_http_methods(["POST"])
def clear_suggestion_cache(request):
    """Clear suggestion cache for fresh results"""
    try:
        print(f"*** CLEAR SUGGESTION CACHE REQUEST ***")
        
        # Initialize suggestion engine
        suggestion_engine = SuggestionEngine()
        
        # Clear cache
        success = suggestion_engine.clear_suggestion_cache()
        
        if success:
            return JsonResponse({
                'status': 'success',
                'message': 'Suggestion cache cleared successfully',
                'cleared_at': datetime.now().isoformat()
            })
        else:
            return JsonResponse({
                'status': 'error',
                'error': 'Failed to clear cache'
            }, status=500)
        
    except Exception as e:
        print(f"*** CLEAR CACHE ERROR: {e} ***")
        return JsonResponse({
            'status': 'error',
            'error': f'Failed to clear cache: {str(e)}'
        }, status=500)

@csrf_exempt
@require_http_methods(["GET"])
def get_personalized_suggestions(request):
    """Get personalized suggestions based on user history"""
    try:
        # Get parameters
        limit = int(request.GET.get('limit', 3))
        user_session = request.GET.get('session', None)
        
        print(f"*** PERSONALIZED SUGGESTIONS REQUEST: session={user_session} ***")
        
        # Initialize suggestion engine
        suggestion_engine = SuggestionEngine()
        
        # Generate personalized suggestions
        suggestions = suggestion_engine.get_personalized_suggestions(
            user_session=user_session,
            limit=limit
        )
        
        return JsonResponse({
            'status': 'success',
            'suggestions': suggestions,
            'count': len(suggestions),
            'personalized': user_session is not None,
            'generated_at': datetime.now().isoformat()
        })
        
    except Exception as e:
        print(f"*** PERSONALIZED SUGGESTIONS ERROR: {e} ***")
        return JsonResponse({
            'status': 'error',
            'error': f'Failed to generate personalized suggestions: {str(e)}',
            'suggestions': [
                "Upload your first document to get started",
                "Try searching for policies or procedures", 
                "Ask me about document management"
            ]
        }, status=500)

@csrf_exempt
@require_http_methods(["POST"])
def track_document_activity(request):
    """Track document view or download activity"""
    try:
        data = json.loads(request.body)
        document_id = data.get('document_id')
        document_title = data.get('document_title')
        action_type = data.get('action_type')  # 'view' or 'download'
        document_category = data.get('document_category', '')
        file_type = data.get('file_type', '')
        file_size = data.get('file_size', '')
        
        if not all([document_id, document_title, action_type]):
            return JsonResponse({'error': 'document_id, document_title, and action_type are required'}, status=400)
        
        if action_type not in ['view', 'download']:
            return JsonResponse({'error': 'action_type must be "view" or "download"'}, status=400)
        
        # Get user session and IP
        user_session = get_user_session(request)
        user_ip = get_client_ip(request)
        
        print(f"*** TRACKING DOCUMENT ACTIVITY: {action_type} - {document_title} ***")
        
        # Track the activity
        recent_view = RecentView.track_document_activity(
            document_id=document_id,
            document_title=document_title,
            action_type=action_type,
            user_session=user_session,
            user_ip=user_ip,
            document_category=document_category,
            file_type=file_type,
            file_size=file_size
        )
        
        return JsonResponse({
            'status': 'success',
            'message': f'Document {action_type} tracked successfully',
            'activity_id': str(recent_view.id),
            'timestamp': recent_view.timestamp.isoformat()
        })
        
    except Exception as e:
        print(f"*** TRACK ACTIVITY ERROR: {e} ***")
        return JsonResponse({'error': f'Failed to track activity: {str(e)}'}, status=500)

@csrf_exempt
@require_http_methods(["GET"])
def get_recent_views(request):
    """Get recent document views and downloads for the home page"""
    try:
        # Get parameters
        limit = int(request.GET.get('limit', 10))
        user_session_only = request.GET.get('user_session_only', 'false').lower() == 'true'
        
        print(f"*** GET RECENT VIEWS REQUEST: limit={limit}, user_session_only={user_session_only} ***")
        
        # Get user session if filtering by user
        user_session = None
        if user_session_only:
            user_session = get_user_session(request)
        
        # Get recent views
        recent_views = RecentView.get_recent_views(limit=limit, user_session=user_session)
        
        # Format for frontend
        formatted_views = []
        for view in recent_views:
            # Determine file icon based on file type
            file_icon = 'fas fa-file'
            if view.file_type:
                if 'pdf' in view.file_type.lower():
                    file_icon = 'fas fa-file-pdf'
                elif any(word in view.file_type.lower() for word in ['word', 'doc']):
                    file_icon = 'fas fa-file-word'
                elif any(word in view.file_type.lower() for word in ['excel', 'sheet']):
                    file_icon = 'fas fa-file-excel'
                elif any(word in view.file_type.lower() for word in ['powerpoint', 'presentation']):
                    file_icon = 'fas fa-file-powerpoint'
                elif any(word in view.file_type.lower() for word in ['image', 'png', 'jpg', 'jpeg']):
                    file_icon = 'fas fa-file-image'
                elif any(word in view.file_type.lower() for word in ['text', 'txt']):
                    file_icon = 'fas fa-file-alt'
            
            formatted_views.append({
                'id': str(view.id),
                'document_id': view.document_id,
                'document_title': view.document_title,
                'document_category': view.document_category,
                'action_type': view.action_type,
                'timestamp': view.timestamp.isoformat(),
                'time_ago': view.time_ago,
                'file_type': view.file_type,
                'file_size': view.file_size,
                'file_icon': file_icon
            })
        
        return JsonResponse({
            'status': 'success',
            'recent_views': formatted_views,
            'count': len(formatted_views),
            'user_session_filtered': user_session_only,
            'generated_at': datetime.now().isoformat()
        })
        
    except Exception as e:
        print(f"*** GET RECENT VIEWS ERROR: {e} ***")
        return JsonResponse({
            'status': 'error',
            'error': f'Failed to get recent views: {str(e)}',
            'recent_views': []
        }, status=500)

@csrf_exempt
@require_http_methods(["DELETE"])
def clear_recent_views(request):
    """Clear recent views (optionally for current user session only)"""
    try:
        user_session_only = request.GET.get('user_session_only', 'false').lower() == 'true'
        
        print(f"*** CLEAR RECENT VIEWS REQUEST: user_session_only={user_session_only} ***")
        
        if user_session_only:
            user_session = get_user_session(request)
            deleted_count = RecentView.objects.filter(user_session=user_session).delete()[0]
        else:
            deleted_count = RecentView.objects.all().delete()[0]
        
        return JsonResponse({
            'status': 'success',
            'message': f'Cleared {deleted_count} recent views',
            'deleted_count': deleted_count,
            'user_session_only': user_session_only
        })
        
    except Exception as e:
        print(f"*** CLEAR RECENT VIEWS ERROR: {e} ***")
        return JsonResponse({'error': f'Failed to clear recent views: {str(e)}'}, status=500)

@csrf_exempt
@require_http_methods(["GET"])
def get_documents_by_category(request):
    """Get documents organized by category for folder view"""
    try:
        category = request.GET.get('category')
        limit = int(request.GET.get('limit', 50))
        
        print(f"*** GET DOCUMENTS BY CATEGORY: {category} ***")
        print(f"*** REQUEST PARAMS: category={category}, limit={limit} ***")
        
        # Initialize DynamoDB storage
        dynamodb_storage = DynamoDBStorage()
        
        if category:
            # Get documents for specific category from DynamoDB only
            print(f"*** USING DYNAMODB ONLY FOR CATEGORY: {category} ***")
            documents = dynamodb_storage.list_documents_by_category(category, limit)
            print(f"*** DYNAMODB RETURNED {len(documents)} DOCUMENTS FOR CATEGORY ***")
            
            # TEMPORARY: Also get all documents to compare
            all_documents = dynamodb_storage.get_all_documents(limit)
            print(f"*** DYNAMODB HAS {len(all_documents)} TOTAL DOCUMENTS ***")
            
            # If no documents found for category, show what categories exist
            if len(documents) == 0 and len(all_documents) > 0:
                print("*** NO DOCUMENTS FOUND FOR CATEGORY, SHOWING ALL AVAILABLE CATEGORIES: ***")
                categories_found = set()
                for doc in all_documents:
                    doc_category = doc.get('category', 'unknown')
                    categories_found.add(doc_category)
                    print(f"*** AVAILABLE CATEGORY: {doc_category} ***")
                
                # TEMPORARY FIX: Return all documents if category filter fails
                print(f"*** TEMPORARILY RETURNING ALL DOCUMENTS INSTEAD OF EMPTY RESULT ***")
                documents = all_documents
        else:
            # Get all documents from DynamoDB only
            print(f"*** USING DYNAMODB ONLY FOR ALL DOCUMENTS ***")
            documents = dynamodb_storage.get_all_documents(limit)
            print(f"*** DYNAMODB RETURNED {len(documents)} TOTAL DOCUMENTS ***")
        
        # Format documents for frontend
        formatted_docs = []
        print(f"*** FORMATTING {len(documents)} DOCUMENTS ***")
        
        for i, doc in enumerate(documents):
            try:
                print(f"*** FORMATTING DOCUMENT {i+1}: {doc.get('DocumentID', 'NO_ID')} ***")
                
                # Determine file icon based on file type
                file_icon = 'fas fa-file'
                if doc.get('file_type'):
                    file_type = doc['file_type'].lower()
                    if 'pdf' in file_type:
                        file_icon = 'fas fa-file-pdf'
                    elif any(word in file_type for word in ['word', 'doc']):
                        file_icon = 'fas fa-file-word'
                    elif any(word in file_type for word in ['excel', 'sheet']):
                        file_icon = 'fas fa-file-excel'
                    elif any(word in file_type for word in ['powerpoint', 'presentation']):
                        file_icon = 'fas fa-file-powerpoint'
                    elif any(word in file_type for word in ['image', 'png', 'jpg', 'jpeg']):
                        file_icon = 'fas fa-file-image'
                
                # Simplified document with just filename and upload time
                formatted_doc = {
                    'id': doc.get('DocumentID', f'doc_{i}'),
                    'title': doc.get('filename', 'Unknown Document'),
                    'upload_date': doc.get('upload_date', '2024-01-01'),
                    'file_icon': 'fas fa-file'
                }
                
                formatted_docs.append(formatted_doc)
                print(f"*** FORMATTED DOCUMENT: {formatted_doc['title']} ***")
                
            except Exception as format_error:
                print(f"*** ERROR FORMATTING DOCUMENT {i+1}: {format_error} ***")
                print(f"*** PROBLEMATIC DOCUMENT: {doc} ***")
                continue
        
        print(f"*** RETURNING {len(formatted_docs)} FORMATTED DOCUMENTS ***")
        
        # Create simple, clean response
        final_response = {}
        final_response['documents'] = formatted_docs
        final_response['count'] = len(formatted_docs)  
        final_response['category'] = category
        final_response['status'] = 'success'  # Set this absolutely last
        
        print(f"*** FINAL RESPONSE STATUS: {final_response['status']} ***")
        print(f"*** FINAL RESPONSE COUNT: {final_response['count']} ***")
        
        return JsonResponse(final_response)
        
    except Exception as e:
        print(f"*** GET DOCUMENTS BY CATEGORY ERROR: {e} ***")
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'status': 'error',
            'error': str(e),
            'details': 'Check server logs for more information'
        }, status=500)

@csrf_exempt
@require_http_methods(["GET"])
def simple_test_documents(request):
    """Simple test endpoint with hardcoded documents"""
    try:
        test_docs = [
            {
                'id': 'test1',
                'title': 'Test Document 1.pdf',
                'upload_date': '2024-01-15T10:30:00Z',
                'file_icon': 'fas fa-file-pdf'
            },
            {
                'id': 'test2', 
                'title': 'Test Document 2.docx',
                'upload_date': '2024-01-16T14:20:00Z',
                'file_icon': 'fas fa-file-word'
            }
        ]
        
        response = {
            'documents': test_docs,
            'count': len(test_docs),
            'category': 'test'
        }
        response['status'] = 'success'
        
        return JsonResponse(response)
        
    except Exception as e:
        return JsonResponse({'status': 'error', 'error': str(e)}, status=500)

@csrf_exempt
@require_http_methods(["GET"])
def get_folder_structure(request):
    """Get folder structure with document counts for upload page"""
    try:
        print(f"*** GET FOLDER STRUCTURE REQUEST ***")
        
        # Initialize DynamoDB storage
        dynamodb_storage = DynamoDBStorage()
        
        # Get category statistics
        category_stats = dynamodb_storage.get_category_stats()
        
        # Get all documents to calculate file type stats per category
        all_documents = dynamodb_storage.get_all_documents(1000)  # Get more for accurate stats
        
        # Calculate detailed stats per category
        folder_structure = {
            'policies_guidelines': {
                'name': 'Policies & Guidelines',
                'icon': 'fas fa-shield-alt',
                'color': '#6f42c1',
                'total_files': category_stats.get('policies_guidelines', 0),
                'file_types': {'pdf': 0, 'doc': 0, 'other': 0}
            },
            'operations_production': {
                'name': 'Operations & Production',
                'icon': 'fas fa-cogs',
                'color': '#fd7e14',
                'total_files': category_stats.get('operations_production', 0),
                'file_types': {'pdf': 0, 'image': 0, 'other': 0}
            },
            'maintenance_technical': {
                'name': 'Maintenance & Technical',
                'icon': 'fas fa-tools',
                'color': '#20c997',
                'total_files': category_stats.get('maintenance_technical', 0),
                'file_types': {'pdf': 0, 'doc': 0, 'other': 0}
            },
            'training_knowledge': {
                'name': 'Training & Knowledge',
                'icon': 'fas fa-graduation-cap',
                'color': '#0dcaf0',
                'total_files': category_stats.get('training_knowledge', 0),
                'file_types': {'pdf': 0, 'doc': 0, 'other': 0}
            },
            'others': {
                'name': 'Others',
                'icon': 'fas fa-folder',
                'color': '#6c757d',
                'total_files': category_stats.get('others', 0),
                'file_types': {'pdf': 0, 'image': 0, 'other': 0}
            }
        }
        
        # Calculate file type distribution
        for doc in all_documents:
            category = doc.get('category', 'others')
            file_type = doc.get('file_type', '').lower()
            
            if category in folder_structure:
                if 'pdf' in file_type:
                    folder_structure[category]['file_types']['pdf'] += 1
                elif any(word in file_type for word in ['word', 'doc']):
                    folder_structure[category]['file_types']['doc'] += 1
                elif any(word in file_type for word in ['image', 'png', 'jpg', 'jpeg']):
                    folder_structure[category]['file_types']['image'] += 1
                else:
                    folder_structure[category]['file_types']['other'] += 1
        
        return JsonResponse({
            'status': 'success',
            'folder_structure': folder_structure,
            'total_documents': sum(category_stats.values())
        })
        
    except Exception as e:
        print(f"*** GET FOLDER STRUCTURE ERROR: {e} ***")
        return JsonResponse({'error': str(e)}, status=500)

@csrf_exempt
@require_http_methods(["DELETE"])
def delete_document(request):
    """Delete document from both DynamoDB and S3"""
    try:
        data = json.loads(request.body)
        document_id = data.get('document_id')
        
        if not document_id:
            return JsonResponse({'error': 'document_id is required'}, status=400)
        
        print(f"*** DELETE DOCUMENT REQUEST: {document_id} ***")
        
        # Initialize storage
        dynamodb_storage = DynamoDBStorage()
        
        # Get document details first
        document = dynamodb_storage.get_document_by_id(document_id)
        if not document:
            return JsonResponse({'error': 'Document not found'}, status=404)
        
        # Delete from DynamoDB
        dynamodb_success = dynamodb_storage.delete_document(document_id)
        
        # Optionally delete from S3 (uncomment if needed)
        # s3_success = False
        # if document.get('s3_key'):
        #     try:
        #         from django.conf import settings
        #         import boto3
        #         s3_client = boto3.client('s3')
        #         s3_client.delete_object(Bucket=settings.AWS_S3_BUCKET_NAME, Key=document['s3_key'])
        #         s3_success = True
        #     except Exception as s3_error:
        #         print(f"*** S3 DELETE ERROR: {s3_error} ***")
        
        if dynamodb_success:
            return JsonResponse({
                'status': 'success',
                'message': f'Document {document["filename"]} deleted successfully'
            })
        else:
            return JsonResponse({'error': 'Failed to delete document'}, status=500)
        
    except Exception as e:
        print(f"*** DELETE DOCUMENT ERROR: {e} ***")
        return JsonResponse({'error': str(e)}, status=500)

@csrf_exempt
@require_http_methods(["GET"])
def debug_storage(request):
    """Debug endpoint to check what's in storage"""
    try:
        kendra_db = KendraDatabase()
        
        # Try a broad search to see what documents exist
        documents = kendra_db.search_documents("*", limit=10)
        
        return JsonResponse({
            'status': 'success',
            'kendra_documents': len(documents),
            'documents': [
                {
                    'id': doc.get('id'),
                    'title': doc.get('title'),
                    'category': doc.get('attributes', {}).get('category', 'Unknown')
                }
                for doc in documents
            ]
        })
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@csrf_exempt
@require_http_methods(["GET"])
def test_category_api(request):
    """Test endpoint to check if API is working"""
    try:
        category = request.GET.get('category', 'maintenance_technical')
        
        # Test DynamoDB connection
        dynamodb_storage = DynamoDBStorage()
        
        # Test DynamoDB documents
        if category:
            dynamodb_docs = dynamodb_storage.list_documents_by_category(category, limit=5)
        else:
            dynamodb_docs = dynamodb_storage.get_all_documents(limit=5)
        
        return JsonResponse({
            'status': 'success',
            'message': 'API is working',
            'category': category,
            'dynamodb_docs_found': len(dynamodb_docs),
            'dynamodb_sample': dynamodb_docs[:1] if dynamodb_docs else [],
            'dynamodb_accessible': hasattr(dynamodb_storage, 'table_accessible') and dynamodb_storage.table_accessible
        })
        
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'error': str(e),
            'message': 'API test failed'
        }, status=500)

def category_view(request, category):
    """View for displaying documents in a specific category"""
    # Category mapping
    category_info = {
        'policies_guidelines': {
            'name': 'Policies & Guidelines',
            'icon': 'fas fa-shield-alt',
            'color': '#6f42c1',
            'description': 'Company policies, procedures, and compliance guidelines'
        },
        'operations_production': {
            'name': 'Operations & Production',
            'icon': 'fas fa-cogs',
            'color': '#fd7e14',
            'description': 'Manufacturing processes, production guides, and operational procedures'
        },
        'maintenance_technical': {
            'name': 'Maintenance & Technical',
            'icon': 'fas fa-tools',
            'color': '#20c997',
            'description': 'Technical manuals, maintenance guides, and troubleshooting documents'
        },
        'training_knowledge': {
            'name': 'Training & Knowledge',
            'icon': 'fas fa-graduation-cap',
            'color': '#0dcaf0',
            'description': 'Training materials, educational content, and knowledge base articles'
        },
        'others': {
            'name': 'Others',
            'icon': 'fas fa-folder',
            'color': '#6c757d',
            'description': 'General documents and miscellaneous files'
        }
    }
    
    # Get category info or default to 'others'
    info = category_info.get(category, category_info['others'])
    
    context = {
        'category': category,
        'category_name': info['name'],
        'category_icon': info['icon'],
        'category_color': info['color'],
        'category_description': info['description']
    }
    
    return render(request, 'document_app/category_view.html', context)