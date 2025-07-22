from django.urls import path
from . import views

app_name = 'parser'

urlpatterns = [
    path('', views.index, name='index'),
    path('upload/', views.upload_resumes, name='upload_resumes'),
    path('get-resumes/', views.get_resumes, name='get_resumes'),
    path('view-resume/<int:resume_id>/', views.view_resume, name='view_resume'),
    path('download-resume/<int:resume_id>/', views.download_resume, name='download_resume'),
]