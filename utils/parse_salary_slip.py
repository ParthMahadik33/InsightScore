"""
Optimized Salary Slip Parser
Extracts structured salary data locally - NO raw text to LLM
"""
import re
import pdfplumber
from typing import Dict, Optional
from datetime import datetime


def parse_salary_slip(pdf_path: str) -> Dict:
    """
    Parse salary slip PDF and extract structured salary data.
    Returns only key metrics - no raw text.
    """
    try:
        with pdfplumber.open(pdf_path) as pdf:
            text = ""
            for page in pdf.pages:
                page_text = page.extract_text() or ""
                text += page_text + "\n"
        
        # Extract gross salary
        gross_patterns = [
            r'(?:gross|gross\s*salary|total\s*earnings)[\s:]*[₹Rs]?\s*(\d+(?:,\d+)*(?:\.\d{2})?)',
            r'[₹Rs]?\s*(\d+(?:,\d+)*(?:\.\d{2})?)\s*(?:gross|gross\s*salary)',
            r'gross[\s:]*[₹Rs]?\s*(\d+(?:,\d+)*(?:\.\d{2})?)',
        ]
        gross_salary = None
        for pattern in gross_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                amount_str = match.group(1).replace(',', '')
                try:
                    gross = float(amount_str)
                    if 10000 <= gross <= 10000000:  # Reasonable range
                        gross_salary = gross
                        break
                except:
                    pass
        
        # Extract net salary
        net_patterns = [
            r'(?:net|net\s*pay|take\s*home|total\s*payable)[\s:]*[₹Rs]?\s*(\d+(?:,\d+)*(?:\.\d{2})?)',
            r'[₹Rs]?\s*(\d+(?:,\d+)*(?:\.\d{2})?)\s*(?:net|net\s*pay|take\s*home)',
        ]
        net_salary = None
        for pattern in net_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                amount_str = match.group(1).replace(',', '')
                try:
                    net = float(amount_str)
                    if 10000 <= net <= 10000000:
                        net_salary = net
                        break
                except:
                    pass
        
        # Extract total deductions
        deduction_patterns = [
            r'(?:total\s*deductions?|deduction)[\s:]*[₹Rs]?\s*(\d+(?:,\d+)*(?:\.\d{2})?)',
            r'[₹Rs]?\s*(\d+(?:,\d+)*(?:\.\d{2})?)\s*(?:deduction|deductions)',
        ]
        total_deductions = 0
        for pattern in deduction_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for match in matches:
                amount_str = match.replace(',', '')
                try:
                    deduction = float(amount_str)
                    total_deductions += deduction
                except:
                    pass
        
        # If net not found, calculate from gross - deductions
        if not net_salary and gross_salary:
            net_salary = gross_salary - total_deductions
        
        # Extract employee ID
        emp_id_patterns = [
            r'(?:employee\s*id|emp\s*id|id)[\s:]*([A-Z0-9]{4,})',
            r'([A-Z]{2,}\d{4,})',  # Common pattern: AB1234
        ]
        emp_id = None
        for pattern in emp_id_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                emp_id = match.group(1)
                break
        
        # Extract employee name (optional)
        name_patterns = [
            r'(?:employee\s*name|name)[\s:]*([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)',
            r'([A-Z][a-z]+\s+[A-Z][a-z]+)',  # First Last
        ]
        emp_name = None
        for pattern in name_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                emp_name = match.group(1)
                break
        
        # Check for regular employment (monthly pattern, date present)
        month_pattern = r'(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\w*\s*\d{4}'
        months_found = len(re.findall(month_pattern, text, re.IGNORECASE))
        is_regular = months_found > 0 and gross_salary is not None
        
        # Extract month/year of salary
        date_patterns = [
            r'(?:for\s*the\s*month\s*of|month)[\s:]*([A-Z][a-z]+)\s*(\d{4})',
            r'(\d{1,2})[/-](\d{4})',  # MM/YYYY
        ]
        salary_month = None
        salary_year = None
        for pattern in date_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                if len(match.groups()) == 2:
                    salary_month = match.group(1)
                    salary_year = match.group(2)
                break
        
        # Build structured JSON - ONLY key metrics
        return {
            "gross_salary": float(gross_salary) if gross_salary else None,
            "net_salary": float(net_salary) if net_salary else None,
            "total_deductions": float(total_deductions),
            "emp_id": emp_id,
            "emp_name": emp_name,
            "is_regular": is_regular,
            "salary_month": salary_month,
            "salary_year": salary_year
        }
    
    except Exception as e:
        return {
            "error": str(e),
            "gross_salary": None,
            "net_salary": None,
            "total_deductions": 0,
            "emp_id": None,
            "emp_name": None,
            "is_regular": False,
            "salary_month": None,
            "salary_year": None
        }

