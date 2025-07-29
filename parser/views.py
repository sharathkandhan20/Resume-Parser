# views.py
from django.shortcuts import render, redirect
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required
from django.db.models import Q
import json
import logging
import re

from .models import Resume
from .utils.parser import SimpleResumeParser

logger = logging.getLogger(__name__)

# Regex patterns for UG and PG degrees

UG_DEGREES = UG_DEGREES = [
    "B.E", "B.Tech", "BCA", "B.Sc", "B.A", "B.Com",
    "Bachelor of Engineering", 
    "Bachelor of Technology",
    "Bachelor of Computer Applications",
    "Bachelor of Science",
    "Bachelor of Science in Information Technology",
    "Bachelor of Arts",
    "Bachelor of Commerce",
    "B. Tech", "B Tech", "B.E.", "B Tech/BE", 
    "B.Tech -", "B.E -", "B.Tech (", "B.E (", 
    "Bachelors in Technology", "Bachelors of Engineering"
]


PG_DEGREES = PG_DEGREES = [
    "M.E", "M.Tech", "MCA", "M.Sc", "MBA", "PGDM", "M.A", "M.Com", "Ph.D",
    "Master of Engineering", "Master of Technology", 
    "Master of Computer Applications", "Master of Science",
    "Master of Arts", "Master of Commerce",
    "M.E.", "M.Tech.", "M Tech", "M.E -", "M.Tech -", "M.Tech (", "M.E ("
]


# Stream synonyms mapping for normalization
STREAM_SYNONYMS = {
    # --- Computer Science ---
    "cse": "computer science",
    "cs": "computer science",
    "comp sci": "computer science",
    "computer sc": "computer science",
    "computer eng": "computer science",
    "computer engineering": "computer science",
    "b.tech - computer engineering": "computer science",
    "b.tech (computer engineering)": "computer science",

    # --- Information Technology ---
    "it": "information technology",
    "info tech": "information technology",
    "information tech": "information technology",
    "information technology": "information technology",

    # --- Electronics and Communication ---
    "ece": "electronics and communication",
    "electronics and communication engineering": "electronics and communication",
    "electronics communication": "electronics and communication",
    "ec": "electronics and communication",
    "e&c": "electronics and communication",
    "electronics and telecom": "electronics and communication",
    "b.e - electronics and telecom": "electronics and communication",
    "b.e in electronics and telecom": "electronics and communication",

    # --- AI and ML (including AI + DS formats) ---
    "ai ml": "ai and ml",
    "ai & ml": "ai and ml",
    "ai and machine learning": "ai and ml",
    "artificial intelligence": "ai and ml",
    "artificial intelligence and machine learning": "ai and ml",
    "ai-ml": "ai and ml",
    "ai ml dl": "ai and ml",
    "ai and dl": "ai and ml",
    "ai ml ds": "ai and ml",
    "ai and data science": "ai and ml",
    "artificial intelligence and data science": "ai and ml",
    "ai ds": "ai and ml",
    "ai, ds": "ai and ml",
    "ai, ml, ds": "ai and ml",
    "ai + data science": "ai and ml",
    "artificial intelligence & data science": "ai and ml",
    "artificial intelligence with data science": "ai and ml",

    # --- Data Science + Data Engineering (grouped as "data science") ---
    "ds": "data science",
    "data science": "data science",
    "data sciences": "data science",
    "data science engineering": "data science",
    "data engineering": "data science",
    "data science and engineering": "data science",
    "data analytics": "data science",
    "data analysis": "data science",
    "data science with ai": "data science",
    "data science ai": "data science",
    "business analytics": "data science",
    "analytics": "data science",

    # --- Cyber Security ---
    "cybersecurity": "cyber security",
    "cyber sec": "cyber security",
    "cyber security": "cyber security",
    "information security": "cyber security",
    "info sec": "cyber security"
}



