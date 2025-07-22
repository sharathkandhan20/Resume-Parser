from django.shortcuts import render, redirect
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required
import json
import logging

from .models import Resume
from .utils.parser import SimpleResumeParser

logger = logging.getLogger(__name__)

@login_required
def index(request):
    """Main page view"""
    resumes = Resume.objects.all().order_by('-created_at')
    return render(request, 'parser/index.html', {
        'resumes': resumes,
        'user': request.user
    })

@csrf_exempt
@login_required
def upload_resumes(request):
    """Handle resume upload and parsing"""
    if request.method == 'POST':
        files = request.FILES.getlist('resumes')
        
        if not files:
            return JsonResponse({'error': 'No files uploaded'}, status=400)
        
        results = []
        parser = SimpleResumeParser()
        
        for uploaded_file in files:
            try:
                # Read file content
                file_content = uploaded_file.read()
                
                # Process the resume
                result = parser.process_resume(
                    file_obj=file_content,
                    filename=uploaded_file.name
                )
                
                if result['success'] and result['data']:
                    resume_data = result['data']
                    
                    # Create or update resume record
                    resume, created = Resume.objects.update_or_create(
                        filename=uploaded_file.name,
                        defaults={
                            'name': resume_data.get('name'),
                            'email': resume_data.get('email'),
                            'phone': resume_data.get('phone'),
                            'linkedin': resume_data.get('linkedin'),
                            'github': resume_data.get('github'),
                            'skills': json.dumps(resume_data.get('skills', [])),
                            'ug_degree': resume_data.get('ug_degree'),
                            'ug_college': resume_data.get('ug_college'),
                            'ug_year': resume_data.get('ug_year'),
                            'pg_degree': resume_data.get('pg_degree'),
                            'pg_college': resume_data.get('pg_college'),
                            'pg_year': resume_data.get('pg_year'),
                            'total_experience_years': resume_data.get('total_experience_years'),
                            'work_experience': json.dumps(resume_data.get('work_experience', [])),
                            'raw_resume': file_content,
                            'mime_type': uploaded_file.content_type or 'application/octet-stream',
                            'uploaded_by': request.user  # Track who uploaded
                        }
                    )
                    
                    results.append({
                        'filename': uploaded_file.name,
                        'success': True,
                        'message': 'Parsed successfully'
                    })
                else:
                    results.append({
                        'filename': uploaded_file.name,
                        'success': False,
                        'message': result.get('error', 'Failed to parse')
                    })
                    
            except Exception as e:
                logger.error(f"Error processing {uploaded_file.name}: {e}")
                results.append({
                    'filename': uploaded_file.name,
                    'success': False,
                    'message': str(e)
                })
        
        return JsonResponse({'results': results})
    
    return JsonResponse({'error': 'Method not allowed'}, status=405)

@login_required
def get_resumes(request):
    """Get all resumes data"""
    resumes = Resume.objects.all().order_by('-created_at')
    
    resume_data = []
    for resume in resumes:
        data = {
            'id': resume.id,
            'filename': resume.filename,
            'name': resume.name or 'N/A',
            'email': resume.email or 'N/A',
            'phone': resume.phone or 'N/A',
            'linkedin': resume.linkedin or 'N/A',
            'github': resume.github or 'N/A',
            'skills': resume.get_skills_list(),
            'ug_degree': resume.ug_degree or 'N/A',
            'ug_college': resume.ug_college or 'N/A',
            'ug_year': resume.ug_year or 'N/A',
            'pg_degree': resume.pg_degree or 'N/A',
            'pg_college': resume.pg_college or 'N/A',
            'pg_year': resume.pg_year or 'N/A',
            'experience': resume.total_experience_years or 'N/A',
            'created_at': resume.created_at.strftime('%Y-%m-%d %H:%M')
        }
        
        # Add uploaded_by info for admins
        if hasattr(request.user, 'is_admin') and request.user.is_admin and resume.uploaded_by:
            data['uploaded_by'] = resume.uploaded_by.email
        
        resume_data.append(data)
    
    return JsonResponse({'resumes': resume_data})

@login_required
def view_resume(request, resume_id):
    """View resume file"""
    try:
        resume = Resume.objects.get(id=resume_id)
        if resume.raw_resume:
            response = HttpResponse(resume.raw_resume, content_type=resume.mime_type)
            response['Content-Disposition'] = f'inline; filename="{resume.filename}"'
            return response
        else:
            return HttpResponse("No resume file found", status=404)
    except Resume.DoesNotExist:
        return HttpResponse("Resume not found", status=404)

@login_required
def download_resume(request, resume_id):
    """Download resume file"""
    try:
        resume = Resume.objects.get(id=resume_id)
        if resume.raw_resume:
            response = HttpResponse(resume.raw_resume, content_type=resume.mime_type)
            response['Content-Disposition'] = f'attachment; filename="{resume.filename}"'
            return response
        else:
            return HttpResponse("No resume file found", status=404)
    except Resume.DoesNotExist:
        return HttpResponse("Resume not found", status=404)