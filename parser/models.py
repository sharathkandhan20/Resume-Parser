# models.py
from django.db import models
import json
from django.conf import settings
import hashlib

class Resume(models.Model):
    filename = models.CharField(max_length=255)
    name = models.CharField(max_length=255, null=True, blank=True)
    email = models.EmailField(null=True, blank=True)
    phone = models.CharField(max_length=50, null=True, blank=True)
    linkedin = models.URLField(null=True, blank=True)
    github = models.URLField(null=True, blank=True)
    skills = models.TextField(null=True, blank=True)  # JSON string
    ug_degree = models.CharField(max_length=255, null=True, blank=True)
    ug_college = models.CharField(max_length=255, null=True, blank=True)
    ug_year = models.IntegerField(null=True, blank=True)
    pg_degree = models.CharField(max_length=255, null=True, blank=True)
    pg_college = models.CharField(max_length=255, null=True, blank=True)
    pg_year = models.IntegerField(null=True, blank=True)
    total_experience_years = models.CharField(max_length=20, null=True, blank=True)
    work_experience = models.TextField(null=True, blank=True)  # JSON string
    raw_resume = models.BinaryField(null=True, blank=True)
    mime_type = models.CharField(max_length=100, null=True, blank=True)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    content_hash = models.CharField(max_length=64, db_index=True, null=True, blank=True)  # SHA256 hash
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'resumes'
        
    def get_skills_list(self):
        if self.skills:
            try:
                return json.loads(self.skills)
            except:
                return []
        return []
    
    def get_work_experience_list(self):
        if self.work_experience:
            try:
                return json.loads(self.work_experience)
            except:
                return []
        return []
    
    @staticmethod
    def calculate_content_hash(file_content):
        """Calculate SHA256 hash of file content"""
        return hashlib.sha256(file_content).hexdigest()
