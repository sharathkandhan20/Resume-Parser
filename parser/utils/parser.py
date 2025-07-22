"""
Simple Resume Parser with Gemini API integration
"""

import os
import json
import logging
from pathlib import Path
from typing import Dict, Optional, List, Any
import io

# Document processing libraries
import pdfplumber
from docx import Document
import pytesseract
from PIL import Image
import pandas as pd

# API
import google.generativeai as genai
from dotenv import load_dotenv

# Configure logging
logger = logging.getLogger(__name__)


class TextExtractor:
    """Handles text extraction from various file formats"""
    
    _ocr_available = None
    
    @classmethod
    def check_ocr_availability(cls):
        """Check if OCR is available (cached)"""
        if cls._ocr_available is None:
            try:
                pytesseract.get_tesseract_version()
                cls._ocr_available = True
            except:
                cls._ocr_available = False
        return cls._ocr_available
    
    @staticmethod
    def extract_text_from_pdf_bytes(file_bytes) -> str:
        """Extract text from PDF bytes in memory"""
        text = ""
        
        try:
            with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
                for page_num, page in enumerate(pdf.pages):
                    page_text = page.extract_text() or ""
                    text += f"\n--- Page {page_num + 1} ---\n{page_text}"
        except Exception as e:
            logger.error(f"PDF extraction error: {e}")
        
        return text
    
    @staticmethod
    def extract_text_from_docx_bytes(file_bytes) -> str:
        """Extract text from DOCX bytes in memory"""
        text = ""
        try:
            doc = Document(io.BytesIO(file_bytes))
            
            for para in doc.paragraphs:
                text += para.text + "\n"
            
            if doc.tables:
                text += "\n[TABLES]\n"
                for table in doc.tables:
                    table_data = []
                    for row in table.rows:
                        row_data = [cell.text.strip() for cell in row.cells]
                        table_data.append(row_data)
                    
                    if table_data:
                        df = pd.DataFrame(table_data[1:], columns=table_data[0] if table_data else None)
                        text += df.to_string(index=False) + "\n"
        except Exception as e:
            logger.error(f"DOCX extraction error: {e}")
        
        return text
    
    @staticmethod
    def extract_text_from_image_bytes(file_bytes) -> str:
        """Extract text from image bytes using OCR"""
        if not TextExtractor.check_ocr_availability():
            logger.warning("OCR not available")
            return ""
            
        try:
            image = Image.open(io.BytesIO(file_bytes))
            return pytesseract.image_to_string(image, lang='eng')
        except Exception as e:
            logger.error(f"Image OCR error: {e}")
            return ""
    
    @staticmethod
    def extract_text_from_txt_bytes(file_bytes) -> str:
        """Extract text from TXT bytes"""
        try:
            return file_bytes.decode('utf-8', errors='ignore')
        except Exception as e:
            logger.error(f"TXT read error: {e}")
            return ""


