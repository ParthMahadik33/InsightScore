"""
Personalized Improvement Plans (Dynamic, NO LLM)

Uses verified extracted JSON (bank/upi/credit_bureau/salary + behavior_json) to generate:
- weak areas
- practical, data-driven tips with amounts when possible
"""

from typing import Dict, List, Optional


def _safe_float(x, default: float = 0.0) -> float:
    try:
        if x is None:
            return default
        return float(x)
    except Exception:
        return default


def _estimate_monthly(total: float) -> float:
    if total <= 0:
        return 0.0
    # heuristic: if big, assume 3 months statement
    if total >= 200000:
        return total / 3.0
    return total


def generate_improvement_plan(verified_dataset: Dict, behavior_json: Optional[Dict] = None) -> Dict:
    bank = verified_dataset.get("bank", {}) if verified_dataset else {}
    upi = verified_dataset.get("upi", {}) if verified_dataset else {}
    bureau = verified_dataset.get("credit_bureau", {}) if verified_dataset else {}
    salary = verified_dataset.get("salary", {}) if verified_dataset else {}

    tips: List[str] = []
    weak_areas: List[str] = []

    income = _safe_float(salary.get("net_salary"), 0.0)
    if income <= 0:
        income = _safe_float(bank.get("avg_monthly_income"), 0.0)
    if income <= 0:
        income = _estimate_monthly(_safe_float(bank.get("total_income"), 0.0))

    expenses = _estimate_monthly(_safe_float(bank.get("total_expenses"), 0.0))
    savings = _estimate_monthly(_safe_float(bank.get("savings_estimate"), 0.0))

    upi_spend = _estimate_monthly(_safe_float(upi.get("upi_total_spend"), 0.0))
    bill_payments = int(_safe_float(upi.get("upi_bill_payments"), 0))
    txn_count = int(_safe_float(upi.get("upi_transaction_count"), 0))

    late_payments = int(_safe_float(bureau.get("late_payments"), 0))
    utilization = bureau.get("credit_utilization")
    utilization_f = _safe_float(utilization, -1.0) if utilization is not None else None

    # 1) Savings weakness
    if income > 0 and savings < income * 0.10:
        weak_areas.append("Low savings buffer")
        target_savings = max(0.0, income * 0.15)
        delta = max(0.0, target_savings - savings)
        tips.append(f"Maintain at least ₹{target_savings:,.0f} monthly savings buffer (increase by ₹{delta:,.0f}).")

    # 2) High expenses
    if income > 0 and expenses > income * 0.75:
        weak_areas.append("High expense ratio")
        reduce_by = expenses * 0.10
        tips.append(f"Reduce monthly expenses by ~10% (≈₹{reduce_by:,.0f}) to improve savings and EMI capacity.")

    # 3) Heavy UPI spend
    if income > 0 and upi_spend > income * 0.25:
        weak_areas.append("High UPI discretionary spend")
        cut = upi_spend * 0.20
        tips.append(f"Reduce UPI discretionary spend by 20% (≈₹{cut:,.0f} monthly).")
    elif upi_spend > 0 and txn_count > 60:
        weak_areas.append("High transaction frequency")
        tips.append("Set weekly UPI spending caps and review top merchants every weekend.")

    # 4) Payment discipline
    if late_payments > 0:
        weak_areas.append("Payment discipline risk")
        tips.append("Enable auto-pay for EMIs/credit card minimums and set bill reminders 3 days before due dates.")

    if utilization_f is not None and utilization_f >= 50:
        weak_areas.append("High credit utilization")
        tips.append("Try keeping credit utilization under 30% by paying mid-cycle or splitting spends across cards.")

    # 5) Negative balance / fees (bank signals)
    if bank.get("negative_balance"):
        weak_areas.append("Overdraft/negative balance risk")
        tips.append("Maintain a minimum balance buffer (e.g., ₹5,000–₹10,000) to avoid overdraft/penalty charges.")

    # 6) If we have very little, still provide actionable (but still data-anchored)
    if not tips:
        tips = [
            "Continue maintaining on-time payments to keep your verified risk stable.",
            "Track monthly income vs expenses to maintain a positive savings estimate.",
        ]

    return {
        "weak_areas": list(dict.fromkeys(weak_areas))[:6],
        "tips": tips[:8],
        "inputs_used": {
            "income_monthly": income,
            "expenses_monthly_est": expenses,
            "savings_monthly_est": savings,
            "upi_spend_monthly_est": upi_spend,
            "late_payments": late_payments,
            "credit_utilization": utilization,
        },
    }


