"""
Optimized Bank Statement Parser
Extracts structured financial metrics locally - NO raw text to LLM
"""
import re
import pdfplumber
from typing import Dict, List
from datetime import datetime, timedelta


def parse_bank_statement(pdf_path: str) -> Dict:
    """
    Parse bank statement PDF and extract structured financial data.
    Returns only key metrics - no raw text.
    """
    try:
        with pdfplumber.open(pdf_path) as pdf:
            text = ""
            tables_data = []
            
            for page in pdf.pages:
                page_text = page.extract_text() or ""
                text += page_text + "\n"
                
                # Try to extract tables (more accurate for transactions)
                tables = page.extract_tables()
                if tables:
                    tables_data.extend(tables)
        
        # Extract account balances
        balance_patterns = [
            r'(?:balance|bal|available|closing)[\s:]*[₹Rs]?\s*(\d+(?:,\d+)*(?:\.\d{2})?)',
            r'[₹Rs]?\s*(\d+(?:,\d+)*(?:\.\d{2})?)\s*(?:balance|bal|available)',
            r'opening\s*balance[\s:]*[₹Rs]?\s*(\d+(?:,\d+)*(?:\.\d{2})?)',
            r'closing\s*balance[\s:]*[₹Rs]?\s*(\d+(?:,\d+)*(?:\.\d{2})?)',
        ]
        balances = []
        for pattern in balance_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for match in matches:
                amount_str = match.replace(',', '')
                try:
                    balance = float(amount_str)
                    if balance > 0:  # Only positive balances
                        balances.append(balance)
                except:
                    pass
        
        avg_balance = sum(balances) / len(balances) if balances else 0
        min_balance = min(balances) if balances else 0
        max_balance = max(balances) if balances else 0
        
        # Extract credits (income, salary, deposits)
        credit_patterns = [
            r'credit[\s:]*[₹Rs]?\s*(\d+(?:,\d+)*(?:\.\d{2})?)',
            r'(?:salary|deposit|income|transfer\s*in)[\s:]*[₹Rs]?\s*(\d+(?:,\d+)*(?:\.\d{2})?)',
            r'[₹Rs]?\s*(\d+(?:,\d+)*(?:\.\d{2})?)\s*(?:credit|cr)',
        ]
        credits = []
        salary_credits = []
        for pattern in credit_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for match in matches:
                amount_str = match.replace(',', '')
                try:
                    amount = float(amount_str)
                    credits.append(amount)
                    # Check if it's salary (typically larger, regular amounts)
                    if 'salary' in pattern.lower() or amount > 10000:
                        salary_credits.append(amount)
                except:
                    pass
        
        total_credits = sum(credits)
        total_salary_credits = sum(salary_credits)
        avg_monthly_income = total_salary_credits / max(len(salary_credits), 1) if salary_credits else None
        
        # Extract debits (expenses, payments, withdrawals)
        debit_patterns = [
            r'debit[\s:]*[₹Rs]?\s*(\d+(?:,\d+)*(?:\.\d{2})?)',
            r'(?:payment|withdrawal|transfer\s*out|expense)[\s:]*[₹Rs]?\s*(\d+(?:,\d+)*(?:\.\d{2})?)',
            r'[₹Rs]?\s*(\d+(?:,\d+)*(?:\.\d{2})?)\s*(?:debit|dr)',
        ]
        debits = []
        emi_payments = []
        late_fees = []
        
        for pattern in debit_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for match in matches:
                amount_str = match.replace(',', '')
                try:
                    amount = float(amount_str)
                    debits.append(amount)
                    
                    # Check for EMI payments (regular, similar amounts)
                    if 'emi' in text.lower() or 'installment' in text.lower():
                        emi_payments.append(amount)
                    
                    # Check for late fees/charges
                    if 'late' in text.lower() or 'fee' in text.lower() or 'charge' in text.lower():
                        late_fees.append(amount)
                except:
                    pass
        
        total_debits = sum(debits)
        total_emi_payments = sum(emi_payments)
        total_late_fees = sum(late_fees)
        
        # Calculate savings estimate
        savings_estimate = total_credits - total_debits
        
        # Extract transaction counts
        transaction_keywords = ['transaction', 'debit', 'credit', 'payment', 'transfer']
        transaction_count = sum(1 for keyword in transaction_keywords if keyword.lower() in text.lower())
        
        # Check for negative balance/overdraft
        negative_balance = any(word in text.lower() for word in ['overdraft', 'negative', 'insufficient', 'od'])
        
        # Extract largest expense
        largest_expense = max(debits) if debits else 0
        
        # Estimate digital vs cash spend (if UPI/online keywords present)
        digital_keywords = ['upi', 'online', 'neft', 'imps', 'rtgs', 'net banking']
        digital_spend = sum(amount for amount in debits if any(kw in text.lower() for kw in digital_keywords))
        cash_spend = total_debits - digital_spend
        
        # Build structured JSON - ONLY key metrics
        return {
            "total_income": float(total_credits),
            "salary_credits": float(total_salary_credits),
            "avg_monthly_income": float(avg_monthly_income) if avg_monthly_income else None,
            "total_expenses": float(total_debits),
            "emi_payments": float(total_emi_payments),
            "late_fees": float(total_late_fees),
            "largest_expense": float(largest_expense),
            "savings_estimate": float(savings_estimate),
            "digital_spend": float(digital_spend),
            "cash_spend": float(cash_spend),
            "avg_balance": float(avg_balance),
            "min_balance": float(min_balance),
            "max_balance": float(max_balance),
            "transaction_count": transaction_count,
            "negative_balance": negative_balance
        }
    
    except Exception as e:
        return {
            "error": str(e),
            "total_income": 0,
            "salary_credits": 0,
            "avg_monthly_income": None,
            "total_expenses": 0,
            "emi_payments": 0,
            "late_fees": 0,
            "largest_expense": 0,
            "savings_estimate": 0,
            "digital_spend": 0,
            "cash_spend": 0,
            "avg_balance": 0,
            "min_balance": 0,
            "max_balance": 0,
            "transaction_count": 0,
            "negative_balance": False
        }

