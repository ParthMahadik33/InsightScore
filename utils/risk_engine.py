"""
Risk Tier Classification for VERIFIED hybrid scores.

Tiers:
- Green (Low Risk)
- Yellow (Medium Risk)
- Red (High Risk)
"""

from typing import Dict, Optional


def compute_risk_tier(hybrid_score: Optional[float]) -> Dict[str, str]:
    """
    Compute risk tier from VERIFIED hybrid score.

    Hybrid score in this app is effectively on a 0-900-ish scale (CIBIL blended with behavior*100).
    Thresholds:
    - >= 750: Green
    - 650-749: Yellow
    - < 650: Red
    """
    if hybrid_score is None:
        return {"tier": "Yellow", "label": "Medium Risk", "icon": "🟡"}

    try:
        score = float(hybrid_score)
    except Exception:
        return {"tier": "Yellow", "label": "Medium Risk", "icon": "🟡"}

    if score >= 750:
        return {"tier": "Green", "label": "Low Risk", "icon": "🟢"}
    if score >= 650:
        return {"tier": "Yellow", "label": "Medium Risk", "icon": "🟡"}
    return {"tier": "Red", "label": "High Risk", "icon": "🔴"}


