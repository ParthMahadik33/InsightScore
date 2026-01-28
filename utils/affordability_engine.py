"""
Sanction Amount Estimator (EMI Affordability Engine)

Deterministic, fintech-style rules:
- Uses verified income/expenses (no LLM)
- EMI should not exceed 30-40% of net income (tier + loan type dependent)
- Produces: recommended loan amount, safe EMI range, disposable income after EMI, risk-adjusted limits
"""

from __future__ import annotations

import math
from typing import Dict, Optional


def _safe_float(x, default: float = 0.0) -> float:
    try:
        if x is None:
            return default
        return float(x)
    except Exception:
        return default


def _estimate_monthly_from_total(total: float) -> float:
    """
    Heuristic: many uploaded statements are ~3 months.
    If total seems large, assume 3 months; else assume already monthly.
    """
    if total <= 0:
        return 0.0
    if total >= 200000:  # heuristic threshold
        return total / 3.0
    return total


def _loan_type_tenure_months(loan_type: str) -> int:
    lt = (loan_type or "other").lower()
    return {
        "personal": 24,
        "home": 240,
        "education": 84,
        "business": 36,
        "vehicle": 60,
        "gold": 24,
        "other": 24,
    }.get(lt, 24)


def _loan_type_emi_ratio_band(loan_type: str) -> Dict[str, float]:
    lt = (loan_type or "other").lower()
    # More stable / secured loans can allow higher EMI ratios.
    return {
        "home": {"min": 0.32, "max": 0.40},
        "gold": {"min": 0.30, "max": 0.40},
        "education": {"min": 0.30, "max": 0.38},
        "personal": {"min": 0.28, "max": 0.35},
        "vehicle": {"min": 0.28, "max": 0.34},
        "business": {"min": 0.25, "max": 0.33},
        "other": {"min": 0.25, "max": 0.33},
    }.get(lt, {"min": 0.25, "max": 0.33})


def _risk_multiplier(risk_tier: str) -> float:
    tier = (risk_tier or "Yellow").lower()
    if tier == "green":
        return 1.0
    if tier == "red":
        return 0.65
    return 0.85


def _pmt_to_pv(emi: float, annual_rate_pct: float, n_months: int) -> float:
    """
    Convert EMI to principal (PV) using standard annuity formula.
    PV = EMI * ( (1 - (1+r)^-n) / r )
    """
    if emi <= 0 or n_months <= 0:
        return 0.0
    r = (annual_rate_pct / 100.0) / 12.0
    if r <= 0:
        return emi * n_months
    return emi * (1.0 - (1.0 + r) ** (-n_months)) / r


def estimate_affordability(
    verified_dataset: Dict,
    risk_tier: str,
    loan_type: str,
    interest_rate_apr_mid: float,
) -> Dict:
    """
    Main engine. Uses ONLY verified_dataset numeric metrics.
    """
    bank = verified_dataset.get("bank", {}) if verified_dataset else {}
    salary = verified_dataset.get("salary", {}) if verified_dataset else {}
    upi = verified_dataset.get("upi", {}) if verified_dataset else {}

    # Income: prefer verified salary net, then bank avg_monthly_income, else estimate from totals.
    net_income = _safe_float(salary.get("net_salary"), 0.0)
    if net_income <= 0:
        net_income = _safe_float(salary.get("gross_salary"), 0.0) * 0.85  # approximate net

    if net_income <= 0:
        net_income = _safe_float(bank.get("avg_monthly_income"), 0.0)

    if net_income <= 0:
        net_income = _estimate_monthly_from_total(_safe_float(bank.get("total_income"), 0.0))

    # Expenses: estimate monthly from totals if needed
    monthly_expenses = _safe_float(bank.get("total_expenses"), 0.0)
    monthly_expenses = _estimate_monthly_from_total(monthly_expenses)

    # Savings: keep consistent with estimated month
    monthly_savings = _safe_float(bank.get("savings_estimate"), 0.0)
    monthly_savings = _estimate_monthly_from_total(monthly_savings)

    # Disposable before EMI (never negative)
    disposable_before_emi = max(0.0, net_income - monthly_expenses)

    # EMI band base (loan-type)
    band = _loan_type_emi_ratio_band(loan_type)
    tier_mult = _risk_multiplier(risk_tier)

    # Tier affects max ratio primarily
    min_ratio = band["min"] * (0.9 if risk_tier.lower() == "red" else 1.0)
    max_ratio = band["max"] * tier_mult
    max_ratio = min(max_ratio, 0.40)  # global cap
    min_ratio = min(min_ratio, max_ratio)

    safe_emi_min = net_income * min_ratio
    safe_emi_max = net_income * max_ratio

    # Also ensure EMI doesn't exceed disposable income (hard safety)
    safe_emi_max = min(safe_emi_max, disposable_before_emi)
    safe_emi_min = min(safe_emi_min, safe_emi_max)

    tenure_months = _loan_type_tenure_months(loan_type)
    principal_max = _pmt_to_pv(safe_emi_max, interest_rate_apr_mid, tenure_months)
    principal_min = _pmt_to_pv(safe_emi_min, interest_rate_apr_mid, tenure_months)

    return {
        "loan_type": (loan_type or "other").lower(),
        "risk_tier": risk_tier,
        "assumptions": {
            "tenure_months": tenure_months,
            "interest_rate_apr_mid": float(interest_rate_apr_mid),
            "income_net_monthly_used": float(net_income),
            "expenses_monthly_estimated": float(monthly_expenses),
            "emi_ratio_min": float(min_ratio),
            "emi_ratio_max": float(max_ratio),
            "tier_multiplier": float(tier_mult),
        },
        "safe_emi_range": {
            "min": float(round(safe_emi_min, 2)),
            "max": float(round(safe_emi_max, 2)),
        },
        "disposable_income_after_max_emi": float(round(disposable_before_emi - safe_emi_max, 2)),
        "recommended_loan_amount_range": {
            "min": float(round(principal_min, 2)),
            "max": float(round(principal_max, 2)),
        },
        "notes": "Estimates based on verified income/expenses. EMI capped by both ratio rules and disposable income.",
    }


