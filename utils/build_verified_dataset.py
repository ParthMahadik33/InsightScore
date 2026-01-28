"""
Structured JSON Builder for Verified Financial Dataset
Combines all parsed documents into a clean, minimal JSON for LLM
"""
from typing import Dict, Optional


def build_verified_dataset(
    bank_data: Optional[Dict] = None,
    upi_data: Optional[Dict] = None,
    credit_bureau_data: Optional[Dict] = None,
    salary_data: Optional[Dict] = None
) -> Dict:
    """
    Build a structured, minimal JSON dataset from all parsed documents.
    This is what we send to Gemini - small and efficient.
    
    Args:
        bank_data: Parsed bank statement data
        upi_data: Parsed UPI transaction data
        credit_bureau_data: Parsed CIBIL/credit report data
        salary_data: Parsed salary slip data
    
    Returns:
        Clean structured JSON ready for LLM processing
    """
    dataset = {}
    
    # Bank statement data (only key metrics)
    if bank_data and not bank_data.get("error"):
        dataset["bank"] = {
            "total_income": bank_data.get("total_income", 0),
            "salary_credits": bank_data.get("salary_credits", 0),
            "avg_monthly_income": bank_data.get("avg_monthly_income"),
            "total_expenses": bank_data.get("total_expenses", 0),
            "emi_payments": bank_data.get("emi_payments", 0),
            "late_fees": bank_data.get("late_fees", 0),
            "largest_expense": bank_data.get("largest_expense", 0),
            "savings_estimate": bank_data.get("savings_estimate", 0),
            "digital_spend": bank_data.get("digital_spend", 0),
            "cash_spend": bank_data.get("cash_spend", 0),
            "avg_balance": bank_data.get("avg_balance", 0),
            "negative_balance": bank_data.get("negative_balance", False)
        }
    else:
        dataset["bank"] = {}
    
    # UPI transaction data
    if upi_data and not upi_data.get("error"):
        dataset["upi"] = {
            "upi_transaction_count": upi_data.get("upi_transaction_count", 0),
            "upi_total_spend": upi_data.get("upi_total_spend", 0),
            "upi_bill_payments": upi_data.get("upi_bill_payments", 0),
            "merchant_categories": upi_data.get("merchant_categories", [])[:5],  # Top 5 only
            "digital_behavior_index": upi_data.get("digital_behavior_index", 0),
            "regularity_per_day": upi_data.get("regularity_per_day", 0)
        }
    else:
        dataset["upi"] = {}
    
    # Credit bureau data
    if credit_bureau_data and not credit_bureau_data.get("error"):
        dataset["credit_bureau"] = {
            "cibil_score": credit_bureau_data.get("cibil_score"),
            "open_loans": credit_bureau_data.get("open_loans", 0),
            "late_payments": credit_bureau_data.get("late_payments", 0),
            "credit_utilization": credit_bureau_data.get("credit_utilization"),
            "credit_history_length_years": credit_bureau_data.get("credit_history_length_years")
        }
    else:
        dataset["credit_bureau"] = {}
    
    # Salary slip data (optional)
    if salary_data and not salary_data.get("error"):
        dataset["salary"] = {
            "gross_salary": salary_data.get("gross_salary"),
            "net_salary": salary_data.get("net_salary"),
            "is_regular": salary_data.get("is_regular", False)
        }
    else:
        dataset["salary"] = {}
    
    return dataset


def validate_dataset(dataset: Dict) -> bool:
    """
    Validate that dataset has at least some useful data.
    Returns True if dataset is valid, False otherwise.
    """
    has_data = False
    
    # Check if any section has meaningful data
    if dataset.get("bank") and any(v for k, v in dataset["bank"].items() if k != "negative_balance" and v):
        has_data = True
    
    if dataset.get("upi") and any(v for v in dataset["upi"].values() if isinstance(v, (int, float)) and v > 0):
        has_data = True
    
    if dataset.get("credit_bureau") and dataset["credit_bureau"].get("cibil_score"):
        has_data = True
    
    if dataset.get("salary") and dataset["salary"].get("gross_salary"):
        has_data = True
    
    return has_data

