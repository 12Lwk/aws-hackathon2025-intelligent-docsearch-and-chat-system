import boto3
import json
from django.conf import settings
from ..aws_document_pipeline.kendra_database import KendraDatabase
from ..aws_credential_keys.config import (
    AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_REGION, 
    BEDROCK_REGION, BEDROCK_MODEL_ID, AWS_KENDRA_INDEX_ID
)

class AISearchEngine:
    def __init__(self):
        self.kendra_db = KendraDatabase()
        self.bedrock_client = boto3.client(
            'bedrock-runtime',
            aws_access_key_id=AWS_ACCESS_KEY_ID,
            aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
            region_name=BEDROCK_REGION
        )

    def perform_search(self, query, category_filter=None, max_results=5, min_similarity=0.8):
        """Performs an intelligent search and returns relevant documents."""
        print(f"*** AI SEARCH: '{query}' ***")
        try:
            # Direct search with Kendra
            search_results = self.kendra_db.search_documents(query, category_filter=category_filter, limit=max_results * 2)
            
            if not search_results:
                return [], "No documents found for your query."
            
            # Filter by similarity and rank results
            filtered_results = self._filter_by_similarity(search_results, min_similarity)
            
            if not filtered_results:
                return [], f"No documents found with similarity above {min_similarity * 100}%."
            
            return filtered_results[:max_results], ""
            
        except Exception as e:
            print(f"*** AI SEARCH ERROR: {e} ***")
            return [], f"Search failed: {str(e)}"

    def _extract_intelligent_search_terms(self, query):
        """Use LLM to extract the most relevant search terms from user query."""
        extraction_prompt = f"""Extract the most important search terms from this user query for document search.

User query: "{query}"

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
            return terms if terms else query
            
        except Exception as e:
            print(f"*** TERM EXTRACTION ERROR: {e} ***")
            # Fallback to original query
            return query
    
    def _perform_multi_strategy_search(self, original_query, search_terms, category_filter, max_results):
        """Perform multi-strategy search similar to chatbot approach."""
        results = None
        
        # Strategy 1: Direct search with extracted intelligent terms
        if search_terms and search_terms != original_query:
            print(f"*** STRATEGY 1: Searching with intelligent terms: '{search_terms}' ***")
            results = self.kendra_db.search_documents(search_terms, category_filter=category_filter, limit=max_results * 2)
            print(f"*** STRATEGY 1 RESULTS: {len(results) if results else 0} ***")
        
        # Strategy 2: Enhanced query search if no results
        if not results:
            enhanced_query = self._enhance_search_query(original_query)
            print(f"*** STRATEGY 2: Searching with enhanced query: '{enhanced_query}' ***")
            results = self.kendra_db.search_documents(enhanced_query, category_filter=category_filter, limit=max_results * 2)
            print(f"*** STRATEGY 2 RESULTS: {len(results) if results else 0} ***")
        
        # Strategy 3: Broader search if still no results
        if not results:
            broader_query = self._create_broader_query(original_query)
            print(f"*** STRATEGY 3: Searching with broader query: '{broader_query}' ***")
            results = self.kendra_db.search_documents(broader_query, category_filter=category_filter, limit=max_results * 2)
            print(f"*** STRATEGY 3 RESULTS: {len(results) if results else 0} ***")
        
        return results or []
    
    def _enhance_search_query(self, query):
        """Enhance the original query with related terms."""
        try:
            enhancement_prompt = f"""Enhance this search query to find more relevant documents by adding related terms and synonyms.

Original query: "{query}"

Create an enhanced version that:
1. Keeps the original intent
2. Adds relevant synonyms and related terms
3. Includes common document types that might contain this information
4. Uses terms that would appear in professional documents

