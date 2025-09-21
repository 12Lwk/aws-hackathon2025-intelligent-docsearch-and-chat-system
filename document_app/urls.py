from django.urls import path
from . import views

urlpatterns = [
    # Page views
    path('', views.home, name='home'),
    path('search/', views.search, name='search'),
    path('chatbot/', views.chatbot, name='chatbot'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('upload/', views.upload, name='upload'),
    path('settings/', views.settings, name='settings'),
    
    # API endpoints for Kendra database
    path('api/upload-files/', views.upload_files, name='upload_files'),
    path('api/documents/', views.list_documents, name='list_documents'),
    
    # Specific document actions must come BEFORE the generic document ID route
    path('api/documents/view/', views.view_document, name='view_document'),
    path('api/documents/download/', views.download_document, name='download_document'),

    # Generic routes with path converters
    path('api/documents/<str:document_id>/', views.get_document_status, name='get_document_status'),
    path('api/document-status/<str:document_id>/', views.get_document_status, name='get_document_status_alt'),
    path('api/debug-doc/<str:document_id>/', views.debug_specific_document, name='debug_specific_document'),

    # Other API endpoints
    path('api/test/', views.test_endpoint, name='test_endpoint'),
    path('api/debug/', views.debug_documents, name='debug_documents'),
    path('api/test-upload/', views.test_document_upload, name='test_document_upload'),
    path('api/search/', views.search_documents, name='search_documents'),
    path('api/ai-search/', views.ai_search, name='ai_search'),
    path('api/chatbot/', views.chatbot_api, name='chatbot_api'),
    
    # Dynamic suggestions and interaction tracking
    path('api/suggestions/', views.get_dynamic_suggestions, name='get_dynamic_suggestions'),
    path('api/suggestions/personalized/', views.get_personalized_suggestions, name='get_personalized_suggestions'),
    path('api/track-interaction/', views.track_search_interaction, name='track_search_interaction'),
    
    # Analytics and cache management
    path('api/suggestions/analytics/', views.get_suggestion_analytics, name='get_suggestion_analytics'),
    path('api/suggestions/clear-cache/', views.clear_suggestion_cache, name='clear_suggestion_cache'),
    
    # Recent views tracking
    path('api/recent-views/', views.get_recent_views, name='get_recent_views'),
    path('api/track-activity/', views.track_document_activity, name='track_document_activity'),
    path('api/recent-views/clear/', views.clear_recent_views, name='clear_recent_views'),
    
    # Document management and folder view
    path('api/documents/category/', views.get_documents_by_category, name='get_documents_by_category'),
    path('api/folder-structure/', views.get_folder_structure, name='get_folder_structure'),
    path('api/documents/delete/', views.delete_document, name='delete_document'),
    
    # Debug endpoint
    path('api/debug-storage/', views.debug_storage, name='debug_storage'),
    path('api/test-category/', views.test_category_api, name='test_category_api'),
    path('api/simple-test/', views.simple_test_documents, name='simple_test_documents'),
    
    # Category view page
    path('category/<str:category>/', views.category_view, name='category_view'),
]