def normalize_degree_stream_text(text):
    """
    Normalize degree/stream text by removing punctuation, lowercasing, 
    and applying synonym mapping.
    """
    if not text:
        return ""
    
    # Convert to lowercase
    text = text.lower()
    
    # Remove common punctuation and special characters
    text = re.sub(r'[().,\-_/]', ' ', text)
    
    # Remove extra whitespaces
    text = ' '.join(text.split())
    
    # Apply synonym mapping
    for synonym, standard in STREAM_SYNONYMS.items():
        # Use word boundaries to avoid partial replacements
        text = re.sub(r'\b' + re.escape(synonym) + r'\b', standard, text)
    
    return text


def check_degree_stream_match(db_value, degree_filter, stream_filter):
    """
    Check if both degree and stream filters match the database value.
    Returns True if both are found in the normalized text.
    """
    if not db_value:
        return False
    
    # Normalize all values
    normalized_db = normalize_degree_stream_text(db_value)
    normalized_degree = normalize_degree_stream_text(degree_filter) if degree_filter else ""
    normalized_stream = normalize_degree_stream_text(stream_filter) if stream_filter else ""
    
    # Check if degree is present (if specified)
    degree_match = True
    if normalized_degree:
        degree_match = normalized_degree in normalized_db
    
    # Check if stream is present (if specified)
    stream_match = True
    if normalized_stream:
        stream_match = normalized_stream in normalized_db
    
    # Both must match if specified
    return degree_match and stream_match


def extract_ug_pg_degrees(text):
    ug_result = None
    pg_result = None

    for degree in UG_DEGREES:
        pattern = rf"{degree}\s*(?:in|of)?\s*(?:\((.*?)\)|([A-Za-z &]+))?"
        matches = re.findall(pattern, text, re.IGNORECASE)
        for match in matches:
            stream = match[0] or match[1]
            if stream:
                stream = stream.strip()
                ug_result = f"{degree} - {stream}"
            else:
                ug_result = degree
            break

    for degree in PG_DEGREES:
        pattern = rf"{degree}\s*(?:in|of)?\s*(?:\((.*?)\)|([A-Za-z &]+))?"
        matches = re.findall(pattern, text, re.IGNORECASE)
        for match in matches:
            stream = match[0] or match[1]
            if stream:
                stream = stream.strip()
                pg_result = f"{degree} - {stream}"
            else:
                pg_result = degree
            break

    return ug_result, pg_result