Enhanced query:"""
            
            response = self.bedrock_client.invoke_model(
                modelId=BEDROCK_MODEL_ID,
                body=json.dumps({
                    "messages": [{
                        "role": "user",
                        "content": [{"text": enhancement_prompt}]
                    }],
                    "inferenceConfig": {
                        "maxTokens": 100,
                        "temperature": 0.3,
                        "topP": 0.8
                    }
                })
            )
            
            response_body = json.loads(response['body'].read())
            enhanced = response_body['output']['message']['content'][0]['text'].strip()
            return enhanced if enhanced else query
            
        except Exception as e:
            print(f"*** QUERY ENHANCEMENT ERROR: {e} ***")
            return query
    
    def _create_broader_query(self, query):
        """Create a broader search query as fallback."""
        # Extract key words and create broader terms
        words = query.lower().split()
        key_words = [word for word in words if len(word) > 3 and word not in ['the', 'and', 'for', 'with', 'this', 'that']]
        
        if key_words:
            # Use the most important words
            return ' '.join(key_words[:3])
        else:
            # Very broad fallback
            return 'document process procedure'
    
    def _intelligent_result_ranking(self, query, results):
        """Use LLM to intelligently rank and select the best results."""
        if not results:
            return []
        
        if len(results) == 1:
            results[0]['relevance_score'] = 1.0
            return results
        
        # Use LLM to select the best results
        try:
            best_results = self._select_best_results_with_llm(query, results)
            
            # Add relevance scores
            for i, result in enumerate(best_results):
                # Higher score for earlier positions
                result['relevance_score'] = 1.0 - (i * 0.1)
            
            return best_results
            
        except Exception as e:
            print(f"*** INTELLIGENT RANKING ERROR: {e} ***")
            # Fallback to simple ranking
            return self._simple_result_ranking(query, results)
    
    def _select_best_results_with_llm(self, query, results):
        """Use LLM to select and rank the most relevant results."""
        if len(results) <= 3:
            return results
        
        # Create summaries for LLM evaluation
        result_summaries = []
        for i, result in enumerate(results[:10]):  # Evaluate top 10
            title = result.get('title', 'Unknown')
            excerpt = result.get('excerpt', '')[:200]
            category = result.get('attributes', {}).get('category', 'Unknown')
            result_summaries.append(f"{i+1}. {title} (Category: {category}) - {excerpt}")
        
        ranking_prompt = f"""Given this user query and search results, rank the top 5 most relevant documents.

User query: "{query}"

Search results:
{chr(10).join(result_summaries)}

Rank the top 5 results by relevance to the user's query. Consider:
- Direct relevance to the query
- Document type appropriateness
- Content quality and completeness

Respond with only the numbers (e.g., "3 1 7 2 9"):"""
        
        try:
            response = self.bedrock_client.invoke_model(
                modelId=BEDROCK_MODEL_ID,
                body=json.dumps({
                    "messages": [{
                        "role": "user",
                        "content": [{"text": ranking_prompt}]
                    }],
                    "inferenceConfig": {
                        "maxTokens": 30,
                        "temperature": 0.1,
                        "topP": 0.7
                    }
                })
            )
            
            response_body = json.loads(response['body'].read())
            ranking = response_body['output']['message']['content'][0]['text'].strip()
            
            # Parse ranking and reorder results
            try:
                indices = [int(x) - 1 for x in ranking.split() if x.isdigit()]
                ranked_results = []
                
                for idx in indices:
                    if 0 <= idx < len(results):
                        ranked_results.append(results[idx])
                
                # Add any remaining results
                for i, result in enumerate(results):
                    if i not in indices and len(ranked_results) < len(results):
                        ranked_results.append(result)
                
                return ranked_results[:10]  # Return top 10
                
            except (ValueError, IndexError):
                pass
                
        except Exception as e:
            print(f"*** LLM RANKING ERROR: {e} ***")
        
        # Fallback to original order
        return results
    
    def _simple_result_ranking(self, query, results):
        """Fallback simple ranking method."""
        for result in results:
            score = self._calculate_relevance_score(query, result)
            result['relevance_score'] = score
        
        return sorted(results, key=lambda x: x['relevance_score'], reverse=True)
    
    def _calculate_relevance_score(self, query, result):
        """Calculate basic relevance score."""
        kendra_score = result.get('score', 0)
        if isinstance(kendra_score, str):
            score_map = {'VERY_HIGH': 1.0, 'HIGH': 0.8, 'MEDIUM': 0.6, 'LOW': 0.4}
            kendra_score = score_map.get(kendra_score.upper(), 0.5)
        
        # Boost score if query keywords appear in title or excerpt
        term_boost = 0
        query_terms = set(query.lower().split())
        title_terms = set(result.get('title', '').lower().split())
        excerpt_terms = set(result.get('excerpt', '').lower().split())

        if query_terms.intersection(title_terms):
            term_boost += 0.2
        if query_terms.intersection(excerpt_terms):
            term_boost += 0.1

        return kendra_score + term_boost
    
    def _filter_by_similarity(self, results, min_similarity=0.8):
        """Filter results by similarity threshold (80% to 100%)"""
        if not results:
            return []
        
        filtered_results = []
        for result in results:
            # Get Kendra score - it comes as 'score' field
            kendra_score = result.get('score', 0)
            
            # Convert Kendra confidence scores to numeric
            if isinstance(kendra_score, str):
                score_map = {'VERY_HIGH': 0.95, 'HIGH': 0.85, 'MEDIUM': 0.75, 'LOW': 0.65}
                relevance_score = score_map.get(kendra_score.upper(), 0.5)
            else:
                # If it's already numeric, use it directly but ensure it's in 0-1 range
                relevance_score = min(max(float(kendra_score), 0.0), 1.0)
            
            print(f"*** DOCUMENT: '{result.get('title', 'Unknown')}' - Similarity: {relevance_score * 100:.1f}% ***")
            
            # Lower the threshold to 60% to show more results
            actual_threshold = 0.6  # 60% instead of 80%
            
            if relevance_score >= actual_threshold:
                result['relevance_score'] = relevance_score
                result['similarity_percentage'] = round(relevance_score * 100, 1)
                filtered_results.append(result)
                print(f"*** INCLUDED: Above {actual_threshold * 100}% threshold ***")
            else:
                print(f"*** EXCLUDED: Below {actual_threshold * 100}% threshold ***")
        
        # Sort by relevance score (highest first)
        filtered_results.sort(key=lambda x: x.get('relevance_score', 0), reverse=True)
        
        return filtered_results
    
    def _generate_intelligent_summary(self, query, ranked_results):
        """Generate intelligent summary with context about the search results."""
        try:
            if not ranked_results:
                return "No relevant documents found for your query."
            
            # Prepare document information
            top_docs_info = []
            for doc in ranked_results[:3]:  # Summarize top 3
                title = doc.get('title', 'Unknown Document')
                category = doc.get('attributes', {}).get('category', 'Unknown')
                excerpt = doc.get('excerpt', '')[:200]
                relevance = doc.get('relevance_score', 0)
                
                info = f"- **{title}** (Category: {category}, Relevance: {relevance:.0%}) - {excerpt}..."
                top_docs_info.append(info)
            
            documents_str = "\n".join(top_docs_info)
            
            summary_prompt = f"""You are an intelligent search assistant. Based on the user's query and the top documents found, provide a helpful summary.

