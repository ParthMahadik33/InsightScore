"""
Script to populate sample data for testing the InsightScore application.
This script creates a user with pseudo financial data.
"""

import sqlite3
import json
import hashlib
import secrets
from datetime import datetime, timedelta
from pathlib import Path
from werkzeug.security import generate_password_hash

# Database path
BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "auth.db"

def get_db():
    """Connect to database"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def generate_unique_user_id():
    """Generate unique user ID"""
    random_part = secrets.token_hex(4).upper()
    return f"USR-{random_part}"

def generate_unique_lender_id():
    """Generate unique lender ID"""
    random_part = secrets.token_hex(4).upper()
    return f"LND-{random_part}"

def init_database():
    """Initialize database schema"""
    conn = get_db()
    
    # Create users table
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            unique_user_id TEXT UNIQUE,
            username TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            role TEXT DEFAULT 'user',
            phone TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    
    # Create lenders table
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS lenders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            unique_lender_id TEXT UNIQUE,
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            org_name TEXT,
            loan_types_offered TEXT,
            role TEXT DEFAULT 'lender',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    
    # Create quick_scores table (monthly behavioral scores)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS quick_scores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            behavior_json TEXT,
            hybrid_score REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
        """
    )
    
    # Create verified_scores table (document-based scores)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS verified_scores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            cibil_json TEXT,
            bank_json TEXT,
            upi_json TEXT,
            salary_json TEXT,
            behavior_json TEXT,
            hybrid_score REAL,
            risk_tier TEXT,
            affordability_json TEXT,
            interest_rate_json TEXT,
            improvement_plan_json TEXT,
            doc_hash TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
        """
    )
    
    # Create loan_requests table
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS loan_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            lender_id INTEGER,
            loan_type TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            decision_json TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id),
            FOREIGN KEY (lender_id) REFERENCES lenders (id)
        )
        """
    )
    
    # Create notifications table
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            lender_id INTEGER,
            notification_type TEXT NOT NULL,
            message TEXT NOT NULL,
            is_read INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id),
            FOREIGN KEY (lender_id) REFERENCES lenders (id)
        )
        """
    )
    
    conn.commit()
    conn.close()
    print("✓ Database schema initialized")

def populate_sample_data():
    """Populate sample financial data for Ninad"""
    conn = get_db()
    
    # User credentials
    email = "ninadsawant12@gmail.com"
    name = "ninad"
    password = "vini1234"
    phone = "9876543210"
    
    try:
        # Check if user already exists
        cur = conn.execute("SELECT id FROM users WHERE email = ?", (email,))
        existing_user = cur.fetchone()
        
        if existing_user:
            user_id = existing_user[0]
            print(f"✓ User already exists with ID: {user_id}")
        else:
            # Create new user
            unique_user_id = generate_unique_user_id()
            password_hash = generate_password_hash(password)
            
            conn.execute(
                """
                INSERT INTO users (unique_user_id, username, email, password_hash, role, phone)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (unique_user_id, name, email, password_hash, "user", phone)
            )
            conn.commit()
            
            cur = conn.execute("SELECT id FROM users WHERE email = ?", (email,))
            user_id = cur.fetchone()[0]
            print(f"✓ User created successfully with ID: {user_id}, Unique ID: {unique_user_id}")
        
        # === POPULATE QUICK SCORES (Monthly Behavioral Scores) ===
        print("\n📊 Creating monthly behavioral scores...")
        
        quick_scores_data = [
            {
                "month": "2025-10",
                "score": 620,
                "behavior": {
                    "transaction_frequency": {"score": 650, "status": "moderate", "transactions_count": 45},
                    "savings_ratio": {"score": 580, "status": "fair", "savings_percentage": 12.5},
                    "loan_payment_timeliness": {"score": 720, "status": "good", "on_time_ratio": 85},
                    "credit_utilization": {"score": 550, "status": "fair", "utilization_ratio": 65},
                    "spending_consistency": {"score": 680, "status": "moderate", "consistency_score": 680}
                }
            },
            {
                "month": "2025-11",
                "score": 680,
                "behavior": {
                    "transaction_frequency": {"score": 720, "status": "good", "transactions_count": 52},
                    "savings_ratio": {"score": 650, "status": "fair", "savings_percentage": 15.2},
                    "loan_payment_timeliness": {"score": 750, "status": "good", "on_time_ratio": 90},
                    "credit_utilization": {"score": 620, "status": "fair", "utilization_ratio": 58},
                    "spending_consistency": {"score": 700, "status": "good", "consistency_score": 700}
                }
            },
            {
                "month": "2025-12",
                "score": 730,
                "behavior": {
                    "transaction_frequency": {"score": 780, "status": "good", "transactions_count": 58},
                    "savings_ratio": {"score": 720, "status": "good", "savings_percentage": 18.5},
                    "loan_payment_timeliness": {"score": 800, "status": "excellent", "on_time_ratio": 95},
                    "credit_utilization": {"score": 680, "status": "fair", "utilization_ratio": 52},
                    "spending_consistency": {"score": 750, "status": "good", "consistency_score": 750}
                }
            },
            {
                "month": "2026-01",
                "score": 760,
                "behavior": {
                    "transaction_frequency": {"score": 800, "status": "excellent", "transactions_count": 62},
                    "savings_ratio": {"score": 780, "status": "good", "savings_percentage": 21.0},
                    "loan_payment_timeliness": {"score": 820, "status": "excellent", "on_time_ratio": 97},
                    "credit_utilization": {"score": 720, "status": "good", "utilization_ratio": 48},
                    "spending_consistency": {"score": 780, "status": "good", "consistency_score": 780}
                }
            }
        ]
        
        # Delete existing quick_scores for this user
        conn.execute("DELETE FROM quick_scores WHERE user_id = ?", (user_id,))
        conn.commit()
        
        for i, score_data in enumerate(quick_scores_data):
            behavior_json = json.dumps(score_data["behavior"])
            created_at = (datetime.now() - timedelta(days=120-i*30)).strftime("%Y-%m-%d %H:%M:%S")
            
            conn.execute(
                """
                INSERT INTO quick_scores (user_id, behavior_json, hybrid_score, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (user_id, behavior_json, score_data["score"], created_at)
            )
        
        conn.commit()
        print(f"✓ Created {len(quick_scores_data)} monthly behavioral scores")
        
        # === POPULATE VERIFIED SCORES (Document-based Scores) ===
        print("\n📄 Creating verified document-based score...")
        
        # CIBIL Data (Credit Information Bureau)
        cibil_data = {
            "cibil_score": 745,
            "credit_grade": "A",
            "total_accounts": 4,
            "accounts_detail": [
                {
                    "type": "Credit Card",
                    "status": "Active",
                    "limit": 500000,
                    "balance": 185000,
                    "utilization": 37,
                    "payment_history": "Good"
                },
                {
                    "type": "Home Loan",
                    "status": "Active",
                    "principal": 3500000,
                    "balance": 3200000,
                    "emi": 35000,
                    "payment_history": "Excellent"
                },
                {
                    "type": "Car Loan",
                    "status": "Active",
                    "principal": 1200000,
                    "balance": 450000,
                    "emi": 15000,
                    "payment_history": "Good"
                },
                {
                    "type": "Personal Loan",
                    "status": "Closed",
                    "principal": 500000,
                    "balance": 0,
                    "payment_history": "Good"
                }
            ],
            "enquiries_last_6_months": 2,
            "enquiries_last_12_months": 3,
            "default_history": None,
            "credit_history_length_months": 84
        }
        
        # Bank Statement Data
        bank_data = {
            "account_type": "Savings",
            "bank_name": "HDFC Bank",
            "account_age_months": 84,
            "average_monthly_balance": 250000,
            "minimum_monthly_balance": 85000,
            "maximum_monthly_balance": 520000,
            "total_inflows_3_months": 1850000,
            "total_outflows_3_months": 1620000,
            "transaction_count_3_months": 87,
            "regular_deposits": True,
            "salary_deposits": {
                "frequency": "Monthly",
                "average_amount": 450000,
                "consistency": 3
            },
            "large_transactions": [
                {"date": "2025-12-15", "amount": 150000, "type": "Investment - Mutual Funds"},
                {"date": "2025-11-28", "amount": 75000, "type": "Investment - Insurance Premium"},
                {"date": "2025-10-10", "amount": 200000, "type": "Investment - Fixed Deposit"}
            ],
            "bounced_cheques": 0,
            "negative_balance_days": 0
        }
        
        # Salary Slip Data
        salary_data = {
            "current_salary": 450000,
            "employment_type": "Full-time",
            "designation": "Senior Software Engineer",
            "company_name": "Tech Solutions Pvt Ltd",
            "joining_date": "2019-03-15",
            "years_of_employment": 5,
            "salary_consistency": True,
            "salary_growth": {
                "2021": 350000,
                "2022": 380000,
                "2023": 410000,
                "2024": 435000,
                "2025": 450000
            },
            "hra": 90000,
            "da": 45000,
            "basic": 315000,
            "deductions": {
                "pf": 22500,
                "tax": 45000,
                "insurance": 5000
            }
        }
        
        # UPI Transaction Data
        upi_data = {
            "total_transactions_6_months": 245,
            "total_sent": 480000,
            "total_received": 620000,
            "transaction_frequency": "Daily",
            "average_transaction_size": 4500,
            "largest_transaction": 125000,
            "merchant_categories": {
                "Groceries & Food": {"count": 65, "amount": 185000, "percentage": 26.5},
                "Entertainment": {"count": 42, "amount": 95000, "percentage": 13.6},
                "Travel & Transport": {"count": 38, "amount": 72000, "percentage": 10.3},
                "Utilities & Bills": {"count": 28, "amount": 105000, "percentage": 15.1},
                "Shopping": {"count": 45, "amount": 142000, "percentage": 20.3},
                "Insurance & Investment": {"count": 15, "amount": 68000, "percentage": 9.7},
                "Other": {"count": 12, "amount": 45000, "percentage": 6.4}
            },
            "spending_pattern": "Regular and Controlled",
            "peer_comparison": "Above Average"
        }
        
        # Behavior Analysis (calculated from documents)
        behavior_data = {
            "financial_discipline": {"score": 820, "status": "Excellent"},
            "payment_reliability": {"score": 850, "status": "Excellent"},
            "savings_propensity": {"score": 780, "status": "Good"},
            "investment_awareness": {"score": 800, "status": "Good"},
            "income_stability": {"score": 850, "status": "Excellent"},
            "spending_control": {"score": 750, "status": "Good"},
            "debt_management": {"score": 830, "status": "Excellent"},
            "overall_assessment": "Financially responsible individual with excellent payment history and good savings behavior"
        }
        
        # Risk Tier
        risk_tier = "TIER-1"  # Low Risk
        
        # Affordability Analysis
        affordability_data = {
            "annual_income": 5400000,
            "monthly_income": 450000,
            "existing_monthly_obligations": 50000,
            "monthly_expenditure": 67500,
            "monthly_surplus": 332500,
            "debt_to_income_ratio": 0.11,
            "approved_loan_amounts": {
                "personal": {"min": 300000, "max": 2500000, "recommended": 1500000},
                "home": {"min": 2000000, "max": 8000000, "recommended": 5000000},
                "education": {"min": 500000, "max": 2500000, "recommended": 1500000},
                "business": {"min": 1000000, "max": 5000000, "recommended": 2500000},
                "vehicle": {"min": 500000, "max": 3000000, "recommended": 2000000}
            },
            "recommended_tenure_months": 60
        }
        
        # Interest Rate Recommendation
        interest_rate_data = {
            "base_rate": 8.5,
            "risk_adjustment": -1.5,
            "performance_bonus": -0.5,
            "offered_rate_range": {"min": 6.5, "max": 7.8},
            "recommended_rate": 7.2,
            "effective_from": "2026-01-28",
            "rate_validity_days": 30,
            "rationale": "Excellent credit profile and payment history warrant preferential rates"
        }
        
        # Improvement Plan
        improvement_plan = {
            "current_score": 7.8,
            "potential_score": 8.5,
            "recommendations": [
                {
                    "category": "Credit Utilization",
                    "current_status": "Fair (37%)",
                    "suggestion": "Maintain credit card balance below 30% of limit",
                    "potential_improvement": "+0.3 points",
                    "timeline": "Immediate"
                },
                {
                    "category": "Credit Mix",
                    "current_status": "Good (4 accounts)",
                    "suggestion": "Consider maintaining diverse credit products",
                    "potential_improvement": "+0.2 points",
                    "timeline": "6 months"
                },
                {
                    "category": "Credit Enquiries",
                    "current_status": "Fair (3 enquiries in 12 months)",
                    "suggestion": "Limit new credit applications",
                    "potential_improvement": "+0.2 points",
                    "timeline": "Ongoing"
                }
            ]
        }
        
        # Delete existing verified_scores for this user
        conn.execute("DELETE FROM verified_scores WHERE user_id = ?", (user_id,))
        conn.commit()
        
        # Create doc_hash (simulated hash of uploaded documents)
        doc_hash = hashlib.sha256(
            f"cibil_bank_upi_salary_{email}".encode()
        ).hexdigest()
        
        conn.execute(
            """
            INSERT INTO verified_scores (
                user_id, cibil_json, bank_json, upi_json, salary_json, 
                behavior_json, hybrid_score, risk_tier, affordability_json, 
                interest_rate_json, improvement_plan_json, doc_hash, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                json.dumps(cibil_data),
                json.dumps(bank_data),
                json.dumps(upi_data),
                json.dumps(salary_data),
                json.dumps(behavior_data),
                780,
                risk_tier,
                json.dumps(affordability_data),
                json.dumps(interest_rate_data),
                json.dumps(improvement_plan),
                doc_hash,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            )
        )
        conn.commit()
        print("✓ Created verified document-based score (CIBIL, Bank, UPI, Salary, Behavior, Risk, Affordability, Interest Rate, Improvement Plan)")
        
        # === POPULATE LOAN REQUESTS ===
        print("\n💰 Creating sample loan requests...")
        
        # Get a sample lender (or create one if needed)
        cur = conn.execute("SELECT id FROM lenders LIMIT 1")
        lender = cur.fetchone()
        
        if not lender:
            # Create a sample lender
            unique_lender_id = f"LND-{hashlib.md5(b'sample_lender').hexdigest()[:8].upper()}"
            lender_password = generate_password_hash("lender123")
            conn.execute(
                """
                INSERT INTO lenders (unique_lender_id, name, email, password_hash, org_name, loan_types_offered, role)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (unique_lender_id, "Sample Bank", "bank@example.com", lender_password, 
                 "Sample Bank Ltd", "personal,home,education,vehicle", "lender")
            )
            conn.commit()
            cur = conn.execute("SELECT id FROM lenders WHERE email = ?", ("bank@example.com",))
            lender = cur.fetchone()
        
        lender_id = lender[0]
        
        # Delete existing loan requests for this user
        conn.execute("DELETE FROM loan_requests WHERE user_id = ?", (user_id,))
        conn.commit()
        
        loan_requests = [
            {
                "loan_type": "personal",
                "status": "approved",
                "decision": {
                    "approved_amount": 1500000,
                    "tenure_months": 60,
                    "interest_rate": 7.2,
                    "monthly_emi": 28745,
                    "approval_reason": "Excellent credit profile with strong payment history"
                }
            },
            {
                "loan_type": "home",
                "status": "processing",
                "decision": {
                    "status": "Under Review",
                    "estimated_approval_amount": 5000000,
                    "documents_received": ["CIBIL Report", "Bank Statement", "Salary Slip"],
                    "pending_documents": []
                }
            },
            {
                "loan_type": "vehicle",
                "status": "rejected",
                "decision": {
                    "rejected_reason": "Applicant already has active vehicle loan",
                    "suggestion": "Can apply after settling current vehicle loan"
                }
            }
        ]
        
        for i, loan_req in enumerate(loan_requests):
            created_at = (datetime.now() - timedelta(days=45-i*15)).strftime("%Y-%m-%d %H:%M:%S")
            conn.execute(
                """
                INSERT INTO loan_requests (user_id, lender_id, loan_type, status, decision_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (user_id, lender_id, loan_req["loan_type"], loan_req["status"], 
                 json.dumps(loan_req["decision"]), created_at)
            )
        
        conn.commit()
        print(f"✓ Created {len(loan_requests)} sample loan requests")
        
        # === POPULATE NOTIFICATIONS ===
        print("\n🔔 Creating sample notifications...")
        
        # Delete existing notifications for this user
        conn.execute("DELETE FROM notifications WHERE user_id = ?", (user_id,))
        conn.commit()
        
        notifications = [
            {
                "type": "loan_approved",
                "message": "Congratulations! Your personal loan of ₹15,00,000 has been approved!",
                "is_read": 1
            },
            {
                "type": "score_updated",
                "message": "Your financial score has been updated to 7.8 (Excellent)",
                "is_read": 1
            },
            {
                "type": "loan_status",
                "message": "Your home loan application is under review. Documents verified successfully.",
                "is_read": 0
            },
            {
                "type": "score_improvement",
                "message": "Your score improved by 0.5 points this month! Keep up the good financial discipline.",
                "is_read": 0
            }
        ]
        
        for i, notif in enumerate(notifications):
            created_at = (datetime.now() - timedelta(days=30-i*10)).strftime("%Y-%m-%d %H:%M:%S")
            conn.execute(
                """
                INSERT INTO notifications (user_id, lender_id, notification_type, message, is_read, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (user_id, lender_id, notif["type"], notif["message"], notif["is_read"], created_at)
            )
        
        conn.commit()
        print(f"✓ Created {len(notifications)} sample notifications")
        
        print("\n" + "="*60)
        print("✅ SAMPLE DATA POPULATED SUCCESSFULLY!")
        print("="*60)
        print(f"\n📌 User Details:")
        print(f"  Email: {email}")
        print(f"  Name: {name}")
        print(f"  Password: {password}")
        print(f"  Phone: {phone}")
        print(f"  User ID: {user_id}")
        print(f"\n📊 Data Created:")
        print(f"  ✓ 4 Monthly behavioral scores (Oct 2025 - Jan 2026)")
        print(f"  ✓ 1 Verified document-based score (CIBIL: 745, Risk: TIER-1)")
        print(f"  ✓ 3 Loan requests (1 Approved, 1 Processing, 1 Rejected)")
        print(f"  ✓ 4 Notifications")
        print(f"\n🎯 Ready to test:")
        print(f"  - Login with above credentials")
        print(f"  - View dashboard with graphs and scores")
        print(f"  - Check loan applications and approval details")
        print(f"  - Review financial improvement recommendations")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()

if __name__ == "__main__":
    init_database()
    populate_sample_data()
