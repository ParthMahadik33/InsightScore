"""
Optimized UPI Statement Parser (CSV and PDF)
Extracts structured transaction data locally - NO raw text to LLM
"""
import re
import pandas as pd
import pdfplumber
from typing import Dict, List
from collections import Counter


def parse_upi_csv(csv_path: str) -> Dict:
    """
    Parse UPI transaction CSV and extract structured data.
    Returns only key metrics - no raw text.
    """
    try:
        df = pd.read_csv(csv_path)
        
        # Find relevant columns (flexible column matching)
        amount_cols = [col for col in df.columns if any(kw in col.lower() for kw in ['amount', 'rupee', 'rs', 'value'])]
        date_cols = [col for col in df.columns if any(kw in col.lower() for kw in ['date', 'time', 'timestamp'])]
        desc_cols = [col for col in df.columns if any(kw in col.lower() for kw in ['desc', 'note', 'remark', 'narration', 'merchant', 'to'])]
        type_cols = [col for col in df.columns if any(kw in col.lower() for kw in ['type', 'status', 'mode'])]
        
        amount_col = amount_cols[0] if amount_cols else df.columns[1]
        date_col = date_cols[0] if date_cols else df.columns[0]
        desc_col = desc_cols[0] if desc_cols else (df.columns[2] if len(df.columns) > 2 else df.columns[0])
        
        # Clean amount column
        df[amount_col] = df[amount_col].astype(str).str.replace(r'[^\d.]', '', regex=True)
        df[amount_col] = pd.to_numeric(df[amount_col], errors='coerce')
        df = df.dropna(subset=[amount_col])
        
        # Calculate totals
        total_transactions = len(df)
        total_spend = df[amount_col].abs().sum()
        avg_transaction = total_spend / total_transactions if total_transactions > 0 else 0
        
        # Categorize transactions
        bill_keywords = ['bill', 'electricity', 'water', 'gas', 'phone', 'internet', 'recharge', 'mobile']
        merchant_keywords = ['merchant', 'store', 'shop', 'restaurant', 'food', 'grocery']
        
        bill_payments = 0
        merchant_transactions = 0
        merchant_categories = []
        
        if desc_col in df.columns:
            for desc in df[desc_col].astype(str):
                desc_lower = desc.lower()
                if any(kw in desc_lower for kw in bill_keywords):
                    bill_payments += 1
                if any(kw in desc_lower for kw in merchant_keywords):
                    merchant_transactions += 1
                    # Extract merchant name (first few words)
                    words = desc.split()[:3]
                    merchant_categories.append(' '.join(words))
        
        # Calculate regularity (transactions per day)
        regularity = 0
        if date_col in df.columns:
            try:
                df[date_col] = pd.to_datetime(df[date_col], errors='coerce')
                df = df.dropna(subset=[date_col])
                if len(df) > 0:
                    date_range = (df[date_col].max() - df[date_col].min()).days
                    regularity = total_transactions / max(date_range, 1)
            except:
                regularity = total_transactions / 30  # Assume monthly
        
        # Count unique merchants
        unique_merchants = len(set(merchant_categories)) if merchant_categories else 0
        
        # Calculate digital behavior index (0-10)
        # Based on transaction frequency, bill payments, merchant diversity
        behavior_score = min(10, (regularity * 2) + (bill_payments / max(total_transactions, 1) * 5) + (unique_merchants / 10))
        
        return {
            "upi_transaction_count": int(total_transactions),
            "upi_total_spend": float(total_spend),
            "upi_bill_payments": int(bill_payments),
            "merchant_categories": list(set(merchant_categories))[:10],  # Top 10 unique
            "digital_behavior_index": float(behavior_score),
            "avg_transaction_amount": float(avg_transaction),
            "regularity_per_day": float(regularity),
            "unique_merchants": int(unique_merchants)
        }
    
    except Exception as e:
        return {
            "error": str(e),
            "upi_transaction_count": 0,
            "upi_total_spend": 0,
            "upi_bill_payments": 0,
            "merchant_categories": [],
            "digital_behavior_index": 0,
            "avg_transaction_amount": 0,
            "regularity_per_day": 0,
            "unique_merchants": 0
        }


def parse_upi_pdf(pdf_path: str) -> Dict:
    """
    Parse UPI transaction PDF and extract structured data.
    Returns only key metrics - no raw text.
    """
    try:
        with pdfplumber.open(pdf_path) as pdf:
            text = ""
            for page in pdf.pages:
                page_text = page.extract_text() or ""
                text += page_text + "\n"
        
        # Extract transaction amounts
        amount_patterns = [
            r'[₹Rs]?\s*(\d{1,3}(?:,\d{2,3})*(?:\.\d{2})?)',
            r'(\d+\.\d{2})',  # Decimal amounts
        ]
        amounts = []
        for pattern in amount_patterns:
            matches = re.findall(pattern, text)
            for match in matches:
                amount_str = match.replace(',', '')
                try:
                    amount = float(amount_str)
                    if 1 <= amount <= 1000000:  # Reasonable range
                        amounts.append(amount)
                except:
                    pass
        
        # Extract transaction IDs (UPI ref numbers)
        txn_id_pattern = r'(?:ref|txn|upi)[\s:]*([A-Z0-9]{8,})'
        txn_ids = re.findall(txn_id_pattern, text, re.IGNORECASE)
        
        # Count transactions
        transaction_keywords = ['upi', 'payment', 'transfer', 'debit', 'credit', 'successful']
        transaction_count = sum(1 for keyword in transaction_keywords if keyword.lower() in text.lower())
        transaction_count = max(transaction_count, len(amounts), len(txn_ids))
        
        total_spend = sum(amounts) if amounts else 0
        avg_transaction = total_spend / len(amounts) if amounts else 0
        
        # Categorize bill payments
        bill_keywords = ['bill', 'electricity', 'water', 'gas', 'phone', 'recharge', 'mobile', 'internet']
        bill_payments = sum(1 for keyword in bill_keywords if keyword.lower() in text.lower())
        
        # Extract merchant names (look for common patterns)
        merchant_patterns = [
            r'to\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)',
            r'merchant[\s:]*([A-Z][a-z]+)',
            r'paid\s+to\s+([A-Z][a-z]+)',
        ]
        merchants = []
        for pattern in merchant_patterns:
            matches = re.findall(pattern, text)
            merchants.extend(matches)
        
        unique_merchants = len(set(merchants))
        merchant_categories = list(set(merchants))[:10]
        
        # Calculate regularity (assume monthly if dates not clear)
        regularity = transaction_count / 30
        
        # Calculate digital behavior index
        behavior_score = min(10, (regularity * 2) + (bill_payments / max(transaction_count, 1) * 5) + (unique_merchants / 10))
        
        return {
            "upi_transaction_count": int(transaction_count),
            "upi_total_spend": float(total_spend),
            "upi_bill_payments": int(bill_payments),
            "merchant_categories": merchant_categories,
            "digital_behavior_index": float(behavior_score),
            "avg_transaction_amount": float(avg_transaction),
            "regularity_per_day": float(regularity),
            "unique_merchants": int(unique_merchants)
        }
    
    except Exception as e:
        return {
            "error": str(e),
            "upi_transaction_count": 0,
            "upi_total_spend": 0,
            "upi_bill_payments": 0,
            "merchant_categories": [],
            "digital_behavior_index": 0,
            "avg_transaction_amount": 0,
            "regularity_per_day": 0,
            "unique_merchants": 0
        }

