"""
Text cleaning utility to reduce tokens before LLM calls.
Removes headers, footers, T&Cs, repeated lines, and noise.
"""
import re


def clean_extracted_text(text):
    """
    Clean extracted text from PDFs to reduce token usage.
    Removes headers, footers, terms, repeated content, and noise.
    """
    if not text:
        return ""
    
    lines = text.split('\n')
    cleaned_lines = []
    
    for line in lines:
        # Skip empty lines
        if not line.strip():
            continue
        
        # Skip common headers/footers
        if is_header_footer(line):
            continue
        
        # Skip terms & conditions
        if is_terms_conditions(line):
            continue
        
        # Skip repeated lines (if same line appears multiple times)
        if line.strip() in [l.strip() for l in cleaned_lines[-5:]]:
            continue
        
        # Keep only lines with useful data (numbers, dates, transaction info)
        if has_useful_data(line):
            cleaned_lines.append(line.strip())
    
    # Join and remove excessive whitespace
    cleaned = '\n'.join(cleaned_lines)
    cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)  # Max 2 consecutive newlines
    cleaned = re.sub(r' {2,}', ' ', cleaned)  # Max 1 space
    
    return cleaned.strip()


def is_header_footer(line):
    """Check if line is a header or footer"""
    line_lower = line.lower().strip()
    
    # Common header/footer patterns
    patterns = [
        r'^page\s+\d+',
        r'^\d+\s+of\s+\d+',
        r'^confidential',
        r'^internal\s+use',
        r'^statement\s+period',
        r'^generated\s+on',
        r'^printed\s+on',
        r'^©\s*',
        r'^all\s+rights\s+reserved',
        r'^this\s+is\s+a\s+computer\s+generated',
    ]
    
    for pattern in patterns:
        if re.match(pattern, line_lower):
            return True
    
    # Very short lines that are likely headers/footers
    if len(line.strip()) < 5 and not any(char.isdigit() for char in line):
        return True
    
    return False


def is_terms_conditions(line):
    """Check if line contains terms & conditions"""
    line_lower = line.lower()
    
    terms_keywords = [
        'terms and conditions',
        'terms & conditions',
        'disclaimer',
        'liability',
        'warranty',
        'copyright',
        'trademark',
        'by using this',
        'you agree',
        'please note',
    ]
    
    return any(keyword in line_lower for keyword in terms_keywords)


def has_useful_data(line):
    """
    Check if line contains useful financial/transaction data.
    Returns True if line has numbers, dates, or transaction keywords.
    """
    # Has numbers (amounts, dates, IDs)
    if re.search(r'\d', line):
        return True
    
    # Has transaction keywords
    transaction_keywords = [
        'debit', 'credit', 'balance', 'transaction', 'payment',
        'transfer', 'upi', 'emi', 'loan', 'salary', 'deposit',
        'withdrawal', 'fee', 'charge', 'interest'
    ]
    
    line_lower = line.lower()
    return any(keyword in line_lower for keyword in transaction_keywords)


def extract_numbers_only(text):
    """Extract only numeric values and dates from text"""
    # Extract amounts (₹, Rs, or plain numbers with decimals)
    amounts = re.findall(r'[₹Rs]?\s*(\d{1,3}(?:,\d{2,3})*(?:\.\d{2})?)', text, re.IGNORECASE)
    
    # Extract dates
    dates = re.findall(r'\d{1,2}[/-]\d{1,2}[/-]\d{2,4}', text)
    
    # Extract transaction IDs
    txn_ids = re.findall(r'[A-Z0-9]{8,}', text)
    
    return {
        'amounts': amounts,
        'dates': dates,
        'transaction_ids': txn_ids
    }