def convert_experience_for_filtering(experience_str):
    """
    Convert string experience values to floats for filtering comparisons.
    
    Examples:
    - '4+' -> 4.5 (treat as slightly more than 4)
    - '4.5' -> 4.5
    - '5' -> 5.0
    - '0.7' -> 0.7
    - '4 yrs' -> 4.0
    - '3 years' -> 3.0
    - None or invalid -> None
    """
    if not experience_str:
        return None
    
    try:
        exp_str = str(experience_str).strip()
        
        # FIX 3: Strip non-numeric characters like "years", "yrs"
        exp_str = re.sub(r'[^\d.+]', '', exp_str)
        
        # Handle "X+" format - treat as X + 0.5
        if '+' in exp_str:
            match = re.search(r'(\d+(?:\.\d+)?)\+', exp_str)
            if match:
                base_value = float(match.group(1))
                return base_value + 0.5  # Treat "4+" as 4.5
            return None
        
        # Handle regular numbers (e.g., "4.5", "5", "0.7")
        return float(exp_str)
        
    except (ValueError, TypeError):
        return None


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
    if request.method == 'POST':
        files = request.FILES.getlist('resumes')

        if not files:
            return JsonResponse({'error': 'No files uploaded'}, status=400)

        results = []
        parser = SimpleResumeParser()

        for uploaded_file in files:
            try:
                file_content = uploaded_file.read()

                # ✅ Step 1: Check for duplicate content in entire DB
                content_hash = Resume.calculate_content_hash(file_content)
                existing_resume = Resume.objects.filter(content_hash=content_hash).first()

                if existing_resume:
                    results.append({
                        'filename': uploaded_file.name,
                        'success': False,
                        'message': 'Duplicate resume detected. Already uploaded.'
                    })
                    continue  # Skip this file

                # Step 2: Parse resume if not duplicate
                result = parser.process_resume(
                    file_obj=file_content,
                    filename=uploaded_file.name
                )

                if result['success'] and result['data']:
                    resume_data = result['data']
                    
                    # 🔍 Extract degree + stream from education text as FALLBACK
                    education_list = resume_data.get('education', [])
                    education_text = " ".join(education_list) if isinstance(education_list, list) else str(education_list)
                    ug_degree, pg_degree = extract_ug_pg_degrees(education_text)

                    # 🔁 CONDITIONAL FALLBACK: Only use regex results if parser didn't provide values
                    if not resume_data.get('ug_degree'):
                        resume_data['ug_degree'] = ug_degree 
                    if not resume_data.get('pg_degree'):
                        resume_data['pg_degree'] = pg_degree 

                    Resume.objects.create(
                        filename=uploaded_file.name,
                        name=resume_data.get('name'),
                        email=resume_data.get('email'),
                        phone=resume_data.get('phone'),
                        linkedin=resume_data.get('linkedin'),
                        github=resume_data.get('github'),
                        skills=json.dumps(resume_data.get('skills', [])),
                        ug_degree=resume_data.get('ug_degree'),
                        ug_college=resume_data.get('ug_college'),
                        ug_year=resume_data.get('ug_year'),
                        pg_degree=resume_data.get('pg_degree'),
                        pg_college=resume_data.get('pg_college'),
                        pg_year=resume_data.get('pg_year'),
                        total_experience_years=resume_data.get('total_experience_years'),
                        work_experience=json.dumps(resume_data.get('work_experience', [])),
                        raw_resume=file_content,
                        mime_type=uploaded_file.content_type or 'application/octet-stream',
                        uploaded_by=request.user,
                        content_hash=content_hash  # ✅ Store the hash
                    )

                    results.append({
                        'filename': uploaded_file.name,
                        'success': True,
                        'message': 'Parsed and stored successfully'
                    })
                else:
                    results.append({
                        'filename': uploaded_file.name,
                        'success': False,
                        'message': result.get('error', 'Failed to parse resume')
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
def get_all_resumes(request):
    """Return all resumes for auto-refresh when filters are cleared"""
    if request.user.is_admin:
        resumes = Resume.objects.all().order_by('-created_at')
    else:
        resumes = Resume.objects.filter(uploaded_by=request.user).order_by('-created_at')

    data = []
    for resume in resumes:
        data.append({
            'id': resume.id,
            'name': resume.name,
            'email': resume.email,
            'phone': resume.phone,
            'skills': resume.get_skills_list(),
            'total_experience_years': resume.total_experience_years if resume.total_experience_years else "N/A",
            'ug_degree': resume.ug_degree if resume.ug_degree else "N/A",
            'pg_degree': resume.pg_degree if resume.pg_degree else "N/A",
            'uploaded_by_email': resume.uploaded_by.email if resume.uploaded_by else "N/A"
        })

    return JsonResponse({'resumes': data})



@login_required
def filter_resumes(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    try:
        data = json.loads(request.body)
        mandatory_skills = data.get('mandatory_skills', [])
        optional_skills = data.get('optional_skills', [])
        min_experience = data.get('min_experience')
        max_experience = data.get('max_experience')
        
        # NEW: Education filter parameters
        ug_degree_filter = data.get('ug_degree', '')
        ug_stream_filter = data.get('ug_stream', '')
        pg_degree_filter = data.get('pg_degree', '')
        pg_stream_filter = data.get('pg_stream', '')

        if request.user.is_admin:
            resumes = Resume.objects.all()
        else:
            resumes = Resume.objects.filter(uploaded_by=request.user)

        # FIX 2: Changed skill normalization to only strip and lowercase
        def normalize_skill(s):
            return s.strip().lower()

        filtered_resumes = []

        for resume in resumes:
            resume_skills = resume.get_skills_list()
            resume_skills_normalized = [normalize_skill(s) for s in resume_skills]

            # --- Check experience filter ---
            passes_experience_filter = True
            resume_experience_str = resume.total_experience_years
            resume_experience = convert_experience_for_filtering(resume_experience_str)
            
            # Apply experience filter if specified
            if min_experience is not None or max_experience is not None:
                # If experience filter is applied but resume has no experience data, it fails
                if resume_experience is None:
                    passes_experience_filter = False
                else:
                    # Check minimum experience
                    if min_experience is not None and resume_experience < min_experience:
                        passes_experience_filter = False
                    
                    # Check maximum experience
                    if max_experience is not None and resume_experience > max_experience:
                        passes_experience_filter = False

            # --- Check skill filters ---
            passes_skill_filter = True
            
            # Only apply skill filter if skills are specified
            if mandatory_skills or optional_skills:
                # FIX 1: Fixed optional skills filtering logic
                
                # Check mandatory skills (ALL must be present)
                if mandatory_skills:
                    all_mandatory_present = all(
                       any(normalize_skill(skill) in rs for rs in resume_skills_normalized)
                       for skill in mandatory_skills
                    )

                    if not all_mandatory_present:
                        passes_skill_filter = False
                
                # Check optional skills ONLY if there are no mandatory skills 
                # OR if mandatory skills are present but we want to ensure at least one optional matches
                if optional_skills and passes_skill_filter:
                    # If we only have optional skills (no mandatory), require at least one match
                    if not mandatory_skills:
                        any_optional_present = any(
                            any(normalize_skill(skill) in rs for rs in resume_skills_normalized)
                            for skill in optional_skills
                        )

                        if not any_optional_present:
                            passes_skill_filter = False
                    # If we have both mandatory and optional, treat optional as bonus (don't block)
                    # So we don't check optional skills when mandatory skills are present

            # --- NEW: Check education filters ---
            passes_education_filter = True
            
            # Check UG degree and stream filter using normalized matching
            if (ug_degree_filter or ug_stream_filter) and passes_education_filter:
                if not resume.ug_degree:
                    passes_education_filter = False
                else:
                    passes_education_filter = check_degree_stream_match(
                        resume.ug_degree, 
                        ug_degree_filter, 
                        ug_stream_filter
                    )
            
            # Check PG degree and stream filter using normalized matching
            if (pg_degree_filter or pg_stream_filter) and passes_education_filter:
                if not resume.pg_degree:
                    passes_education_filter = False
                else:
                    passes_education_filter = check_degree_stream_match(
                        resume.pg_degree,
                        pg_degree_filter,
                        pg_stream_filter
                    )

            # Resume must pass ALL filters (if applied)
            if passes_experience_filter and passes_skill_filter and passes_education_filter:
                # Resume passes all applied filters - UPDATED to include degree information
                filtered_resumes.append({
                    'id': resume.id,
                    'name': resume.name,
                    'email': resume.email,
                    'phone': resume.phone,
                    'skills': resume_skills,
                    'total_experience_years': resume.total_experience_years if resume.total_experience_years is not None else "N/A",
                    'ug_degree': resume.ug_degree if resume.ug_degree else "N/A",
                    'pg_degree': resume.pg_degree if resume.pg_degree else "N/A",
                    'uploaded_by_email': resume.uploaded_by.email if resume.uploaded_by else "N/A"
                })

        # Sort latest first
        filtered_resumes.sort(key=lambda r: r['id'], reverse=True)

        return JsonResponse({'resumes': filtered_resumes})

    except Exception as e:
        logger.error(f"Error filtering resumes: {e}")
        return JsonResponse({'error': str(e)}, status=500)