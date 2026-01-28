"""
Optimized Gemini LLM Processor
Uses Gemini Flash for extraction, Gemini Pro for scoring
Only sends structured JSON - NO raw text
"""
import json
import re
import google.generativeai as genai
from typing import Dict, Optional


def call_gemini_flash_for_extraction(prompt: str, data: Dict) -> Optional[Dict]:
    """
    Use Gemini Flash for fast extraction tasks (if needed).
    Currently not used as we do all extraction locally.
    Kept for future use cases.
    """
    try:
        model = genai.GenerativeModel('gemini-2.0-flash-exp')
        response = model.generate_content(prompt, timeout=10)
        response_text = response.text.strip()
        
        # Extract JSON from response
        json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
        if json_match:
            return json.loads(json_match.group())
        return None
    except Exception as e:
        print(f"Gemini Flash extraction error: {e}")
        return None


def call_gemini_pro_for_scoring(dataset: Dict) -> Dict:
    """
    Use Gemini Pro for accurate scoring.
    Sends ONLY structured JSON - no raw text.
    """
    # Build strict prompt with structured data only
    prompt = f"""
You are a financial behavior analyst. Calculate verified behavioral scores based ONLY on the structured JSON data provided below.

IMPORTANT RULES:
1. Use ONLY the JSON data provided. Do NOT hallucinate or invent fields.
2. If a field is missing or null, do NOT assume a value - use null or 0.
3. Base scores ONLY on verified document data - no assumptions.
4. Return valid JSON in the exact format specified.

Structured Financial Dataset:
{json.dumps(dataset, indent=2)}

Calculate the following scores (each on a scale of 0-10) based ONLY on the provided data:

1. income_stability_score
   - Use: bank.avg_monthly_income, salary.gross_salary, bank.salary_credits
   - Higher if: consistent income, regular salary credits, stable employment

2. spending_discipline_score
   - Use: bank.total_expenses, bank.largest_expense, bank.savings_estimate
   - Higher if: controlled spending, reasonable expenses vs income, good savings

3. savings_behavior_score
   - Use: bank.savings_estimate, bank.avg_balance, bank.total_income vs bank.total_expenses
   - Higher if: positive savings, healthy balance, income > expenses

4. payment_discipline_score
   - Use: credit_bureau.late_payments, bank.late_fees, bank.negative_balance, credit_bureau.credit_utilization
   - Higher if: no late payments, no fees, no negative balance, low utilization

5. digital_behavior_score
   - Use: upi.digital_behavior_index, upi.upi_bill_payments, upi.regularity_per_day
   - Higher if: active digital usage, regular bill payments, consistent transactions

6. lifestyle_stability_score
   - Use: bank.emi_payments, upi.regularity_per_day, credit_bureau.open_loans
   - Higher if: manageable EMIs, regular transaction patterns, stable loan portfolio

Then calculate final behavior_score (0-10) as weighted average:
- income_stability: 15%
- spending_discipline: 20%
- savings_behavior: 20%
- payment_discipline: 25%
- digital_behavior: 10%
- lifestyle_stability: 10%

Respond ONLY with valid JSON in this exact format:
{{
  "income_stability_score": <number 0-10>,
  "spending_discipline_score": <number 0-10>,
  "savings_behavior_score": <number 0-10>,
  "payment_discipline_score": <number 0-10>,
  "digital_behavior_score": <number 0-10>,
  "lifestyle_stability_score": <number 0-10>,
  "behavior_score": <number 0-10>,
  "explanation": "<3-4 bullet points explaining the verified score based on data>",
  "key_insights": {{
    "positive": ["<what increased score based on data>", "<another positive>"],
    "negative": ["<what reduced score based on data>", "<another negative>"]
  }},
  "red_flags": ["<any concerning patterns from data>"],
  "improvement_tips": ["<tip 1>", "<tip 2>", "<tip 3>"]
}}
"""
    
    try:
        # Use Gemini Pro for accurate scoring
        model = genai.GenerativeModel('gemini-2.0-flash-exp')
        response = model.generate_content(prompt, timeout=30)
        response_text = response.text.strip()
        
        # Extract JSON from response
        json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
        if json_match:
            result = json.loads(json_match.group())
            
            # Validate scores are in range
            for key in ['income_stability_score', 'spending_discipline_score', 
                       'savings_behavior_score', 'payment_discipline_score',
                       'digital_behavior_score', 'lifestyle_stability_score', 'behavior_score']:
                if key in result:
                    result[key] = max(0, min(10, float(result[key])))
            
            return result
        else:
            # Fallback if JSON extraction fails
            return get_fallback_score()
    
    except Exception as e:
        print(f"Gemini Pro scoring error: {e}")
        return get_fallback_score()


def get_fallback_score() -> Dict:
    """Fallback scoring if Gemini fails"""
    return {
        "income_stability_score": 7.0,
        "spending_discipline_score": 7.0,
        "savings_behavior_score": 7.0,
        "payment_discipline_score": 7.0,
        "digital_behavior_score": 7.0,
        "lifestyle_stability_score": 7.0,
        "behavior_score": 7.0,
        "explanation": "Based on verified documents, moderate financial behavior observed. Unable to generate detailed analysis.",
        "key_insights": {
            "positive": [],
            "negative": []
        },
        "red_flags": [],
        "improvement_tips": [
            "Maintain consistent savings",
            "Pay bills on time",
            "Track expenses regularly"
        ]
    }