class SimpleResumeParser:
    """Simple resume parser using Gemini API"""
    
    def __init__(self):
        load_dotenv()
        self.api_key = self._load_api_key()
        
        if self.api_key:
            genai.configure(api_key=self.api_key)
        else:
            logger.warning("No API key found. Parser will extract text only.")
        
        self.parsing_prompt = """Extract the following information from this resume and return ONLY valid JSON:

{
  "name": "full name",
  "email": "email address",
  "phone": "phone number",
  "linkedin": "LinkedIn URL",
  "github": "GitHub URL",
  "skills": ["skill1", "skill2", ...],
  "ug_education": {
    "degree": "Bachelor's degree name",
    "college": "college/university name",
    "year": graduation year as number
  },
  "pg_education": {
    "degree": "Master's/PhD degree name",
    "college": "college/university name",
    "year": graduation year as number
  },
  "total_experience_years": total years as number,
  "work_experience": [
    {
      "title": "job title",
      "company": "company name",
      "start_year": start year as number,
      "end_year": end year as number or null if current
    }
  ]
}

Resume text:
{text}

Return ONLY the JSON, no explanations."""
    
    def _load_api_key(self) -> Optional[str]:
        """Load API key from environment"""
        # Try numbered key first
        key = os.getenv('GEMINI_API_KEY_1')
        if key:
            return key
        
        # Try single key format
        key = os.getenv('GEMINI_API_KEY')
        return key
    
    def extract_text(self, file_obj, filename: str) -> str:
        """Extract text from file bytes"""
        ext = Path(filename).suffix.lower()
        
        if ext == '.pdf':
            return TextExtractor.extract_text_from_pdf_bytes(file_obj)
        elif ext == '.docx':
            return TextExtractor.extract_text_from_docx_bytes(file_obj)
        elif ext == '.txt':
            return TextExtractor.extract_text_from_txt_bytes(file_obj)
        elif ext in {'.png', '.jpg', '.jpeg', '.tiff', '.bmp'}:
            return TextExtractor.extract_text_from_image_bytes(file_obj)
        else:
            raise ValueError(f"Unsupported file type: {ext}")
    
    def parse_with_gemini(self, text_content: str) -> Optional[Dict]:
        """Parse resume text with Gemini API"""
        if not self.api_key:
            return None
        
        try:
            model = genai.GenerativeModel("gemini-1.5-flash")
            
            prompt = self.parsing_prompt.replace("{text}", text_content)
            response = model.generate_content(prompt)
            
            return self._parse_json_response(response.text)
            
        except Exception as e:
            logger.error(f"Gemini API error: {e}")
            return None
    
    def _parse_json_response(self, json_text: str) -> Dict[str, Any]:
        """Parse JSON response from Gemini"""
        try:
            # Clean JSON response
            if "```json" in json_text:
                json_text = json_text.split("```json")[1].split("```")[0]
            elif "```" in json_text:
                json_text = json_text.split("```")[1].split("```")[0]
            
            parsed = json.loads(json_text.strip())
            
            # Normalize data
            result = {
                'name': parsed.get('name'),
                'email': parsed.get('email'),
                'phone': parsed.get('phone'),
                'linkedin': parsed.get('linkedin'),
                'github': parsed.get('github'),
                'skills': parsed.get('skills', []),
                'total_experience_years': parsed.get('total_experience_years')
            }
            
            # Handle education
            ug_edu = parsed.get('ug_education', {})
            if ug_edu and isinstance(ug_edu, dict):
                result['ug_degree'] = ug_edu.get('degree')
                result['ug_college'] = ug_edu.get('college')
                result['ug_year'] = ug_edu.get('year')
            
            pg_edu = parsed.get('pg_education', {})
            if pg_edu and isinstance(pg_edu, dict):
                result['pg_degree'] = pg_edu.get('degree')
                result['pg_college'] = pg_edu.get('college')
                result['pg_year'] = pg_edu.get('year')
            
            # Handle work experience
            result['work_experience'] = parsed.get('work_experience', [])
            
            return result
            
        except Exception as e:
            logger.error(f"JSON parsing error: {e}")
            return None
    
    def process_resume(self, file_obj, filename: str) -> Dict:
        """Process a single resume"""
        result = {
            'filename': filename,
            'success': False,
            'data': None,
            'error': None
        }
        
        try:
            # Extract text
            text_content = self.extract_text(file_obj, filename)
            
            if not text_content or len(text_content.strip()) < 10:
                raise ValueError("No meaningful text extracted")
            
            # Parse with Gemini if available
            if self.api_key:
                parsed_data = self.parse_with_gemini(text_content)
                
                if parsed_data:
                    result['data'] = parsed_data
                    result['success'] = True
                else:
                    result['error'] = "Failed to parse resume"
            else:
                # If no API key, just return success with empty data
                result['data'] = {
                    'name': None,
                    'email': None,
                    'phone': None,
                    'linkedin': None,
                    'github': None,
                    'skills': [],
                    'ug_degree': None,
                    'ug_college': None,
                    'ug_year': None,
                    'pg_degree': None,
                    'pg_college': None,
                    'pg_year': None,
                    'total_experience_years': None,
                    'work_experience': []
                }
                result['success'] = True
                result['error'] = "No API key - text extracted but not parsed"
                
        except Exception as e:
            result['error'] = str(e)
            logger.error(f"Error processing {filename}: {e}")
        
        return result