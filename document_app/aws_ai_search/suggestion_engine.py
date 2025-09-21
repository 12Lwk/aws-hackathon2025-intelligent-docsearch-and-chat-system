import boto3
import json
import random
import hashlib
from datetime import datetime, timedelta
from django.conf import settings
from django.core.cache import cache
from ..aws_document_pipeline.kendra_database import KendraDatabase
from ..aws_credential_keys.config import (
    AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_REGION, 
    BEDROCK_REGION, BEDROCK_MODEL_ID
)

class SuggestionEngine:
    def __init__(self):
        self.kendra_db = KendraDatabase()
        self.bedrock_client = boto3.client(
            'bedrock-runtime',
            aws_access_key_id=AWS_ACCESS_KEY_ID,
            aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
            region_name=BEDROCK_REGION
        )
        
    def generate_dynamic_suggestions(self, user_context=None, limit=3, use_cache=True):
        """Generate dynamic search suggestions based on available documents and user context"""
        try:
            print(f"*** GENERATING DYNAMIC SUGGESTIONS ***")
            
            # Create cache key based on document collection state and context
            cache_key = self._generate_cache_key(user_context, limit)
            
            # Try to get cached suggestions first
            if use_cache:
                cached_suggestions = cache.get(cache_key)
                if cached_suggestions:
                    print(f"*** RETURNING {len(cached_suggestions)} CACHED SUGGESTIONS ***")
                    return cached_suggestions
            
            # Get document insights (with caching)
            document_insights = self._analyze_document_collection(use_cache=use_cache)
            
            # Generate AI-powered suggestions
            suggestions = self._generate_ai_suggestions(document_insights, user_context, limit)
            print(f"*** AI GENERATED SUGGESTIONS: {suggestions} ***")
            
            # Add fallback suggestions if needed
            if len(suggestions) < limit:
                print(f"*** NEED MORE SUGGESTIONS: {len(suggestions)}/{limit}, ADDING FALLBACKS ***")
                fallback_suggestions = self._get_fallback_suggestions(document_insights)
                suggestions.extend(fallback_suggestions[:limit - len(suggestions)])
                print(f"*** FINAL SUGGESTIONS WITH FALLBACKS: {suggestions} ***")
            
            # Cache the results for 30 minutes
            final_suggestions = suggestions[:limit]
            if use_cache and final_suggestions:
                cache.set(cache_key, final_suggestions, 1800)  # 30 minutes
            
            print(f"*** GENERATED {len(final_suggestions)} DYNAMIC SUGGESTIONS ***")
            return final_suggestions
            
        except Exception as e:
            print(f"*** SUGGESTION GENERATION ERROR: {e} ***")
            return self._get_default_suggestions()
    
    def _generate_cache_key(self, user_context, limit):
        """Generate a cache key based on document collection state and context"""
        try:
            # Get document collection stats for cache key
            stats = self.kendra_db.get_category_stats()
            stats_str = json.dumps(stats, sort_keys=True)
            
            # Include user context if available
            context_str = json.dumps(user_context or {}, sort_keys=True)
            
            # Create hash of the combined data
            cache_data = f"{stats_str}_{context_str}_{limit}"
            cache_hash = hashlib.md5(cache_data.encode()).hexdigest()
            
            return f"dynamic_suggestions_{cache_hash}"
            
        except Exception as e:
            print(f"*** CACHE KEY GENERATION ERROR: {e} ***")
            # Fallback to simple cache key
            return f"dynamic_suggestions_default_{limit}"
    
    def _analyze_document_collection(self, use_cache=True):
        """Analyze the current document collection to understand what's available"""
        try:
            # Try to get cached analysis first
            if use_cache:
                cached_analysis = cache.get('document_collection_analysis')
                if cached_analysis:
                    print(f"*** RETURNING CACHED DOCUMENT ANALYSIS ***")
                    return cached_analysis
            # Get sample documents from different categories
            categories = ['policies_guidelines', 'operations_production', 'maintenance_technical', 'training_knowledge', 'others']
            document_insights = {
                'categories': {},
                'common_keywords': [],
                'document_types': [],
                'total_documents': 0,
                'recent_documents': []
            }
            
            all_keywords = []
            all_titles = []
            
            for category in categories:
                docs = self.kendra_db.list_documents_by_category(category, limit=10)
                if docs:
                    document_insights['categories'][category] = {
                        'count': len(docs),
                        'sample_titles': [doc.get('title', '') for doc in docs[:3]],
                        'keywords': []
                    }
                    
                    # Collect keywords and titles
                    for doc in docs:
                        keywords = doc.get('attributes', {}).get('keywords', [])
                        if keywords:
                            all_keywords.extend(keywords)
                            document_insights['categories'][category]['keywords'].extend(keywords)
                        
                        title = doc.get('title', '')
                        if title:
                            all_titles.append(title)
                    
                    document_insights['total_documents'] += len(docs)
            
            # Find most common keywords
            if all_keywords:
                keyword_counts = {}
                for keyword in all_keywords:
                    keyword_counts[keyword] = keyword_counts.get(keyword, 0) + 1
                
                # Get top 10 most common keywords
                sorted_keywords = sorted(keyword_counts.items(), key=lambda x: x[1], reverse=True)
                document_insights['common_keywords'] = [kw[0] for kw in sorted_keywords[:10]]
            
            # Identify document types from titles
            document_types = set()
            for title in all_titles:
                title_lower = title.lower()
                if 'policy' in title_lower or 'procedure' in title_lower:
                    document_types.add('policies')
                elif 'manual' in title_lower or 'guide' in title_lower:
                    document_types.add('manuals')
                elif 'report' in title_lower:
                    document_types.add('reports')
                elif 'training' in title_lower:
                    document_types.add('training')
                elif 'process' in title_lower:
                    document_types.add('processes')
            
            document_insights['document_types'] = list(document_types)
            
            # Cache the analysis for 15 minutes
            if use_cache:
                cache.set('document_collection_analysis', document_insights, 900)  # 15 minutes
            
            print(f"*** DOCUMENT ANALYSIS: {document_insights['total_documents']} docs, {len(document_insights['common_keywords'])} keywords ***")
            return document_insights
            
        except Exception as e:
            print(f"*** DOCUMENT ANALYSIS ERROR: {e} ***")
            return {'categories': {}, 'common_keywords': [], 'document_types': [], 'total_documents': 0}
    
    def _generate_ai_suggestions(self, document_insights, user_context, limit=3):
        """Use AI to generate contextual search suggestions"""
        try:
            # Prepare context for AI
            context_info = []
            
            # Add document collection info
            if document_insights['total_documents'] > 0:
                context_info.append(f"Document collection contains {document_insights['total_documents']} documents")
                
                # Add category information with more detail
                for category, info in document_insights['categories'].items():
                    if info['count'] > 0:
                        sample_titles = ', '.join(info['sample_titles'][:2])
                        category_name = category.replace('_', ' ').title()
                        context_info.append(f"{category_name}: {info['count']} documents (examples: {sample_titles})")
                
                # Add common keywords with more context
                if document_insights['common_keywords']:
                    top_keywords = ', '.join(document_insights['common_keywords'][:5])
                    context_info.append(f"Common topics and keywords: {top_keywords}")
                
                # Add document types with examples
                if document_insights['document_types']:
                    doc_types = ', '.join(document_insights['document_types'])
                    context_info.append(f"Document types available: {doc_types}")
            else:
                context_info.append("No documents currently available in the system")
            
            context_str = '\n'.join(context_info)
            print(f"*** CONTEXT FOR AI: {context_str} ***")
            
            suggestion_prompt = f"""You are an AI assistant helping users discover documents in their collection. Based on the available documents, generate {limit} diverse, practical search suggestions that users would actually want to try.

Available Document Collection:
{context_str}

Generate {limit} search suggestions that:
1. Are specific to the actual documents available (use real keywords/topics from the collection)
2. Use natural language queries that demonstrate the AI search capabilities
3. Are diverse - cover different types of searches (specific documents, summaries, analysis, etc.)
4. Are practical and useful for business/organizational needs
5. Use quotation marks to show they are example queries

Format each suggestion as a quoted search query, like:
"Find the latest safety procedures"
"Summarize all training materials"
"What are the key points in the quality manual?"

Suggestions:"""
            
            response = self.bedrock_client.invoke_model(
                modelId=BEDROCK_MODEL_ID,
                body=json.dumps({
                    "messages": [{
                        "role": "user",
                        "content": [{"text": suggestion_prompt}]
                    }],
                    "inferenceConfig": {
                        "maxTokens": 200,
                        "temperature": 0.7,
                        "topP": 0.9
                    }
                })
            )
            
            response_body = json.loads(response['body'].read())
            ai_suggestions_text = response_body['output']['message']['content'][0]['text'].strip()
            
            # Parse suggestions from AI response
            suggestions = []
            lines = ai_suggestions_text.split('\n')
            for line in lines:
                line = line.strip()
                if line and (line.startswith('"') or line.startswith("'")) and (line.endswith('"') or line.endswith("'")):
                    # Clean up the suggestion
                    suggestion = line.strip('"\'').strip()
                    if suggestion and len(suggestion) > 10:  # Reasonable length check
                        suggestions.append(suggestion)
                elif '"' in line:
                    # Try to extract quoted text
                    import re
                    matches = re.findall(r'"([^"]*)"', line)
                    for match in matches:
                        if match and len(match) > 10:
                            suggestions.append(match)
            
            print(f"*** AI GENERATED {len(suggestions)} SUGGESTIONS ***")
            return suggestions[:limit]
            
        except Exception as e:
            print(f"*** AI SUGGESTION ERROR: {e} ***")
            return []
    
    def _get_fallback_suggestions(self, document_insights):
        """Generate fallback suggestions based on document analysis"""
        fallback_suggestions = []
        
        print(f"*** GENERATING FALLBACK SUGGESTIONS FROM: {document_insights} ***")
        
        # If we have documents, create document-aware suggestions
        if document_insights['total_documents'] > 0:
            # Category-based suggestions
            for category, info in document_insights['categories'].items():
                if info['count'] > 0:
                    category_name = category.replace('_', ' ').lower()
                    if category == 'policies_guidelines':
                        fallback_suggestions.append("Find policy and guideline documents")
                    elif category == 'operations_production':
                        fallback_suggestions.append("Show me operations and production documents")
                    elif category == 'maintenance_technical':
                        fallback_suggestions.append("Search for maintenance and technical manuals")
                    elif category == 'training_knowledge':
                        fallback_suggestions.append("Find training and knowledge materials")
                    else:
                        fallback_suggestions.append(f"Show me {category_name} documents")
            
            # Keyword-based suggestions
            if document_insights['common_keywords']:
                top_keywords = document_insights['common_keywords'][:3]
                for keyword in top_keywords:
                    fallback_suggestions.append(f"Search for documents about {keyword}")
            
            # Document type suggestions
            if 'policies' in document_insights['document_types']:
                fallback_suggestions.append("What policies do we have?")
            if 'manuals' in document_insights['document_types']:
                fallback_suggestions.append("Show me available manuals")
            if 'training' in document_insights['document_types']:
                fallback_suggestions.append("Find training materials")
            if 'reports' in document_insights['document_types']:
                fallback_suggestions.append("Search for reports and analysis")
            
            # Generic but document-aware suggestions
            fallback_suggestions.extend([
                "Summarize the most important documents",
                "What documents were uploaded recently?",
                "Find documents by category"
            ])
        else:
            # No documents available - encourage upload
            fallback_suggestions = [
                "Upload your first document to get started",
                "Add documents to enable smart search",
                "Learn about document management features"
            ]
        
        print(f"*** GENERATED {len(fallback_suggestions)} FALLBACK SUGGESTIONS ***")
        return fallback_suggestions
    
    def _get_default_suggestions(self):
        """Default suggestions when no documents are available or analysis fails"""
        return [
            "Upload your first document to get started",
            "Try searching for policies or procedures",
            "Ask me about document management"
        ]
    
    def track_user_interaction(self, query, result_clicked=False, user_session=None):
        """Track user interactions for future personalization"""
        try:
            interaction_data = {
                'timestamp': datetime.now().isoformat(),
                'query': query,
                'result_clicked': result_clicked,
                'user_session': user_session
            }
            
            # Store in user's search history (cache-based for now)
            if user_session:
                history_key = f"user_search_history_{user_session}"
                search_history = cache.get(history_key, [])
                
                # Add new interaction
                search_history.append(interaction_data)
                
                # Keep only last 50 interactions
                if len(search_history) > 50:
                    search_history = search_history[-50:]
                
                # Store back in cache for 24 hours
                cache.set(history_key, search_history, 86400)  # 24 hours
            
            # Update analytics
            self._update_suggestion_analytics(query, result_clicked)
            
            print(f"*** USER INTERACTION TRACKED: {query} ***")
            
        except Exception as e:
            print(f"*** INTERACTION TRACKING ERROR: {e} ***")
    
    def _update_suggestion_analytics(self, query, result_clicked):
        """Update suggestion analytics with new interaction data"""
        try:
            analytics = cache.get('suggestion_analytics', {
                'total_searches': 0,
                'total_clicks': 0,
                'popular_queries': {},
                'click_through_rate': 0
            })
            
            # Update counters
            analytics['total_searches'] += 1
            if result_clicked:
                analytics['total_clicks'] += 1
            
            # Update popular queries
            if 'popular_queries' not in analytics:
                analytics['popular_queries'] = {}
            
            query_lower = query.lower().strip()
            analytics['popular_queries'][query_lower] = analytics['popular_queries'].get(query_lower, 0) + 1
            
            # Calculate click-through rate
            if analytics['total_searches'] > 0:
                analytics['click_through_rate'] = analytics['total_clicks'] / analytics['total_searches']
            
            # Store updated analytics
            cache.set('suggestion_analytics', analytics, 86400)  # 24 hours
            
        except Exception as e:
            print(f"*** ANALYTICS UPDATE ERROR: {e} ***")
    
    def get_personalized_suggestions(self, user_session=None, limit=3):
        """Get personalized suggestions based on user history"""
        try:
            # Get user's search history from cache
            user_history = self._get_user_search_history(user_session)
            
            if user_history and len(user_history) > 0:
                # Generate suggestions based on user's search patterns
                personalized_context = {
                    'session': user_session,
                    'search_history': user_history,
                    'preferences': self._analyze_user_preferences(user_history)
                }
                return self.generate_dynamic_suggestions(user_context=personalized_context, limit=limit)
            else:
                # Fallback to general dynamic suggestions
                return self.generate_dynamic_suggestions(user_context={'session': user_session}, limit=limit)
                
        except Exception as e:
            print(f"*** PERSONALIZED SUGGESTIONS ERROR: {e} ***")
            return self.generate_dynamic_suggestions(user_context={'session': user_session}, limit=limit)
    
    def _get_user_search_history(self, user_session):
        """Get user's search history from cache"""
        if not user_session:
            return []
        
        history_key = f"user_search_history_{user_session}"
        return cache.get(history_key, [])
    
    def _analyze_user_preferences(self, search_history):
        """Analyze user's search patterns to understand preferences"""
        preferences = {
            'common_terms': [],
            'preferred_categories': [],
            'search_patterns': []
        }
        
        if not search_history:
            return preferences
        
        # Analyze common terms
        all_terms = []
        for search in search_history:
            query = search.get('query', '').lower()
            terms = [term.strip() for term in query.split() if len(term.strip()) > 2]
            all_terms.extend(terms)
        
        # Find most common terms
        if all_terms:
            term_counts = {}
            for term in all_terms:
                term_counts[term] = term_counts.get(term, 0) + 1
            
            # Get top 5 most common terms
            sorted_terms = sorted(term_counts.items(), key=lambda x: x[1], reverse=True)
            preferences['common_terms'] = [term[0] for term in sorted_terms[:5]]
        
        return preferences
    
    def get_suggestion_analytics(self):
        """Get analytics about suggestion usage and effectiveness"""
        try:
            analytics = {
                'total_suggestions_generated': 0,
                'cache_hit_rate': 0,
                'popular_suggestions': [],
                'user_engagement': {},
                'document_coverage': {}
            }
            
            # Get analytics from cache (in a real implementation, this would be from a database)
            cached_analytics = cache.get('suggestion_analytics', {})
            analytics.update(cached_analytics)
            
            # Add current document collection stats
            document_insights = self._analyze_document_collection()
            analytics['document_coverage'] = {
                'total_documents': document_insights['total_documents'],
                'categories': len(document_insights['categories']),
                'keywords': len(document_insights['common_keywords']),
                'document_types': len(document_insights['document_types'])
            }
            
            return analytics
            
        except Exception as e:
            print(f"*** ANALYTICS ERROR: {e} ***")
            return {'error': str(e)}
    
    def clear_suggestion_cache(self):
        """Clear all suggestion-related cache entries"""
        try:
            # Clear document analysis cache
            cache.delete('document_collection_analysis')
            
            # Clear suggestion caches (this is a simplified approach)
            # In a real implementation, you'd track cache keys more systematically
            cache_keys = [
                'dynamic_suggestions_default_3',
                'suggestion_analytics'
            ]
            
            for key in cache_keys:
                cache.delete(key)
            
            print("*** SUGGESTION CACHE CLEARED ***")
            return True
            
        except Exception as e:
            print(f"*** CACHE CLEAR ERROR: {e} ***")
            return False
