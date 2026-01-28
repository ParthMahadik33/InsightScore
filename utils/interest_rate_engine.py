"""
Interest Rate Recommendation Engine.

Based on:
- risk tier
- verified hybrid score
- loan type
"""

from typing import Dict, Optional, Tuple


def _range(lo: float, hi: float) -> Dict[str, float]:
    return {"min": float(lo), "max": float(hi)}


def recommend_interest_rate_range(
    risk_tier: str,
    loan_type: Optional[str] = None,
    hybrid_score: Optional[float] = None,
) -> Dict:
    """
    Return an interest rate range recommendation (APR %) for the given risk tier + loan type.

    This is intentionally deterministic (no LLM) and meant for display + lender guidance.
    """
    lt = (loan_type or "other").strip().lower()
    tier = (risk_tier or "Yellow").strip().lower()

    # Base by tier (rough fintech defaults)
    if tier == "green":
        base = _range(11, 13)
    elif tier == "red":
        base = _range(20, 28)
    else:
        base = _range(14, 18)

    # Adjust by loan type
    # (Home/gold secured tend to be cheaper; personal/other more expensive)
    if lt in {"home"}:
        if tier == "green":
            base = _range(8.5, 10.5)
        elif tier == "yellow":
            base = _range(10.5, 13.0)
        else:
            base = _range(13.5, 16.5)
    elif lt in {"gold"}:
        if tier == "green":
            base = _range(9.5, 12.0)
        elif tier == "yellow":
            base = _range(12.0, 15.0)
        else:
            base = _range(16.0, 22.0)
    elif lt in {"vehicle"}:
        if tier == "green":
            base = _range(9.5, 12.0)
        elif tier == "yellow":
            base = _range(12.0, 16.0)
        else:
            base = _range(17.0, 23.0)
    elif lt in {"education"}:
        if tier == "green":
            base = _range(10.0, 12.5)
        elif tier == "yellow":
            base = _range(12.5, 16.5)
        else:
            base = _range(18.0, 24.0)
    elif lt in {"business"}:
        if tier == "green":
            base = _range(12.0, 15.0)
        elif tier == "yellow":
            base = _range(15.0, 20.0)
        else:
            base = _range(22.0, 30.0)
    elif lt in {"personal", "other"}:
        # keep base
        pass

    return {
        "risk_tier": risk_tier,
        "loan_type": lt,
        "apr_percent_range": base,
        "notes": "Recommendation based on verified risk tier + loan type. Final pricing depends on lender policy.",
        "hybrid_score": hybrid_score,
    }


