"""
Optimized CIBIL/Credit Bureau Report Parser
Extracts only key metrics locally - NO raw text to LLM
"""
import re
import pdfplumber
from typing import Dict, Optional


def parse_cibil_report(pdf_path: str) -> Dict:
    """
    Parse CIBIL credit report PDF and extract structured data.
    Returns only key metrics - no raw text.
    """
    try:
        with pdfplumber.open(pdf_path) as pdf:
            text = ""
            for page in pdf.pages:
                page_text = page.extract_text() or ""
                text += page_text + "\n"
        
        # Extract CIBIL score (typically 300-900)
        score_patterns = [
            r'(?:CIBIL|credit\s*score|score)[\s:]*(\d{3})',
            r'(\d{3})\s*(?:CIBIL|credit\s*score)',
            r'score[\s:]*(\d{3})',
        ]
        cibil_score = None
        for pattern in score_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                score = int(match.group(1))
                if 300 <= score <= 900:
                    cibil_score = score
                    break
        
        # Extract open loans count
        loan_keywords = ['loan', 'credit card', 'mortgage', 'personal loan', 'home loan']
        loan_count = 0
        for keyword in loan_keywords:
            matches = re.findall(rf'\b{re.escape(keyword)}\b', text, re.IGNORECASE)
            loan_count += len(matches)
        
        # Extract late payments count
        late_patterns = [
            r'(?:late|delayed|overdue|missed).*?payment',
            r'payment.*?(?:late|delayed|overdue|missed)',
            r'DPD\s*(\d+)',  # Days Past Due
        ]
        late_payments = 0
        for pattern in late_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            late_payments += len(matches)
        
        # Extract credit utilization percentage
        util_patterns = [
            r'utilization[\s:]*(\d+(?:\.\d+)?)\s*%',
            r'(\d+(?:\.\d+)?)\s*%[\s]*utilization',
            r'credit\s*utilization[\s:]*(\d+(?:\.\d+)?)',
        ]
        credit_utilization = None
        for pattern in util_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                util = float(match.group(1))
                if 0 <= util <= 100:
                    credit_utilization = util
                    break
        
        # Extract credit history length (look for dates or years mentioned)
        history_patterns = [
            r'(\d+)\s*(?:years?|yrs?)\s*(?:of\s*)?(?:credit\s*)?history',
            r'history[\s:]*(\d+)\s*(?:years?|yrs?)',
            r'since\s*(\d{4})',  # Account opened since year
        ]
        credit_history_years = None
        for pattern in history_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                if 'since' in pattern:
                    # Calculate years from year mentioned
                    year = int(match.group(1))
                    from datetime import datetime
                    current_year = datetime.now().year
                    credit_history_years = current_year - year
                else:
                    credit_history_years = int(match.group(1))
                break
        
        # Extract total credit limit (if available)
        limit_patterns = [
            r'(?:total\s*)?credit\s*limit[\s:]*[₹Rs]?\s*(\d+(?:,\d+)*(?:\.\d+)?)',
            r'limit[\s:]*[₹Rs]?\s*(\d+(?:,\d+)*(?:\.\d+)?)',
        ]
        total_credit_limit = None
        for pattern in limit_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                amount_str = match.group(1).replace(',', '')
                total_credit_limit = float(amount_str)
                break
        
        # Build structured JSON - ONLY key metrics
        return {
            "cibil_score": cibil_score,
            "open_loans": loan_count,
            "late_payments": late_payments,
            "credit_utilization": credit_utilization,
            "credit_history_length_years": credit_history_years,
            "total_credit_limit": total_credit_limit
        }
    
    except Exception as e:
        return {
            "error": str(e),
            "cibil_score": None,
            "open_loans": 0,
            "late_payments": 0,
            "credit_utilization": None,
            "credit_history_length_years": None,
            "total_credit_limit": None
        }

