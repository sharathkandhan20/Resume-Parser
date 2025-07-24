# views.py
from django.shortcuts import render, redirect
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required
from django.db.models import Q
import json
import logging

from .models import Resume
from .utils.parser import SimpleResumeParser

logger = logging.getLogger(__name__)


@login_required
def index(request):
    """Main page view"""
    if request.user.is_admin:
        resumes = Resume.objects.all().order_by('-created_at')
    else:
        resumes = Resume.objects.filter(uploaded_by=request.user).order_by('-created_at')
    
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
                
                # Calculate content hash
                content_hash = Resume.calculate_content_hash(file_content)
                
                # Check if this user has already uploaded this exact resume
                existing_resume = Resume.objects.filter(
                    uploaded_by=request.user,
                    content_hash=content_hash
                ).first()
                
                if existing_resume:
                    # Resume already exists for this user
                    results.append({
                        'filename': uploaded_file.name,
                        'success': False,
                        'message': 'You have already parsed this resume.',
                        'is_duplicate': True
                    })
                    continue
                
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
                            'uploaded_by': request.user,  # Track who uploaded
                            'content_hash': content_hash  # Store content hash
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
    """Render the resume list page with all resumes"""
    if request.user.is_admin:
        resumes = Resume.objects.all().order_by('-created_at')
    else:
        resumes = Resume.objects.filter(uploaded_by=request.user).order_by('-created_at')
    
    context = {'resumes': resumes}
    return render(request, 'parser/list_resume.html', context)


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


@login_required
def skill_suggestions(request):
    """Get skill suggestions based on query - from ALL resumes in database"""
    query = request.GET.get('q', '').strip()
    
    if len(query) < 2:
        return JsonResponse({'skills': []})
    
    try:
        # Get all resumes from database (not just current user's)
        all_resumes = Resume.objects.all()
        
        # Extract all unique skills
        all_skills = set()
        for resume in all_resumes:
            skills_list = resume.get_skills_list()
            for skill in skills_list:
                if skill:  # Skip empty skills
                    all_skills.add(skill)
        
        # Filter skills that match the query (case-insensitive)
        matching_skills = []
        query_lower = query.lower()
        
        for skill in all_skills:
            if query_lower in skill.lower():
                matching_skills.append(skill)
        
        # Sort by relevance (skills starting with query first)
        matching_skills.sort(key=lambda s: (
            not s.lower().startswith(query_lower),  # Starts with query = higher priority
            s.lower()
        ))
        
        # Limit to top 10 suggestions
        matching_skills = matching_skills[:10]
        
        return JsonResponse({'skills': matching_skills})
        
    except Exception as e:
        logger.error(f"Error getting skill suggestions: {e}")
        return JsonResponse({'skills': []})


@login_required
def filter_resumes(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    try:
        data = json.loads(request.body)
        mandatory_skills = data.get('mandatory_skills', [])
        optional_skills = data.get('optional_skills', [])

        if request.user.is_admin:
            resumes = Resume.objects.all()
        else:
            resumes = Resume.objects.filter(uploaded_by=request.user)

        def normalize_skill(s):
            return s.strip().lower().replace(' ', '').replace('.', '')

        filtered_resumes = []

        for resume in resumes:
            resume_skills = resume.get_skills_list()
            resume_skills_normalized = [normalize_skill(s) for s in resume_skills]

            # --- Mandatory filter ---
            if mandatory_skills:
                all_mandatory_present = all(
                    normalize_skill(skill) in resume_skills_normalized for skill in mandatory_skills
                )
                if not all_mandatory_present:
                    continue  # Skip resume if any mandatory skill is missing

            # --- Optional filter ---
            if not mandatory_skills and optional_skills:
                any_optional_present = any(
                    normalize_skill(skill) in resume_skills_normalized for skill in optional_skills
                )
                if not any_optional_present:
                    continue  # Only optional selected and no match → skip

            # Resume passes the filters
            filtered_resumes.append({
                'id': resume.id,
                'name': resume.name,
                'email': resume.email,
                'phone': resume.phone,
                'skills': resume_skills,
                'total_experience_years': resume.total_experience_years if resume.total_experience_years else "N/A",
                'uploaded_by_email': resume.uploaded_by.email if resume.uploaded_by else "N/A"
            })

        # Sort latest first
        filtered_resumes.sort(key=lambda r: r['id'], reverse=True)

        return JsonResponse({'resumes': filtered_resumes})

    except Exception as e:
        logger.error(f"Error filtering resumes: {e}")
        return JsonResponse({'error': str(e)}, status=500)
