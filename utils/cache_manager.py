"""
Cache Manager for Verified Scores
Hashes actual file content (not JSON) for accurate caching
"""
import hashlib
import os
from typing import Dict, Optional, List


def hash_file_content(file_path: str) -> str:
    """
    Calculate SHA256 hash of file content.
    Used for caching - same files = same hash = cached score.
    """
    try:
        with open(file_path, 'rb') as f:
            file_hash = hashlib.sha256(f.read()).hexdigest()
        return file_hash
    except Exception as e:
        print(f"Error hashing file {file_path}: {e}")
        return ""


def hash_documents(files_dict: Dict[str, str]) -> str:
    """
    Calculate combined hash of all uploaded documents.
    This is used to check if we've processed these exact files before.
    
    Args:
        files_dict: Dictionary with keys like 'cibil', 'bank', 'upi', 'salary'
                   and values as file paths
    
    Returns:
        SHA256 hash string
    """
    hashes = []
    
    # Sort keys for consistent hashing
    for key in sorted(files_dict.keys()):
        file_path = files_dict[key]
        if file_path and os.path.exists(file_path):
            file_hash = hash_file_content(file_path)
            if file_hash:
                hashes.append(f"{key}:{file_hash}")
    
    # Combine all hashes
    combined = "|".join(hashes)
    return hashlib.sha256(combined.encode()).hexdigest()


def check_cache(conn, user_id: str, doc_hash: str) -> Optional[Dict]:
    """
    Check if a cached verified score exists for this document hash.
    
    Args:
        conn: Database connection
        user_id: User ID
        doc_hash: Document hash
    
    Returns:
        Cached score data if found, None otherwise
    """
    try:
        cur = conn.execute(
            "SELECT * FROM verified_scores WHERE user_id = ? AND doc_hash = ?",
            (user_id, doc_hash)
        )
        cached = cur.fetchone()
        
        if cached:
            return {
                "behavior_json": cached["behavior_json"],
                "hybrid_score": cached["hybrid_score"],
                "risk_tier": cached["risk_tier"] if "risk_tier" in cached.keys() else None,
                "affordability_json": cached["affordability_json"] if "affordability_json" in cached.keys() else None,
                "interest_rate_json": cached["interest_rate_json"] if "interest_rate_json" in cached.keys() else None,
                "improvement_plan_json": cached["improvement_plan_json"] if "improvement_plan_json" in cached.keys() else None,
                "cibil_json": cached["cibil_json"],
                "bank_json": cached["bank_json"],
                "upi_json": cached["upi_json"],
                "salary_json": cached["salary_json"],
                "created_at": cached["created_at"]
            }
        return None
    except Exception as e:
        print(f"Cache check error: {e}")
        return None


def save_verified_score(
    conn,
    user_id: str,
    doc_hash: str,
    cibil_json: Dict,
    bank_json: Dict,
    upi_json: Dict,
    salary_json: Dict,
    behavior_json: Dict,
    hybrid_score: float,
    risk_tier: Optional[str] = None,
    affordability_json: Optional[Dict] = None,
    interest_rate_json: Optional[Dict] = None,
    improvement_plan_json: Optional[Dict] = None,
) -> bool:
    """
    Save verified score to database with caching.
    
    Returns:
        True if saved successfully, False otherwise
    """
    try:
        import json
        conn.execute(
            """INSERT INTO verified_scores 
               (user_id, cibil_json, bank_json, upi_json, salary_json, behavior_json, hybrid_score,
                risk_tier, affordability_json, interest_rate_json, improvement_plan_json, doc_hash)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                user_id,
                json.dumps(cibil_json),
                json.dumps(bank_json),
                json.dumps(upi_json),
                json.dumps(salary_json),
                json.dumps(behavior_json),
                hybrid_score,
                risk_tier,
                json.dumps(affordability_json) if affordability_json is not None else None,
                json.dumps(interest_rate_json) if interest_rate_json is not None else None,
                json.dumps(improvement_plan_json) if improvement_plan_json is not None else None,
                doc_hash
            )
        )
        conn.commit()
        return True
    except Exception as e:
        print(f"Error saving verified score: {e}")
        conn.rollback()
        return False

