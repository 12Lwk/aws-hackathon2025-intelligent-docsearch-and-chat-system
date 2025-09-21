import boto3
import json
import re
from django.conf import settings
from ..aws_credential_keys.config import (
    AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_REGION, 
    BEDROCK_REGION, BEDROCK_MODEL_ID, AWS_KENDRA_INDEX_ID
)
from ..aws_document_pipeline.kendra_database import KendraDatabase

class ChatbotEngine:
    def __init__(self):
        self.kendra_client = boto3.client(
            'kendra',
            aws_access_key_id=AWS_ACCESS_KEY_ID,
            aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
            region_name=AWS_REGION
        )
        
        self.bedrock_client = boto3.client(
            'bedrock-runtime',
            aws_access_key_id=AWS_ACCESS_KEY_ID,
            aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
            region_name=BEDROCK_REGION
        )
        
        self.kendra_db = KendraDatabase()
        
        # Intelligent Document Assistant
        self.system_prompt = """You are an intelligent document assistant that helps users find, analyze, and understand their documents.

Core capabilities:
- Search and retrieve relevant documents using advanced query understanding
- Analyze document content and provide summaries and insights
- Answer questions based on document context
- Guide users through document management tasks
- Provide helpful suggestions when information is not available

Behavior guidelines:
- Always be helpful, accurate, and professional
- Provide specific, actionable responses
- When information is incomplete, suggest alternative approaches
- Use clear, concise language that's easy to understand
- Focus on being genuinely useful to the user's document needs

You have access to a document database and can search, retrieve, and analyze content to provide the most relevant and helpful responses."""
    
    def process_message(self, message, context=None):
        """Main entry point for processing user messages with improved error handling"""
        try:
            # Input validation
            if not message or not message.strip():
                return {
                    'response': 'Please provide a message or question. I\'m here to help you with your documents!',
                    'type': 'error'
                }
            
            message = message.strip()
            document_context = context.get('document') if context else None
            last_response = context.get('lastResponse') if context else None

            # Check if this is a follow-up question about a specific document
            if document_context and self.is_follow_up_question(message):
                print(f"*** Handling follow-up question for document: {document_context.get('title', 'Unknown')} ***")
                return self.perform_contextual_analysis(message, document_context, last_response)

            # Otherwise, proceed with the intelligent response flow
            return self.handle_intelligent_response(message)
                
        except Exception as e:
            print(f"Process message error: {e}")
            return {
                'response': 'I encountered an issue processing your request. Please try again with a different phrasing, or let me know if you need help with document search, analysis, or uploads.',
                'type': 'error'
            }

    def is_follow_up_question(self, message):
        """Check if a message is a follow-up question using improved detection."""
        follow_up_keywords = [
            'analyze', 'summarize', 'explain', 'what are', 'provide', 'give me', 
            'this file', 'the steps', 'troubleshooting', 'simplify', 'break down',
            'how about', 'what about', 'can you', 'could you', 'tell me more',
            'elaborate', 'expand on', 'more details', 'further', 'also',
            'in addition', 'besides', 'furthermore', 'moreover', 'additionally',
            'read this', 'read the', 'read for me', 'read aloud', 'read it',
            'how do i', 'what should i do', 'can you provide', 'what steps'
        ]
        
        # Check for follow-up phrases
        follow_up_phrases = [
            'how about the', 'what about the', 'can you simplify', 'could you simplify',
            'tell me about the', 'explain the', 'what are the', 'break down the',
            'simplify for me', 'make it simple', 'in simple terms',
            'read this for me', 'read the document', 'read it aloud', 'read this aloud',
            'how do i ensure', 'what should i do if', 'can you provide an example',
            'what are the specific steps', 'what are the targeted', 'how to find'
        ]
        
        message_lower = message.lower()
        
        # Check if this looks like a suggested question pattern
        suggested_question_patterns = [
            'how do i ensure that automatic updates',
            'what should i do if my school-managed device',
            'can you provide an example of how to',
            'what are the specific steps',
            'what are the targeted areas',
            'what methods and materials should be used'
        ]
        
        is_suggested_question = any(pattern in message_lower for pattern in suggested_question_patterns)
        
        # Check keywords
        has_keywords = any(keyword in message_lower for keyword in follow_up_keywords)
        
        # Check phrases
        has_phrases = any(phrase in message_lower for phrase in follow_up_phrases)
        
        # Check for pronouns that suggest reference to previous content
        reference_pronouns = ['it', 'this', 'that', 'these', 'those', 'them']
        has_references = any(pronoun in message_lower.split() for pronoun in reference_pronouns)
        
        # Special handling for standalone read requests
        standalone_read_requests = ['read this', 'read it', 'read the document', 'read for me', 'read aloud']
        is_read_request = any(request in message_lower for request in standalone_read_requests)
        
        return has_keywords or has_phrases or has_references or is_read_request or is_suggested_question

    def classify_follow_up_question(self, question):
        """Classify the type of follow-up question to provide better responses"""
        question_lower = question.lower()
        
        # Read-aloud requests
        if any(phrase in question_lower for phrase in ['read this', 'read the', 'read for me', 'read aloud', 'read it']):
            return 'read_aloud'
        
        # Simplification requests
        if any(word in question_lower for word in ['simplify', 'simple', 'break down', 'easy', 'plain', 'basic']):
            return 'simplify'
        
        # Elaboration requests  
        if any(word in question_lower for word in ['elaborate', 'more details', 'expand', 'tell me more', 'further']):
            return 'elaborate'
            
        # Specific information requests
        if any(word in question_lower for word in ['what are', 'how many', 'which', 'when', 'where', 'who']):
            return 'specific'
            
        # Default
        return 'general'

    def perform_contextual_analysis(self, user_question, document_context, last_ai_response=None):
        """Use Bedrock to answer a user's question based on a specific document's content and conversation history."""
        try:
            doc_title = document_context.get('title', 'the document')
            doc_content = document_context.get('content', '')
            doc_id = document_context.get('id')

            print(f"*** CONTEXTUAL ANALYSIS for '{doc_title}' ***")
            print(f"*** USER QUESTION: '{user_question}' ***")

            # Heuristic to check if we have the full content or just an excerpt.
            # Excerpts from Kendra are often truncated with '...'.
            is_excerpt = len(doc_content) < 2000 and doc_content.endswith('...')

            if is_excerpt and doc_id:
                print(f"*** Content for '{doc_title}' is just an excerpt. Fetching full document. ***")
                full_doc = self.kendra_db.get_document_by_id(doc_id)
                if full_doc and full_doc.get('content'):
                    doc_content = full_doc['content']
                    print(f"*** Successfully fetched full content ({len(doc_content)} chars). ***")
                else:
                    print(f"*** Could not fetch full content for document ID: {doc_id} ***")

            if not doc_content:
                return {
                    'response': f"I'm sorry, but I don't have enough content from '{doc_title}' to answer your question. Try viewing the document first.",
                    'type': 'error'
                }

            # Detect the type of follow-up question to provide better responses
            question_type = self.classify_follow_up_question(user_question)
            print(f"*** FOLLOW-UP TYPE: {question_type} ***")

            # Build the history part of the prompt if it exists
            history_prompt = ""
            if last_ai_response:
                history_prompt = (
                    f"Previous conversation context:\n--- PREVIOUS RESPONSE ---\n{last_ai_response[:500]}\n--- END PREVIOUS RESPONSE ---\n\n"
                    f"The user is now asking a follow-up question. Build upon the previous response but provide new insights."
                )

            # Construct specialized prompts based on question type
            if question_type == 'read_aloud':
                return self.handle_read_aloud_request(doc_title, doc_content)
            elif question_type == 'simplify':
                task_instruction = "Simplify and break down the information from this document in easy-to-understand terms. Use bullet points and clear language."
            elif question_type == 'elaborate':
                task_instruction = "Provide more detailed explanation and elaborate on the key points from this document."
            elif question_type == 'specific':
                task_instruction = "Answer the specific question using only the information available in this document."
            else:
                task_instruction = "Provide a helpful response based on the document content."

            # Construct the final, more intelligent prompt
            prompt_lines = [
                "You are an intelligent document assistant. Your task is to help the user understand the document content.",
                history_prompt,
                f"\n## Document: '{doc_title}' ##\n",
                doc_content[:4000],
                f"\n## User's Request ##\n",
                f'"{user_question}"',
                f"\n## Task ##\n{task_instruction}",
                "\nProvide a clear, helpful response based ONLY on the document content above. If the document doesn't contain enough information to fully answer the question, say so and explain what information is available."
            ]
            prompt = "\n".join(prompt_lines)

            model_id = getattr(settings, 'BEDROCK_MODEL_ID', None)
            if not model_id:
                return {'response': 'The AI model is not configured, so I cannot analyze the document.', 'type': 'error'}

            # Adjust parameters based on question type
            max_tokens = 800 if question_type == 'simplify' else 1000
            temperature = 0.3 if question_type == 'simplify' else 0.2

            body = {
                "messages": [{"role": "user", "content": [{"text": prompt}]}],
                "inferenceConfig": {
                    "maxTokens": max_tokens,
                    "temperature": temperature,
                    "topP": 0.9
                }
            }

            response = self.bedrock_client.invoke_model(
                modelId=model_id,
                body=json.dumps(body)
            )

            result = json.loads(response['body'].read())
            ai_answer = result.get('output', {}).get('message', {}).get('content', [{}])[0].get('text', '')

            return {
                'response': ai_answer,
                'type': 'analysis',
                'sources': [doc_title]
            }

        except Exception as e:
            return {
                'response': f"I encountered an error while analyzing the document. Please try again. Error: {e}",
                'type': 'error'
            }
    
    def handle_intelligent_response(self, message):
        """Use LLM to intelligently understand and respond to any message"""
        try:
            # First, let LLM understand the intent and decide what to do
            intent_response = self.analyze_user_intent(message)
            print(f"*** DETECTED INTENT: {intent_response} ***")
            
            # Based on LLM analysis, perform appropriate actions
            if 'search_documents' in intent_response.lower():
                return self.perform_document_search(message)
            elif 'analyze_document' in intent_response.lower():
                return self.perform_document_analysis(message)
            elif 'upload_files' in intent_response.lower():
                return self.handle_upload_guidance(message)
            else:
                # For general conversation, search for context and respond intelligently
                return self.handle_conversational_response(message)
                
        except Exception as e:
            print(f"Intelligent response error: {e}")
            return {
                'response': 'I\'m having trouble understanding your request right now. Could you try rephrasing it? I can help you search for documents, analyze content, or guide you through uploads.',
                'type': 'error'
            }
    
    def analyze_user_intent(self, message):
        """Use LLM to analyze user intent with improved accuracy"""
        intent_prompt = f"""You are an intelligent document assistant. Analyze the user's message and determine their intent.

User message: "{message}"

Classify the intent as ONE of these categories:
1. SEARCH - User wants to find specific documents (keywords: find, search, look for, show me, get, where is)
2. ANALYZE - User wants to analyze/summarize a specific document (keywords: analyze, summarize, explain, what does, tell me about)
3. UPLOAD - User wants to upload documents (keywords: upload, add, submit, import)
4. READ_ALOUD - User wants content read aloud (keywords: read this, read for me, read aloud, read the document)
5. GREETING - Simple greetings, identity questions, or capability questions (keywords: hi, hello, help, what can you do, what is your name, who are you)
6. QUESTION - User has a specific question about document content (keywords: how to do something, what does this document say, when was this created)

Consider the context and keywords. Respond with ONLY the category name (SEARCH, ANALYZE, UPLOAD, READ_ALOUD, GREETING, or QUESTION).

Intent:"""
        
        try:
            response = self.bedrock_client.invoke_model(
                modelId=BEDROCK_MODEL_ID,
                body=json.dumps({
                    "messages": [
                        {
                            "role": "user",
                            "content": [{
                                "text": intent_prompt
                            }]
                        }
                    ],
                    "inferenceConfig": {
                        "maxTokens": 20,
                        "temperature": 0.1,
                        "topP": 0.7
                    }
                })
            )
            
            response_body = json.loads(response['body'].read())
            intent = response_body['output']['message']['content'][0]['text'].strip().upper()
            
            # Map to our internal actions
            intent_mapping = {
                'SEARCH': 'search_documents',
                'ANALYZE': 'analyze_document', 
                'UPLOAD': 'upload_files',
                'READ_ALOUD': 'general_conversation',  # Handle in conversational flow
                'QUESTION': 'search_documents',  # Questions usually need search
                'GREETING': 'general_conversation'
            }
            
            return intent_mapping.get(intent, 'general_conversation')
            
        except Exception as e:
            print(f"Intent analysis error: {e}")
            # Fallback to keyword-based classification
            message_lower = message.lower()
            
            # Check for identity/greeting questions first
            identity_phrases = ['what is your name', 'who are you', 'what are you called', 'introduce yourself']
            greeting_phrases = ['hi', 'hello', 'hey', 'good morning', 'good afternoon', 'help', 'what can you do']
            
            if any(phrase in message_lower for phrase in identity_phrases + greeting_phrases):
                return 'general_conversation'
            elif any(word in message_lower for word in ['find', 'search', 'look for', 'show me', 'get']):
                return 'search_documents'
            elif any(word in message_lower for word in ['analyze', 'summarize', 'explain']):
                return 'analyze_document'
            elif any(word in message_lower for word in ['upload', 'add', 'submit']):
                return 'upload_files'
            elif any(phrase in message_lower for phrase in ['read this', 'read for me', 'read aloud']):
                return 'general_conversation'  # Handle read requests in conversation
            else:
                return 'general_conversation'
    
    def handle_upload_guidance(self, message):
        """Handle upload requests with LLM response"""
        upload_prompt = f"""{self.system_prompt}

The user wants to upload documents. Provide helpful guidance about uploading manufacturing documents.
Mention that they can use the Upload page from the sidebar menu, and that the system supports PDF, Word, Excel, and text files up to 10MB each.

User message: "{message}"

Response:"""
        
        try:
            response = self.bedrock_client.invoke_model(
                modelId=BEDROCK_MODEL_ID,
                body=json.dumps({
                    "messages": [
                        {
                            "role": "user",
                            "content": [{
                                "text": upload_prompt
                            }]
                        }
                    ],
                    "inferenceConfig": {
                        "maxTokens": 200,
                        "temperature": 0.3,
                        "topP": 0.8
                    }
                })
            )
            
            response_body = json.loads(response['body'].read())
            return {
                'response': response_body['output']['message']['content'][0]['text'].strip(),
                'type': 'upload'
            }
            
        except:
            return {
                'response': 'I can help you upload manufacturing documents! Please use the Upload page from the sidebar menu. The system supports PDF, Word, Excel, and text files up to 10MB each.',
                'type': 'upload'
            }
    
    def perform_document_search(self, message):
        """Perform intelligent document search with improved accuracy"""
        try:
            # Use LLM to understand what user is really looking for
            search_intent = self.analyze_search_intent(message)
            
            # Extract key terms using LLM
            search_terms = self.extract_intelligent_search_terms(message)
            
            print(f"*** ORIGINAL QUERY: '{message}' ***")
            print(f"*** SEARCH INTENT: '{search_intent}' ***")
            print(f"*** EXTRACTED TERMS: '{search_terms}' ***")
            
            # Try multiple search strategies
            results = None
            
            # Strategy 1: Direct search with extracted terms
            if search_terms:
                results = self.kendra_db.search_documents(search_terms, limit=10)
                print(f"*** STRATEGY 1 RESULTS: {len(results) if results else 0} ***")
            
            # Strategy 2: Enhanced query if no results
            if not results:
                enhanced_query = self.enhance_search_query(message)
                results = self.kendra_db.search_documents(enhanced_query, limit=10)
                print(f"*** STRATEGY 2 RESULTS: {len(results) if results else 0} ***")
            
            # Strategy 3: Broader search if still no results
            if not results:
                broader_query = self.create_broader_query(message)
                results = self.kendra_db.search_documents(broader_query, limit=10)
                print(f"*** STRATEGY 3 RESULTS: {len(results) if results else 0} ***")
            
            if not results:
                return self.generate_helpful_no_results_response(message)
            
            # Rank results by relevance using LLM
            best_match = self.select_best_result(message, results)
            
            # Generate intelligent response about the found document
            response_text = self.generate_search_response_with_context(message, best_match)
            
            # Format document properly
            formatted_doc = self.format_document_result(best_match)
            
            print(f"*** FINAL RESULT: {formatted_doc['title']} ***")
            
            return {
                'response': response_text,
                'document': formatted_doc,
                'type': 'search'
            }
            
        except Exception as e:
            print(f"Search error: {e}")
            return {
                'response': 'I encountered an issue while searching. Please try rephrasing your query or check if documents are uploaded.',
                'document': None,
                'type': 'error'
            }
    
    def extract_intelligent_search_terms(self, message):
        """Use LLM to extract the most relevant search terms"""
        extraction_prompt = f"""Extract the most important search terms from this user query for document search.

User query: "{message}"

Extract 3-5 key terms that would be most effective for finding relevant documents. Focus on:
- Main topics and subjects
- Specific processes or equipment
- Document types (manual, procedure, report, etc.)
- Technical terms

Provide only the key terms separated by spaces, no explanations:"""
        
        try:
            response = self.bedrock_client.invoke_model(
                modelId=BEDROCK_MODEL_ID,
                body=json.dumps({
                    "messages": [{
                        "role": "user",
                        "content": [{"text": extraction_prompt}]
                    }],
                    "inferenceConfig": {
                        "maxTokens": 50,
                        "temperature": 0.2,
                        "topP": 0.8
                    }
                })
            )
            
            response_body = json.loads(response['body'].read())
            terms = response_body['output']['message']['content'][0]['text'].strip()
            return terms if terms else message
            
        except Exception as e:
            print(f"Term extraction error: {e}")
            return self.extract_search_terms(message)  # Fallback to original method
    
    def select_best_result(self, query, results):
        """Use LLM to select the most relevant result from search results"""
        if not results or len(results) == 1:
            return results[0] if results else None
            
        # Create a summary of top results for LLM evaluation
        result_summaries = []
        for i, result in enumerate(results[:5]):
            title = result.get('title', 'Unknown')
            excerpt = result.get('excerpt', '')[:200]
            category = result.get('attributes', {}).get('category', 'Unknown')
            result_summaries.append(f"{i+1}. {title} (Category: {category}) - {excerpt}")
        
        selection_prompt = f"""Given this user query and search results, select the MOST relevant document.

User query: "{query}"

Search results:
{chr(10).join(result_summaries)}

Which result number (1-{len(result_summaries)}) is most relevant to the user's query? Consider:
- Direct relevance to the query
- Document type appropriateness
- Content quality

Respond with only the number:"""
        
        try:
            response = self.bedrock_client.invoke_model(
                modelId=BEDROCK_MODEL_ID,
                body=json.dumps({
                    "messages": [{
                        "role": "user",
                        "content": [{"text": selection_prompt}]
                    }],
                    "inferenceConfig": {
                        "maxTokens": 10,
                        "temperature": 0.1,
                        "topP": 0.7
                    }
                })
            )
            
            response_body = json.loads(response['body'].read())
            selection = response_body['output']['message']['content'][0]['text'].strip()
            
            # Extract number and return corresponding result
            try:
                selected_index = int(selection) - 1
                if 0 <= selected_index < len(results):
                    return results[selected_index]
            except ValueError:
                pass
                
        except Exception as e:
            print(f"Result selection error: {e}")
            
        # Fallback to first result
        return results[0]
    
    def generate_search_response_with_context(self, query, document):
        """Generate an intelligent response about the found document with suggestions"""
        if not document:
            return "No relevant documents found."
            
        doc_title = document.get('title', 'Unknown Document')
        doc_category = document.get('attributes', {}).get('category', 'Unknown')
        doc_excerpt = document.get('excerpt', '')[:400]
        
        # Generate both response and suggestions
        main_response = self.generate_document_response(query, doc_title, doc_category, doc_excerpt)
        suggestions = self.generate_query_suggestions(doc_title, doc_excerpt, query)
        
        # Combine response with suggestions
        full_response = main_response
        if suggestions:
            full_response += f"\n\n💡 **You might also want to ask:**\n{suggestions}"
        
        # Add read-aloud option
        full_response += "\n\n📖 *Say 'read this for me' or 'read the document' if you'd like me to read the content aloud.*"
        
        return full_response
    
    def generate_document_response(self, query, doc_title, doc_category, doc_excerpt):
        """Generate the main response about the found document"""
        response_prompt = f"""Generate a helpful response about this search result for the user.

User query: "{query}"
Found document: "{doc_title}"
Category: {doc_category}
Content preview: {doc_excerpt}

Create a brief, helpful response that:
1. Confirms what was found
2. Explains why it's relevant to their query
3. Mentions key information from the preview

Keep it concise and professional:"""
        
        try:
            response = self.bedrock_client.invoke_model(
                modelId=BEDROCK_MODEL_ID,
                body=json.dumps({
                    "messages": [{
                        "role": "user",
                        "content": [{"text": response_prompt}]
                    }],
                    "inferenceConfig": {
                        "maxTokens": 150,
                        "temperature": 0.3,
                        "topP": 0.8
                    }
                })
            )
            
            response_body = json.loads(response['body'].read())
            return response_body['output']['message']['content'][0]['text'].strip()
            
        except Exception as e:
            print(f"Response generation error: {e}")
            return f'Found: "{doc_title}" (Category: {doc_category}) - This document appears relevant to your query about {query}.'
    
    def generate_query_suggestions(self, doc_title, doc_excerpt, original_query):
        """Generate intelligent follow-up query suggestions based on the document"""
        suggestion_prompt = f"""Based on this document, suggest 3 specific, actionable questions that can be answered directly from the document content.

Document: "{doc_title}"
Content preview: {doc_excerpt[:300]}
Original query: "{original_query}"

Generate 3 questions that:
1. Can be answered DIRECTLY using the information in this document
2. Are specific and practical for the user
3. Focus on actionable steps, procedures, or specific details mentioned in the preview
4. Are different from the original query
5. Start with phrases like "What does the document say about..." or "According to this document..."

Format as:
• What does the document say about [specific topic from preview]?
• According to this document, what are the steps for [specific process]?
• Based on this document, what should you do if [specific scenario]?

Make the questions clearly reference the document content so they are treated as follow-up questions:"""
        
        try:
            response = self.bedrock_client.invoke_model(
                modelId=BEDROCK_MODEL_ID,
                body=json.dumps({
                    "messages": [{
                        "role": "user",
                        "content": [{"text": suggestion_prompt}]
                    }],
                    "inferenceConfig": {
                        "maxTokens": 150,
                        "temperature": 0.4,
                        "topP": 0.8
                    }
                })
            )
            
            response_body = json.loads(response['body'].read())
            return response_body['output']['message']['content'][0]['text'].strip()
            
        except Exception as e:
            print(f"Suggestion generation error: {e}")
            # Fallback suggestions based on document type
            return self.generate_fallback_suggestions(doc_title, original_query)
    
    def generate_fallback_suggestions(self, doc_title, original_query):
        """Generate fallback suggestions when AI generation fails"""
        suggestions = [
            f"• What are the key points in {doc_title}?",
            f"• Can you summarize {doc_title} for me?",
            f"• What should I know about {doc_title}?"
        ]
        return "\n".join(suggestions)
    
    def handle_read_aloud_request(self, doc_title, doc_content):
        """Handle requests to read document content aloud"""
        try:
            # Prepare content for reading (clean and format)
            reading_content = self.prepare_content_for_reading(doc_content)
            
            # Generate a natural reading version
            reading_prompt = f"""Convert this document content into a natural, easy-to-listen format for text-to-speech reading.

Document: "{doc_title}"
Content: {reading_content[:2000]}

Rewrite the content to be:
1. Easy to listen to when read aloud
2. Well-structured with clear sections
3. Natural flowing sentences
4. Include brief pauses indicated by periods

Provide the reading-friendly version:"""
            
            response = self.bedrock_client.invoke_model(
                modelId=BEDROCK_MODEL_ID,
                body=json.dumps({
                    "messages": [{
                        "role": "user",
                        "content": [{"text": reading_prompt}]
                    }],
                    "inferenceConfig": {
                        "maxTokens": 1200,
                        "temperature": 0.2,
                        "topP": 0.8
                    }
                })
            )
            
            response_body = json.loads(response['body'].read())
            reading_text = response_body['output']['message']['content'][0]['text'].strip()
            
            return {
                'response': f"📖 **Reading '{doc_title}' for you:**\n\n{reading_text}\n\n🔊 *This content has been formatted for easy listening. You can use your device's text-to-speech feature to hear it read aloud.*",
                'type': 'read_aloud',
                'sources': [doc_title],
                'reading_content': reading_text  # For potential TTS integration
            }
            
        except Exception as e:
            print(f"Read aloud error: {e}")
            # Fallback to basic content reading
            clean_content = self.prepare_content_for_reading(doc_content)[:1000]
            return {
                'response': f"📖 **Reading '{doc_title}' for you:**\n\n{clean_content}\n\n🔊 *Use your device's text-to-speech feature to hear this content read aloud.*",
                'type': 'read_aloud',
                'sources': [doc_title]
            }
    
    def prepare_content_for_reading(self, content):
        """Clean and prepare content for text-to-speech reading"""
        if not content:
            return "No content available to read."
        
        # Basic cleaning for better TTS
        import re
        
        # Remove excessive whitespace
        content = re.sub(r'\s+', ' ', content)
        
        # Add periods after abbreviations for better TTS pauses
        content = re.sub(r'\b([A-Z]{2,})\b', r'\1.', content)
        
        # Ensure sentences end with periods
        content = re.sub(r'([a-zA-Z])\s*\n', r'\1. ', content)
        
        # Replace special characters that might confuse TTS
        content = content.replace('&', ' and ')
        content = content.replace('@', ' at ')
        content = content.replace('#', ' number ')
        
        return content.strip()
    
    def generate_helpful_no_results_response(self, query):
        """Generate helpful response when no documents are found"""
        suggestion_prompt = f"""The user searched for documents but none were found. Generate helpful suggestions.

User query: "{query}"

Provide:
1. A brief acknowledgment that no documents were found
2. 2-3 specific alternative search terms they could try
3. General advice about document search

Be helpful and specific:"""
        
        try:
            response = self.bedrock_client.invoke_model(
                modelId=BEDROCK_MODEL_ID,
                body=json.dumps({
                    "messages": [{
                        "role": "user",
                        "content": [{"text": suggestion_prompt}]
                    }],
                    "inferenceConfig": {
                        "maxTokens": 150,
                        "temperature": 0.4,
                        "topP": 0.8
                    }
                })
            )
            
            response_body = json.loads(response['body'].read())
            helpful_response = response_body['output']['message']['content'][0]['text'].strip()
            
            return {
                'response': helpful_response,
                'document': None,
                'type': 'search'
            }
            
        except Exception as e:
            print(f"No results response error: {e}")
            return {
                'response': f'No documents found for "{query}". Try using more specific keywords, check spelling, or verify that relevant documents have been uploaded.',
                'document': None,
                'type': 'search'
            }
    
    def format_document_result(self, document):
        """Format document result with proper ID handling"""
        if not document:
            return None
            
        doc_id = document.get('id')
        doc_title = document.get('title', 'Unknown Document')
        
        # Ensure proper ID for retrieval
        if not doc_id:
            doc_id = doc_title.replace(' ', '_').replace('.', '_')
        
        return {
            'id': doc_id,
            'title': doc_title,
            'excerpt': (document.get('excerpt', 'No preview available') or 'No preview available')[:200] + '...',
            'category': document.get('attributes', {}).get('category', 'Unknown'),
            'score': self.convert_score_to_number(document.get('score', 0)),
            'full_content': document.get('excerpt', ''),
            'attributes': document.get('attributes', {})
        }
    
    def analyze_search_intent(self, message):
        """Use LLM to understand what user is really searching for"""
        intent_prompt = f"""Analyze this search request and identify the key concepts:

User request: "{message}"

Identify:
1. Main topic (quality, maintenance, safety, production, etc.)
2. Specific equipment or process mentioned
3. Document type needed (manual, procedure, report, etc.)
4. Key keywords for search

Provide concise analysis:"""
        
        try:
            response = self.bedrock_client.invoke_model(
                modelId=BEDROCK_MODEL_ID,
                body=json.dumps({
                    "messages": [{
                        "role": "user",
                        "content": [{"text": intent_prompt}]
                    }],
                    "inferenceConfig": {
                        "maxTokens": 100,
                        "temperature": 0.2,
                        "topP": 0.8
                    }
                })
            )
            
            response_body = json.loads(response['body'].read())
            return response_body['output']['message']['content'][0]['text'].strip()
        except:
            return message
    
    
    def generate_search_response(self, query, results):
        """Generate intelligent response about search results"""
        if not results:
            return f'No relevant documents found for "{query}".'
        
        # Create summary of found documents
        doc_summaries = []
        for doc in results:
            summary = f"- {doc['title']} (Category: {doc['attributes'].get('category', 'Unknown')})"
            if 'relevance_reason' in doc:
                summary += f" - {doc['relevance_reason']}"
            doc_summaries.append(summary)
        
        response_prompt = f"""Create a helpful response about these search results:

User searched for: "{query}"

Found documents:
{chr(10).join(doc_summaries)}

Provide a brief, helpful response explaining what was found and how it relates to their query."""
        
        try:
            response = self.bedrock_client.invoke_model(
                modelId=BEDROCK_MODEL_ID,
                body=json.dumps({
                    "messages": [{
                        "role": "user",
                        "content": [{"text": response_prompt}]
                    }],
                    "inferenceConfig": {
                        "maxTokens": 200,
                        "temperature": 0.3,
                        "topP": 0.8
                    }
                })
            )
            
            response_body = json.loads(response['body'].read())
            return response_body['output']['message']['content'][0]['text'].strip()
        except:
            return f'Found document for "{query}"'
    
    def extract_category_terms(self, message):
        """Extract broader category terms for fallback search"""
        category_mapping = {
            'quality': 'quality control assurance inspection',
            'maintenance': 'maintenance repair service preventive',
            'safety': 'safety security protocol compliance',
            'production': 'production manufacturing assembly process',
            'training': 'training education learning instruction',
            'procedure': 'procedure process workflow operation'
        }
        
        message_lower = message.lower()
        for category, terms in category_mapping.items():
            if category in message_lower:
                return terms
        
        return None
    
    def perform_document_analysis(self, message):
        """Perform intelligent document analysis"""
        doc_name = self.extract_document_name(message)
        results = self.kendra_db.search_documents(doc_name, limit=1)
        
        if not results:
            # Use LLM to respond intelligently when document not found
            not_found_prompt = f"""{self.system_prompt}

The user asked to analyze a document but it wasn't found: "{message}"
Provide a helpful response suggesting they check the document name or search for similar documents.

Response:"""
            
            try:
                response = self.bedrock_client.invoke_model(
                    modelId=BEDROCK_MODEL_ID,
                    body=json.dumps({
                        "messages": [
                            {
                                "role": "user",
                                "content": [{
                                    "text": not_found_prompt
                                }]
                            }
                        ],
                        "inferenceConfig": {
                            "maxTokens": 100,
                            "temperature": 0.3,
                            "topP": 0.8
                        }
                    })
                )
                
                response_body = json.loads(response['body'].read())
                return {
                    'response': response_body['output']['message']['content'][0]['text'].strip(),
                    'type': 'error'
                }
            except:
                return {
                    'response': f'Could not find document "{doc_name}". Please check the name or search for similar documents.',
                    'type': 'error'
                }
        
        doc = results[0]
        analysis = self.generate_intelligent_analysis(doc, message)
        
        return {
            'response': analysis,
            'document': doc['title'],
            'type': 'analysis'
        }
    
    def handle_conversational_response(self, message):
        """Handle general conversation with improved intelligence"""
        try:
            # Handle common queries with predefined intelligent responses
            message_lower = message.lower()
            
            # Identity questions
            identity_phrases = ['what is your name', 'who are you', 'what are you called', 'introduce yourself', 'tell me about yourself']
            if any(phrase in message_lower for phrase in identity_phrases):
                return {
                    'response': 'I\'m your intelligent document assistant! I help you find, analyze, and understand your documents. I can search through your document library, provide summaries, answer questions about content, and even read documents aloud for you. How can I assist you today?',
                    'sources': None,
                    'type': 'general'
                }
            
            # Capability questions
            if any(phrase in message_lower for phrase in ['what can you do', 'help me', 'how can you help', 'capabilities']):
                return {
                    'response': 'I can help you with document management tasks:\n\n• Search for specific documents using keywords\n• Analyze and summarize document content\n• Answer questions based on your documents\n• Guide you through document uploads\n• Navigate through search results\n• Read documents aloud for accessibility\n\nWhat would you like to do?',
                    'sources': None,
                    'type': 'general'
                }
            
            # Greetings with context
            if any(greeting in message_lower for greeting in ['hi', 'hello', 'hey', 'good morning', 'good afternoon', 'selamat pagi', 'selamat petang']):
                return {
                    'response': 'Hello! I\'m your document assistant. I can help you search, analyze, and navigate your documents. What are you looking for today?',
                    'sources': None,
                    'type': 'general'
                }
            
            # Check if this might be a question that needs document context
            if self.is_question_needing_context(message):
                return self.handle_contextual_question(message)
            
            # For other general conversation, provide helpful guidance
            return self.generate_helpful_guidance(message)
            
        except Exception as e:
            print(f"Conversational response error: {e}")
            return {
                'response': 'I\'m here to help you with your documents. You can ask me to search for specific documents, analyze content, or answer questions about your files. What would you like to do?',
                'type': 'general'
            }
    
    def is_question_needing_context(self, message):
        """Determine if a message is a question that might need document context"""
        message_lower = message.lower()
        
        # Exclude identity and capability questions
        identity_phrases = ['what is your name', 'who are you', 'what are you called', 'what can you do', 'how can you help']
        if any(phrase in message_lower for phrase in identity_phrases):
            return False
        
        # Check for document-related questions
        document_question_indicators = [
            'what does this document say', 'what is in the document', 'how to do', 
            'what are the steps', 'what are the procedures', 'what are the requirements',
            'when should', 'where can I find', 'which document', 'how do I'
        ]
        
        return any(indicator in message_lower for indicator in document_question_indicators)
    
    def handle_contextual_question(self, message):
        """Handle questions that might need document context"""
        try:
            # Search for relevant context
            search_terms = self.extract_intelligent_search_terms(message)
            results = self.kendra_db.search_documents(search_terms, limit=3)
            
            if not results:
                return {
                    'response': f'I don\'t have specific information about "{message}" in the uploaded documents. You could try:\n\n• Searching for related keywords\n• Uploading relevant documents\n• Asking more specific questions\n\nWhat else can I help you with?',
                    'sources': None,
                    'type': 'general'
                }
            
            # Use the best result to provide context
            best_result = results[0]
            doc_title = best_result.get('title', 'Unknown')
            doc_excerpt = best_result.get('excerpt', '')[:400]
            
            # Generate contextual response
            context_prompt = f"""Answer this question using the provided document context. Be helpful and specific.

Question: "{message}"

Document context from "{doc_title}":
{doc_excerpt}

Provide a helpful answer based on the context. If the context doesn't fully answer the question, say so and suggest what additional information might be needed:"""
            
            response = self.bedrock_client.invoke_model(
                modelId=BEDROCK_MODEL_ID,
                body=json.dumps({
                    "messages": [{
                        "role": "user",
                        "content": [{"text": context_prompt}]
                    }],
                    "inferenceConfig": {
                        "maxTokens": 200,
                        "temperature": 0.3,
                        "topP": 0.8
                    }
                })
            )
            
            response_body = json.loads(response['body'].read())
            ai_response = response_body['output']['message']['content'][0]['text'].strip()
            
            return {
                'response': ai_response,
                'sources': [doc_title],
                'type': 'general'
            }
            
        except Exception as e:
            print(f"Contextual question error: {e}")
            return {
                'response': 'I can help answer questions based on your documents. Try searching for specific topics or uploading relevant documents first.',
                'type': 'general'
            }
    
    def generate_helpful_guidance(self, message):
        """Generate helpful guidance for general messages"""
        guidance_prompt = f"""The user sent this message: "{message}"

Generate a helpful response that:
1. Acknowledges their message
2. Suggests specific ways I can help with documents
3. Asks a clarifying question to better assist them

Keep it friendly, professional, and focused on document assistance:"""
        
        try:
            response = self.bedrock_client.invoke_model(
                modelId=BEDROCK_MODEL_ID,
                body=json.dumps({
                    "messages": [{
                        "role": "user",
                        "content": [{"text": guidance_prompt}]
                    }],
                    "inferenceConfig": {
                        "maxTokens": 120,
                        "temperature": 0.4,
                        "topP": 0.8
                    }
                })
            )
            
            response_body = json.loads(response['body'].read())
            helpful_response = response_body['output']['message']['content'][0]['text'].strip()
            
            return {
                'response': helpful_response,
                'sources': None,
                'type': 'general'
            }
            
        except Exception as e:
            print(f"Guidance generation error: {e}")
            return {
                'response': 'I can help you search for documents, analyze content, or answer questions about your files. What specific information are you looking for?',
                'type': 'general'
            }
    
    def is_content_relevant(self, query, content):
        """Quick relevance check for content filtering"""
        query_words = set(query.lower().split())
        content_words = set(content.lower().split())
        
        # Check for word overlap
        overlap = len(query_words.intersection(content_words))
        
        # Consider relevant if there's significant overlap or manufacturing keywords
        manufacturing_keywords = {'quality', 'production', 'maintenance', 'safety', 'procedure', 'process', 'equipment', 'manufacturing'}
        has_manufacturing_context = bool(manufacturing_keywords.intersection(content_words))
        
        return overlap >= 2 or (overlap >= 1 and has_manufacturing_context)
    
    def generate_intelligent_analysis(self, doc, original_message):
        """Generate intelligent document analysis using LLM"""
        content = doc.get('content', doc.get('excerpt', ''))
        title = doc['title']
        
        if not content:
            return f"Document '{title}' was found but content is not available for detailed analysis."
        
        # Use LLM to generate intelligent analysis
        analysis_prompt = f"""{self.system_prompt}

Analyze this manufacturing document and provide insights:

Document Title: {title}
Document Content: {content[:2000]}
User Request: {original_message}

Provide a comprehensive analysis including:
- Key insights and main topics
- Manufacturing relevance
- Important procedures or guidelines mentioned
- Any safety or quality considerations
- Summary of key points

Analysis:"""
        
        try:
            response = self.bedrock_client.invoke_model(
                modelId=BEDROCK_MODEL_ID,
                body=json.dumps({
                    "messages": [
                        {
                            "role": "user",
                            "content": [{
                                "text": analysis_prompt
                            }]
                        }
                    ],
                    "inferenceConfig": {
                        "maxTokens": 600,
                        "temperature": 0.3,
                        "topP": 0.8
                    }
                })
            )
            
            response_body = json.loads(response['body'].read())
            return response_body['output']['message']['content'][0]['text'].strip()
            
        except:
            # Fallback to basic analysis
            word_count = len(content.split())
            return f"Analysis of '{title}':\n\nThis manufacturing document contains {word_count} words and covers important operational information. The document appears to be categorized as {doc['attributes'].get('category', 'general manufacturing content')}."
    
    def enhance_search_query(self, query):
        """Enhance search query with manufacturing context"""
        manufacturing_terms = {
            'sop': 'standard operating procedure',
            'qc': 'quality control',
            'qa': 'quality assurance',
            'pm': 'preventive maintenance',
            'oee': 'overall equipment effectiveness',
            'wip': 'work in progress',
            'bom': 'bill of materials'
        }
        
        enhanced_query = query.lower()
        for abbr, full_term in manufacturing_terms.items():
            if abbr in enhanced_query:
                enhanced_query = enhanced_query.replace(abbr, full_term)
        
        return enhanced_query
    
    def get_manufacturing_synonyms(self, terms):
        """Get comprehensive manufacturing-related synonyms"""
        synonyms = {
            'manual': 'procedure guide documentation handbook instructions',
            'process': 'procedure workflow operation method technique',
            'machine': 'equipment machinery device apparatus tool',
            'repair': 'maintenance fix troubleshoot service restore',
            'safety': 'security protocol compliance hazard protection',
            'training': 'education learning instruction course development',
            'quality': 'qc qa inspection control assurance standard',
            'production': 'manufacturing assembly fabrication processing',
            'maintenance': 'service repair upkeep preventive corrective',
            'sop': 'standard operating procedure protocol guideline',
            'inspection': 'check examination review audit verification',
            'calibration': 'adjustment tuning configuration setup',
            'troubleshooting': 'diagnosis problem-solving repair maintenance'
        }
        
        words = terms.lower().split()
        enhanced_words = []
        
        for word in words:
            enhanced_words.append(word)
            # Add exact matches
            if word in synonyms:
                enhanced_words.extend(synonyms[word].split())
            # Add partial matches
            for key, values in synonyms.items():
                if word in key or key in word:
                    enhanced_words.extend(values.split())
        
        return ' '.join(list(set(enhanced_words)))  # Remove duplicates
    
    def extract_search_terms(self, message):
        """Extract search terms with manufacturing context awareness"""
        # Simple but effective term extraction
        stop_words = {'search', 'find', 'look', 'for', 'the', 'a', 'an', 'show', 'me', 'get', 'retrieve', 
                     'where', 'is', 'are', 'can', 'you', 'please', 'help', 'i', 'want', 'need', 'document'}
        
        words = message.lower().split()
        filtered_words = [w for w in words if w not in stop_words and len(w) > 2]
        
        # If we have good keywords, use them
        if filtered_words:
            return ' '.join(filtered_words)
        
        # Otherwise return original message
        return message
    
    def create_broader_query(self, message):
        """Create a broader search query for fallback"""
        # Extract main concepts and create broader terms
        broader_terms = {
            'maintenance': 'maintenance repair service fix',
            'quality': 'quality control inspection QC QA',
            'safety': 'safety security protocol compliance',
            'production': 'production manufacturing process operation',
            'training': 'training education learning instruction',
            'manual': 'manual procedure guide handbook',
            'report': 'report analysis summary document',
            'interview': 'interview candidate hiring recruitment'
        }
        
        message_lower = message.lower()
        for key, broader in broader_terms.items():
            if key in message_lower:
                return broader
        
        # If no specific match, return a very broad search
        return 'document'
    
    def convert_score_to_number(self, score):
        """Convert Kendra score to numeric value"""
        if isinstance(score, (int, float)):
            return score
        elif isinstance(score, str):
            score_map = {
                'VERY_HIGH': 0.95,
                'HIGH': 0.85,
                'MEDIUM': 0.65,
                'LOW': 0.45
            }
            return score_map.get(score.upper(), 0.5)
        return 0.5
    
    def extract_document_name(self, message):
        """Extract document name from message"""
        if '"' in message:
            return message.split('"')[1]
        elif 'analyze' in message:
            return message.split('analyze')[-1].strip()
        else:
            words = message.split()
            doc_keywords = ['report', 'document', 'file', 'proposal', 'budget', 'financial']
            for i, word in enumerate(words):
                if word in doc_keywords and i < len(words) - 1:
                    return ' '.join(words[i:i+3])
            return message