User Query: "{query}"

Top Documents Found:
{documents_str}

Create a summary that:
1. Acknowledges what the user was looking for
2. Briefly describes what was found and why it's relevant
3. Highlights key information from the top results
4. Is conversational and helpful

Summary:"""
            
            response = self.bedrock_client.invoke_model(
                modelId=BEDROCK_MODEL_ID,
                body=json.dumps({
                    "messages": [{
                        "role": "user",
                        "content": [{"text": summary_prompt}]
                    }],
                    "inferenceConfig": {
                        "maxTokens": 250,
                        "temperature": 0.3,
                        "topP": 0.8
                    }
                })
            )
            
            response_body = json.loads(response['body'].read())
            summary = response_body['output']['message']['content'][0]['text'].strip()
            
            return summary if summary else f"Found {len(ranked_results)} relevant documents for your query about {query}."
            
        except Exception as e:
            print(f"*** INTELLIGENT SUMMARY ERROR: {e} ***")
            return f"Found {len(ranked_results)} relevant documents matching your search for '{query}'."
    
    def _generate_helpful_no_results_response(self, query):
        """Generate helpful response when no results are found."""
        try:
            no_results_prompt = f"""The user searched for "{query}" but no documents were found. Provide a helpful response that:

1. Acknowledges that no documents were found
2. Suggests alternative search terms or approaches
3. Provides general guidance on document search
4. Is encouraging and helpful

Response:"""
            
            response = self.bedrock_client.invoke_model(
                modelId=BEDROCK_MODEL_ID,
                body=json.dumps({
                    "messages": [{
                        "role": "user",
                        "content": [{"text": no_results_prompt}]
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
            print(f"*** NO RESULTS RESPONSE ERROR: {e} ***")
            return f"No documents found for '{query}'. Try using different keywords, broader terms, or check if documents have been uploaded to the system."
    
    def _generate_query_suggestions(self, query, top_results):
        """Generate intelligent query suggestions based on search results."""
        if not top_results:
            return None
            
        try:
            # Prepare information about top results
            results_info = []
            for result in top_results:
                title = result.get('title', 'Unknown')
                category = result.get('attributes', {}).get('category', 'Unknown')
                excerpt = result.get('excerpt', '')[:150]
                results_info.append(f"- {title} (Category: {category}): {excerpt}")
            
            results_str = "\n".join(results_info)
            
            suggestion_prompt = f"""Based on the user's search query and the documents found, suggest 3 related search queries that might interest the user.

Original query: "{query}"

Documents found:
{results_str}

Suggest 3 specific, actionable search queries that:
1. Are related but different from the original query
2. Could help the user find additional relevant information
3. Are based on the content and categories of the found documents
4. Are phrased as natural search queries

Format as:
• [suggestion 1]
• [suggestion 2] 
• [suggestion 3]

Suggestions:"""
            
            response = self.bedrock_client.invoke_model(
                modelId=BEDROCK_MODEL_ID,
                body=json.dumps({
                    "messages": [{
                        "role": "user",
                        "content": [{"text": suggestion_prompt}]
                    }],
                    "inferenceConfig": {
                        "maxTokens": 120,
                        "temperature": 0.4,
                        "topP": 0.8
                    }
                })
            )
            
            response_body = json.loads(response['body'].read())
            suggestions = response_body['output']['message']['content'][0]['text'].strip()
            
            return suggestions if suggestions else None
            
        except Exception as e:
            print(f"*** QUERY SUGGESTIONS ERROR: {e} ***")
            return None
