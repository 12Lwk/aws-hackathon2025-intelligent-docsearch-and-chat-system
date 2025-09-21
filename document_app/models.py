from django.db import models
from django.utils import timezone
import uuid

class Document(models.Model):
    STATUS_CHOICES = [
        ('uploaded', 'Uploaded'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]
    
    CATEGORY_CHOICES = [
        ('policies_guidelines', 'Policies & Guidelines'),
        ('operations_production', 'Operations & Production'),
        ('maintenance_technical', 'Maintenance & Technical'),
        ('training_knowledge', 'Training & Knowledge'),
        ('others', 'Others'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    file_name = models.CharField(max_length=255)
    s3_key = models.CharField(max_length=500)
    file_type = models.CharField(max_length=50)
    file_size = models.IntegerField()
    upload_date = models.DateTimeField(auto_now_add=True)
    processing_status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='uploaded')
    category = models.CharField(max_length=30, choices=CATEGORY_CHOICES, blank=True)
    confidence_score = models.FloatField(null=True, blank=True)
    extracted_text = models.TextField(blank=True)
    keywords = models.JSONField(default=list, blank=True)
    classification_method = models.CharField(max_length=50, blank=True, help_text='Method used for classification (bedrock, fallback, text)')
    processed_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True)
    
    class Meta:
        ordering = ['-upload_date']
    
    def __str__(self):
        return self.file_name


class RecentView(models.Model):
    """Track user document views and downloads for recent activity"""
    
    ACTION_CHOICES = [
        ('view', 'View'),
        ('download', 'Download'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    document_id = models.CharField(max_length=255, help_text='Document ID from Kendra or local database')
    document_title = models.CharField(max_length=500)
    document_category = models.CharField(max_length=100, blank=True)
    action_type = models.CharField(max_length=10, choices=ACTION_CHOICES)
    user_session = models.CharField(max_length=100, blank=True, help_text='User session identifier')
    user_ip = models.GenericIPAddressField(blank=True, null=True)
    timestamp = models.DateTimeField(default=timezone.now)
    file_type = models.CharField(max_length=50, blank=True)
    file_size = models.CharField(max_length=50, blank=True)
    
    class Meta:
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['-timestamp']),
            models.Index(fields=['user_session', '-timestamp']),
            models.Index(fields=['document_id']),
        ]
    
    def __str__(self):
        return f"{self.action_type.title()}: {self.document_title} at {self.timestamp}"
    
    @property
    def time_ago(self):
        """Return human-readable time difference"""
        from django.utils.timesince import timesince
        return timesince(self.timestamp)
    
    @classmethod
    def get_recent_views(cls, limit=10, user_session=None):
        """Get recent views, optionally filtered by user session"""
        queryset = cls.objects.all()
        if user_session:
            queryset = queryset.filter(user_session=user_session)
        return queryset[:limit]
    
    @classmethod
    def track_document_activity(cls, document_id, document_title, action_type, 
                              user_session=None, user_ip=None, document_category='', 
                              file_type='', file_size=''):
        """Track a document view or download activity"""
        return cls.objects.create(
            document_id=document_id,
            document_title=document_title,
            document_category=document_category,
            action_type=action_type,
            user_session=user_session,
            user_ip=user_ip,
            file_type=file_type,
            file_size=file_size
        )