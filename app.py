from pathlib import Path
import os
import sqlite3
import json
import re
import hashlib
import secrets
from datetime import datetime

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    session,
    jsonify,
    send_from_directory,
)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import pdfplumber
import pandas as pd
import google.generativeai as genai
import requests
from datetime import datetime, timedelta

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "auth.db"
UPLOAD_FOLDER = BASE_DIR / "uploads"
UPLOAD_FOLDER.mkdir(exist_ok=True)

# Gemini API Key
GEMINI_API_KEY = "AIzaSyCrFYdJIoSYyyqH1McZ1S8V_wa9qL-TJu4"
genai.configure(api_key=GEMINI_API_KEY)

ALLOWED_EXTENSIONS = {'pdf', 'csv'}

# Loan types
LOAN_TYPES = ['personal', 'home', 'education', 'business', 'vehicle', 'gold', 'other']

# UltraMSG WhatsApp API Configuration
ULTRAMSG_API_URL = "https://api.ultramsg.com/instance160178/"
ULTRAMSG_TOKEN = "glqz6gz9yr7txkik"
ULTRAMSG_INSTANCE_ID = "instance160178"

def get_db(app: Flask) -> sqlite3.Connection:
    conn = sqlite3.connect(app.config["DATABASE"])
    conn.row_factory = sqlite3.Row
    # Enable auto-commit for context manager
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def generate_unique_user_id():
    """Generate unique user ID: USR-<random>"""
    random_part = secrets.token_hex(4).upper()
    return f"USR-{random_part}"

def generate_unique_lender_id():
    """Generate unique lender ID: LND-<random>"""
    random_part = secrets.token_hex(4).upper()
    return f"LND-{random_part}"

def calculate_doc_hash(files_dict):
    """Calculate hash of uploaded documents for caching"""
    combined = json.dumps(files_dict, sort_keys=True)
    return hashlib.sha256(combined.encode()).hexdigest()

def send_whatsapp_message(phone_number, message):
    """Send WhatsApp message via UltraMSG API"""
    try:
        # Format phone number (remove +, spaces, etc.)
        phone = phone_number.replace("+", "").replace(" ", "").replace("-", "")
        # Ensure it starts with country code (assuming India +91)
        if not phone.startswith("91") and len(phone) == 10:
            phone = "91" + phone
        
        # UltraMSG API endpoint format: https://api.ultramsg.com/{instance}/messages/chat
        url = f"https://api.ultramsg.com/{ULTRAMSG_INSTANCE_ID}/messages/chat"
        payload = {
            "token": ULTRAMSG_TOKEN,
            "to": phone,
            "body": message
        }
        
        response = requests.post(url, data=payload, timeout=10)
        if response.status_code == 200:
            result = response.json()
            if result.get("sent") == "true" or result.get("success") == True:
                return True
            else:
                print(f"WhatsApp API Response: {result}")
                return False
        else:
            print(f"WhatsApp API Error: {response.status_code} - {response.text}")
            return False
    except Exception as e:
        print(f"Error sending WhatsApp message: {str(e)}")
        return False

def check_monthly_reminder(user_id, conn):
    """Check if user needs monthly reminder to check score"""
    try:
        # Get user's phone number
        cur = conn.execute("SELECT phone FROM users WHERE id = ?", (user_id,))
        user = cur.fetchone()
        if not user or not user["phone"]:
            return False
        
        # Get last quick score
        cur = conn.execute(
            "SELECT created_at FROM quick_scores WHERE user_id = ? ORDER BY created_at DESC LIMIT 1",
            (user_id,)
        )
        last_score = cur.fetchone()
        
        # If no score exists or last score is more than 30 days old, send reminder
        should_remind = False
        if not last_score:
            should_remind = True
        else:
            last_date = datetime.fromisoformat(last_score["created_at"].replace("Z", "+00:00") if "Z" in last_score["created_at"] else last_score["created_at"])
            days_since = (datetime.now() - last_date.replace(tzinfo=None)).days
            if days_since >= 30:
                should_remind = True
        
        if should_remind:
            message = "🔔 InsightScore Reminder: It's been a while since you checked your credit score. Generate your monthly Quick InsightScore to track your financial health! Visit your dashboard to get started."
            return send_whatsapp_message(user["phone"], message)
        
        return False
    except Exception as e:
        print(f"Error checking monthly reminder: {str(e)}")
        return False

def init_db(app: Flask) -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with get_db(app) as conn:
        # Check if users table exists and get its columns
        cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
        table_exists = cur.fetchone() is not None
        
        if table_exists:
            # Get existing columns
            cur = conn.execute("PRAGMA table_info(users)")
            columns = [row[1] for row in cur.fetchall()]
            
            # Add unique_user_id column if it doesn't exist
            if 'unique_user_id' not in columns:
                conn.execute("ALTER TABLE users ADD COLUMN unique_user_id TEXT")
                # Generate unique_user_id for existing users
                cur = conn.execute("SELECT id FROM users WHERE unique_user_id IS NULL OR unique_user_id = ''")
                existing_users = cur.fetchall()
                for user_row in existing_users:
                    unique_id = generate_unique_user_id()
                    # Ensure uniqueness
                    max_attempts = 10
                    attempts = 0
                    while attempts < max_attempts:
                        check_cur = conn.execute("SELECT id FROM users WHERE unique_user_id = ?", (unique_id,))
                        if check_cur.fetchone() is None:
                            break
                        unique_id = generate_unique_user_id()
                        attempts += 1
                    conn.execute("UPDATE users SET unique_user_id = ? WHERE id = ?", (unique_id, user_row[0]))
                # Create unique index
                try:
                    conn.execute("CREATE UNIQUE INDEX idx_users_unique_user_id ON users(unique_user_id)")
                except sqlite3.OperationalError:
                    pass
                conn.commit()
            
            # Add role column if it doesn't exist
            if 'role' not in columns:
                conn.execute("ALTER TABLE users ADD COLUMN role TEXT DEFAULT 'user'")
                # Set default role for existing users
                conn.execute("UPDATE users SET role = 'user' WHERE role IS NULL")
                conn.commit()
            
            # Add phone column if it doesn't exist
            if 'phone' not in columns:
                conn.execute("ALTER TABLE users ADD COLUMN phone TEXT")
                conn.commit()
                
                # Update existing users' phone numbers
                conn.execute("UPDATE users SET phone = '9930235462' WHERE LOWER(username) LIKE '%parth%mahadik%' OR LOWER(username) LIKE '%mahadik%parth%'")
                conn.execute("UPDATE users SET phone = '9076370678' WHERE LOWER(username) LIKE '%vini%sawant%' OR LOWER(username) LIKE '%sawant%vini%'")
                conn.commit()
        else:
            # Create users table with all columns
            conn.execute(
                """
                CREATE TABLE users (
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
        
        # Keep old scores table for backward compatibility (will migrate data later)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS scores (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                cibil_score INTEGER,
                behavior_score REAL,
                hybrid_score REAL,
                behavior_details TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
            """
        )
        
        conn.commit()

# Initialize Flask app
app = Flask(__name__)

# Use environment variables in production, with safe fallbacks for local dev
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "change-this-secret-key")
app.config["DATABASE"] = str(DB_PATH)
app.config["UPLOAD_FOLDER"] = str(UPLOAD_FOLDER)
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16MB max file size

# Initialize database
init_db(app)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def extract_cibil_from_pdf(pdf_path):
    """Extract CIBIL score and related info from PDF"""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            text = ""
            for page in pdf.pages:
                text += page.extract_text() or ""
        
        # Look for CIBIL score (typically 300-900)
        score_pattern = r'(?:CIBIL|credit\s*score|score)[\s:]*(\d{3})'
        score_match = re.search(score_pattern, text, re.IGNORECASE)
        cibil_score = int(score_match.group(1)) if score_match else None
        
        # Extract loan history keywords
        loan_keywords = ['loan', 'credit card', 'mortgage', 'EMI']
        loan_count = sum(1 for keyword in loan_keywords if keyword.lower() in text.lower())
        
        # Look for late payments
        late_pattern = r'(?:late|delayed|overdue|missed).*?payment'
        late_payments = len(re.findall(late_pattern, text, re.IGNORECASE))
        
        # Credit utilization (look for percentage)
        util_pattern = r'(\d+(?:\.\d+)?)\s*%'
        util_matches = re.findall(util_pattern, text)
        credit_utilization = float(util_matches[0]) if util_matches else None
        
        return {
            'cibil_score': cibil_score,
            'loan_history_summary': loan_count,
            'late_payments': late_payments,
            'credit_utilization': credit_utilization
        }
    except Exception as e:
        return {'error': str(e)}

def parse_upi_csv(csv_path):
    """Parse UPI transaction CSV"""
    try:
        df = pd.read_csv(csv_path)
        
        # Common column name variations
        amount_cols = [col for col in df.columns if 'amount' in col.lower() or 'rupee' in col.lower() or 'rs' in col.lower()]
        date_cols = [col for col in df.columns if 'date' in col.lower() or 'time' in col.lower()]
        desc_cols = [col for col in df.columns if 'desc' in col.lower() or 'note' in col.lower() or 'remark' in col.lower()]
        
        amount_col = amount_cols[0] if amount_cols else df.columns[1]
        date_col = date_cols[0] if date_cols else df.columns[0]
        
        # Clean amount column
        df[amount_col] = df[amount_col].astype(str).str.replace(r'[^\d.]', '', regex=True)
        df[amount_col] = pd.to_numeric(df[amount_col], errors='coerce')
        
        total_transactions = len(df)
        total_spend = df[amount_col].abs().sum()
        
        # Categorize transactions
        bill_keywords = ['bill', 'electricity', 'water', 'gas', 'phone', 'internet', 'recharge']
        bill_payments = sum(1 for desc in (df[desc_cols[0]] if desc_cols else pd.Series([''])) 
                          if any(kw in str(desc).lower() for kw in bill_keywords))
        
        # Regularity check (transactions per day)
        if date_cols:
            df[date_col] = pd.to_datetime(df[date_col], errors='coerce')
            df = df.dropna(subset=[date_col])
            if len(df) > 0:
                date_range = (df[date_col].max() - df[date_col].min()).days
                regularity = total_transactions / max(date_range, 1)
            else:
                regularity = 0
        else:
            regularity = total_transactions / 30  # Assume monthly
        
        return {
            'total_transactions': int(total_transactions),
            'total_spend': float(total_spend),
            'bill_payments': int(bill_payments),
            'regularity': float(regularity),
            'avg_transaction': float(total_spend / max(total_transactions, 1))
        }
    except Exception as e:
        return {'error': str(e)}

def parse_upi_pdf(pdf_path):
    """Parse UPI transaction PDF"""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            text = ""
            for page in pdf.pages:
                text += page.extract_text() or ""
        
        # Extract amounts (UPI transactions typically show amounts)
        amounts = re.findall(r'₹?\s*(\d+(?:,\d+)*(?:\.\d{2})?)', text)
        amounts = [float(a.replace(',', '')) for a in amounts if a.replace(',', '').replace('.', '').isdigit()]
        
        # Count transactions
        transaction_keywords = ['upi', 'payment', 'transfer', 'debit', 'credit']
        transaction_count = sum(1 for keyword in transaction_keywords if keyword.lower() in text.lower())
        
        total_spend = sum(amounts) if amounts else 0
        
        # Bill payments
        bill_keywords = ['bill', 'electricity', 'water', 'gas', 'phone', 'recharge']
        bill_payments = sum(1 for keyword in bill_keywords if keyword.lower() in text.lower())
        
        return {
            'total_transactions': max(transaction_count, len(amounts)),
            'total_spend': float(total_spend),
            'bill_payments': bill_payments,
            'regularity': max(transaction_count, len(amounts)) / 30,  # Assume monthly
            'avg_transaction': float(total_spend / max(len(amounts), 1))
        }
    except Exception as e:
        return {'error': str(e)}

def parse_bank_statement(pdf_path):
    """Parse bank statement PDF"""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            text = ""
            for page in pdf.pages:
                text += page.extract_text() or ""
        
        # Extract account balance patterns
        balance_patterns = [
            r'(?:balance|bal|available)[\s:]*₹?\s*(\d+(?:,\d+)*(?:\.\d{2})?)',
            r'₹?\s*(\d+(?:,\d+)*(?:\.\d{2})?)\s*(?:balance|bal)'
        ]
        balances = []
        for pattern in balance_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            balances.extend([float(m.replace(',', '')) for m in matches])
        
        avg_balance = sum(balances) / len(balances) if balances else 0
        
        # Extract transaction patterns
        debit_pattern = r'(?:debit|withdrawal|payment)[\s:]*₹?\s*(\d+(?:,\d+)*(?:\.\d{2})?)'
        credit_pattern = r'(?:credit|deposit|salary)[\s:]*₹?\s*(\d+(?:,\d+)*(?:\.\d{2})?)'
        
        debits = re.findall(debit_pattern, text, re.IGNORECASE)
        credits = re.findall(credit_pattern, text, re.IGNORECASE)
        
        total_debits = sum([float(d.replace(',', '')) for d in debits])
        total_credits = sum([float(c.replace(',', '')) for c in credits])
        
        # Count EMI/loan payments
        emi_keywords = ['emi', 'loan', 'installment', 'repayment']
        emi_count = sum(1 for keyword in emi_keywords if keyword.lower() in text.lower())
        
        # Check for overdraft or negative balance
        negative_balance = any('overdraft' in text.lower() or 'negative' in text.lower() or 'insufficient' in text.lower())
        
        return {
            'avg_balance': float(avg_balance),
            'total_debits': float(total_debits),
            'total_credits': float(total_credits),
            'emi_count': emi_count,
            'negative_balance': negative_balance,
            'transaction_count': len(debits) + len(credits)
        }
    except Exception as e:
        return {'error': str(e)}

def parse_salary_slip(pdf_path):
    """Parse salary slip PDF"""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            text = ""
            for page in pdf.pages:
                text += page.extract_text() or ""
        
        # Extract salary/gross/net pay
        salary_patterns = [
            r'(?:gross|salary|net\s*pay|total)[\s:]*₹?\s*(\d+(?:,\d+)*(?:\.\d{2})?)',
            r'₹?\s*(\d+(?:,\d+)*(?:\.\d{2})?)\s*(?:gross|salary|net)'
        ]
        salaries = []
        for pattern in salary_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            salaries.extend([float(m.replace(',', '')) for m in matches])
        
        gross_salary = max(salaries) if salaries else None
        
        # Extract deductions
        deduction_pattern = r'(?:deduction|pf|tax|tds)[\s:]*₹?\s*(\d+(?:,\d+)*(?:\.\d{2})?)'
        deductions = re.findall(deduction_pattern, text, re.IGNORECASE)
        total_deductions = sum([float(d.replace(',', '')) for d in deductions])
        
        # Extract employee ID or name
        emp_id_pattern = r'(?:employee\s*id|emp\s*id|id)[\s:]*([A-Z0-9]+)'
        emp_id_match = re.search(emp_id_pattern, text, re.IGNORECASE)
        emp_id = emp_id_match.group(1) if emp_id_match else None
        
        # Check for regular employment (monthly pattern)
        month_pattern = r'(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\w*\s*\d{4}'
        months_found = len(re.findall(month_pattern, text, re.IGNORECASE))
        is_regular = months_found > 0
        
        return {
            'gross_salary': float(gross_salary) if gross_salary else None,
            'net_salary': float(gross_salary - total_deductions) if gross_salary else None,
            'total_deductions': float(total_deductions),
            'emp_id': emp_id,
            'is_regular': is_regular
        }
    except Exception as e:
        return {'error': str(e)}

def calculate_behavioral_score(data):
    """Use Gemini LLM to calculate behavioral score"""
    prompt = f"""
You are a financial behavior analyst. Based on the following user data, calculate behavioral scores.

User Data:
- Monthly Income: {data.get('monthly_income', 'N/A')}
- Income Stability: {data.get('income_stability', 'N/A')}
- Monthly Expenses: {data.get('monthly_expenses', 'N/A')}
- Monthly Savings: {data.get('monthly_savings', 'N/A')}
- Emergency Fund: {data.get('emergency_fund', 'N/A')}
- Paid Bills On Time: {data.get('paid_bills_on_time', 'N/A')}
- Missed Payments: {data.get('missed_payments', 'N/A')}
- Monthly UPI Transactions: {data.get('monthly_upi_transactions', 'N/A')}
- Digital vs Cash: {data.get('digital_vs_cash', 'N/A')}
- Tracks Expenses: {data.get('tracks_expenses', 'N/A')}
- Overspends Often: {data.get('overspends_often', 'N/A')}
- Sudden Big Expenses: {data.get('sudden_big_expenses', 'N/A')}
- UPI Data: {json.dumps(data.get('upi_data', {}), indent=2)}

Calculate the following scores (each on a scale of 0-10):
1. income_stability_score
2. spending_discipline_score
3. savings_behavior_score
4. payment_discipline_score
5. digital_behavior_score
6. lifestyle_stability_score

Then calculate a final behavior_score (0-10) as a weighted average:
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
  "explanation": "<3-4 bullet points explaining the score>",
  "key_insights": {{
    "positive": ["<what increased score>", "<another positive>"],
    "negative": ["<what reduced score>", "<another negative>"]
  }},
  "improvement_tips": ["<tip 1>", "<tip 2>", "<tip 3>", "<tip 4>"]
}}
"""
    
    try:
        model = genai.GenerativeModel('gemini-2.5-flash')
        response = model.generate_content(prompt)
        response_text = response.text.strip()
        
        # Extract JSON from response
        json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
        if json_match:
            return json.loads(json_match.group())
        else:
            # Fallback scoring
            return {
                "income_stability_score": 7.0,
                "spending_discipline_score": 7.0,
                "savings_behavior_score": 7.0,
                "payment_discipline_score": 7.0,
                "digital_behavior_score": 7.0,
                "lifestyle_stability_score": 7.0,
                "behavior_score": 7.0,
                "explanation": "Based on provided data, moderate financial behavior observed.",
                "key_insights": {"positive": [], "negative": []},
                "improvement_tips": ["Maintain consistent savings", "Pay bills on time", "Track expenses regularly"]
            }
    except Exception as e:
        # Fallback scoring
        return {
            "income_stability_score": 7.0,
            "spending_discipline_score": 7.0,
            "savings_behavior_score": 7.0,
            "payment_discipline_score": 7.0,
            "digital_behavior_score": 7.0,
            "lifestyle_stability_score": 7.0,
            "behavior_score": 7.0,
            "explanation": f"Error in AI analysis: {str(e)}. Using default scores.",
            "key_insights": {"positive": [], "negative": []},
            "improvement_tips": ["Maintain consistent savings", "Pay bills on time", "Track expenses regularly"]
        }

def calculate_hybrid_score(cibil_score, behavior_score):
    """Calculate hybrid score"""
    if cibil_score:
        return (cibil_score * 0.4) + ((behavior_score * 100) * 0.6)
    else:
        return behavior_score * 100

def calculate_verified_behavioral_score(cibil_json, bank_json, upi_json, salary_json):
    """Use Gemini LLM to calculate verified behavioral score from documents"""
    prompt = f"""
You are a financial behavior analyst. Based on OFFICIAL DOCUMENTS provided, calculate verified behavioral scores.
DO NOT use any self-reported data - ONLY use verified data from documents.

Document Data:
- CIBIL Report: {json.dumps(cibil_json, indent=2)}
- Bank Statement: {json.dumps(bank_json, indent=2)}
- UPI Transactions: {json.dumps(upi_json, indent=2)}
- Salary Slip: {json.dumps(salary_json, indent=2)}

Calculate the following scores (each on a scale of 0-10) based ONLY on verified document data:
1. income_stability_score (from salary slip regularity, bank credits)
2. spending_discipline_score (from bank debits, UPI patterns)
3. savings_behavior_score (from bank balance, credits vs debits)
4. payment_discipline_score (from CIBIL late payments, bank overdrafts)
5. digital_behavior_score (from UPI transaction patterns)
6. lifestyle_stability_score (from transaction regularity, EMI patterns)

Then calculate a final behavior_score (0-10) as a weighted average:
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
  "explanation": "<3-4 bullet points explaining the verified score>",
  "key_insights": {{
    "positive": ["<what increased score>", "<another positive>"],
    "negative": ["<what reduced score>", "<another negative>"]
  }},
  "red_flags": ["<any concerning patterns>"],
  "improvement_tips": ["<tip 1>", "<tip 2>", "<tip 3>"]
}}
"""
    
    try:
        model = genai.GenerativeModel('gemini-2.5-flash')
        response = model.generate_content(prompt)
        response_text = response.text.strip()
        
        # Extract JSON from response
        json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
        if json_match:
            return json.loads(json_match.group())
        else:
            # Fallback scoring
            return {
                "income_stability_score": 7.0,
                "spending_discipline_score": 7.0,
                "savings_behavior_score": 7.0,
                "payment_discipline_score": 7.0,
                "digital_behavior_score": 7.0,
                "lifestyle_stability_score": 7.0,
                "behavior_score": 7.0,
                "explanation": "Based on verified documents, moderate financial behavior observed.",
                "key_insights": {"positive": [], "negative": []},
                "red_flags": [],
                "improvement_tips": ["Maintain consistent savings", "Pay bills on time", "Track expenses regularly"]
            }
    except Exception as e:
        # Fallback scoring
        return {
            "income_stability_score": 7.0,
            "spending_discipline_score": 7.0,
            "savings_behavior_score": 7.0,
            "payment_discipline_score": 7.0,
            "digital_behavior_score": 7.0,
            "lifestyle_stability_score": 7.0,
            "behavior_score": 7.0,
            "explanation": f"Error in AI analysis: {str(e)}. Using default scores.",
            "key_insights": {"positive": [], "negative": []},
            "red_flags": [],
            "improvement_tips": ["Maintain consistent savings", "Pay bills on time", "Track expenses regularly"]
        }

def calculate_loan_type_score(behavior_json, loan_type, cibil_score, salary_json=None):
    """Calculate loan-type-specific score and recommendation"""
    behavior_score = behavior_json.get('behavior_score', 7.0) if isinstance(behavior_json, dict) else 7.0
    hybrid_score = calculate_hybrid_score(cibil_score, behavior_score)
    
    # Loan-type-specific risk weights
    risk_weights = {
        'personal': {'cibil_weight': 0.5, 'behavior_weight': 0.5},
        'home': {'cibil_weight': 0.6, 'behavior_weight': 0.4},
        'education': {'cibil_weight': 0.4, 'behavior_weight': 0.6},
        'business': {'cibil_weight': 0.45, 'behavior_weight': 0.55},
        'vehicle': {'cibil_weight': 0.5, 'behavior_weight': 0.5},
        'gold': {'cibil_weight': 0.3, 'behavior_weight': 0.7},
        'other': {'cibil_weight': 0.5, 'behavior_weight': 0.5}
    }
    
    weights = risk_weights.get(loan_type, risk_weights['other'])
    adjusted_score = (cibil_score * weights['cibil_weight']) + ((behavior_score * 100) * weights['behavior_weight'])
    
    # EMI affordability (simplified calculation)
    # Assuming 30% of income can go to EMI
    salary = None
    if salary_json:
        salary = salary_json.get('gross_salary') or salary_json.get('net_salary')
    if salary:
        max_emi = salary * 0.3
    else:
        max_emi = None
    
    # Default risk prediction
    if adjusted_score >= 750:
        risk_level = "Low"
        recommendation = "Approve"
    elif adjusted_score >= 650:
        risk_level = "Medium"
        recommendation = "Approve with Caution"
    elif adjusted_score >= 550:
        risk_level = "Medium-High"
        recommendation = "Caution / Need more documents"
    else:
        risk_level = "High"
        recommendation = "Reject"
    
    return {
        'adjusted_score': adjusted_score,
        'hybrid_score': hybrid_score,
        'risk_level': risk_level,
        'recommendation': recommendation,
        'max_emi_affordability': max_emi,
        'loan_type': loan_type
    }

@app.route("/")
def index():
    """Home page"""
    return render_template("index.html")

@app.route("/signup", methods=["GET", "POST"])
def signup():
    """User/Lender registration"""
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")
        phone = request.form.get("phone", "").strip()
        role = request.form.get("role", "user")  # 'user' or 'lender'
        org_name = request.form.get("org_name", "").strip() if role == "lender" else None
        loan_types = request.form.getlist("loan_types") if role == "lender" else None

        if not username or not email or not password:
            flash("All fields are required.", "error")
            return redirect(url_for("signup"))
        
        if role == "user" and not phone:
            flash("Phone number is required for WhatsApp notifications.", "error")
            return redirect(url_for("signup"))

        if password != confirm_password:
            flash("Passwords do not match.", "error")
            return redirect(url_for("signup"))

        hashed = generate_password_hash(password)

        try:
            with get_db(app) as conn:
                if role == "lender":
                    unique_lender_id = generate_unique_lender_id()
                    # Ensure uniqueness
                    while True:
                        check_cur = conn.execute("SELECT id FROM lenders WHERE unique_lender_id = ?", (unique_lender_id,))
                        if check_cur.fetchone() is None:
                            break
                        unique_lender_id = generate_unique_lender_id()
                    
                    loan_types_json = json.dumps(loan_types) if loan_types else "[]"
                    conn.execute(
                        """INSERT INTO lenders (unique_lender_id, name, email, password_hash, org_name, loan_types_offered, role)
                           VALUES (?, ?, ?, ?, ?, ?, ?)""",
                        (unique_lender_id, username, email, hashed, org_name, loan_types_json, role),
                    )
                    flash(f"Lender account created! Your Lender ID: {unique_lender_id}", "success")
                else:
                    unique_user_id = generate_unique_user_id()
                    # Ensure uniqueness
                    while True:
                        check_cur = conn.execute("SELECT id FROM users WHERE unique_user_id = ?", (unique_user_id,))
                        if check_cur.fetchone() is None:
                            break
                        unique_user_id = generate_unique_user_id()
                    
                    # Check if unique_user_id column exists, if not, add it
                    cur = conn.execute("PRAGMA table_info(users)")
                    columns = [row[1] for row in cur.fetchall()]
                    if 'unique_user_id' not in columns:
                        conn.execute("ALTER TABLE users ADD COLUMN unique_user_id TEXT")
                    if 'phone' not in columns:
                        conn.execute("ALTER TABLE users ADD COLUMN phone TEXT")
                    
                    conn.execute(
                        """INSERT INTO users (unique_user_id, username, email, password_hash, role, phone)
                           VALUES (?, ?, ?, ?, ?, ?)""",
                        (unique_user_id, username, email, hashed, role, phone),
                    )
                    flash(f"Account created successfully! Your User ID: {unique_user_id}", "success")
            return redirect(url_for("signin"))
        except sqlite3.IntegrityError as e:
            flash("A user with that email already exists.", "error")
            return redirect(url_for("signup"))
        except sqlite3.OperationalError as e:
            # If column doesn't exist, try to add it and retry
            if "no column named unique_user_id" in str(e).lower():
                with get_db(app) as conn:
                    conn.execute("ALTER TABLE users ADD COLUMN unique_user_id TEXT")
                    # Retry the insert
                    unique_user_id = generate_unique_user_id()
                    while True:
                        check_cur = conn.execute("SELECT id FROM users WHERE unique_user_id = ?", (unique_user_id,))
                        if check_cur.fetchone() is None:
                            break
                        unique_user_id = generate_unique_user_id()
                    # Check if phone column exists
                    cur = conn.execute("PRAGMA table_info(users)")
                    columns = [row[1] for row in cur.fetchall()]
                    if 'phone' not in columns:
                        conn.execute("ALTER TABLE users ADD COLUMN phone TEXT")
                    
                    conn.execute(
                        """INSERT INTO users (unique_user_id, username, email, password_hash, role, phone)
                           VALUES (?, ?, ?, ?, ?, ?)""",
                        (unique_user_id, username, email, hashed, role, phone),
                    )
                    flash(f"Account created successfully! Your User ID: {unique_user_id}", "success")
                    return redirect(url_for("signin"))
            else:
                flash(f"Database error: {str(e)}", "error")
                return redirect(url_for("signup"))

    return render_template("signup.html", loan_types=LOAN_TYPES)

@app.route("/signin", methods=["GET", "POST"])
def signin():
    """User/Lender login"""
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        role = request.form.get("role", "user")  # 'user' or 'lender'

        with get_db(app) as conn:
            if role == "lender":
                cur = conn.execute(
                    "SELECT id, unique_lender_id, name, email, password_hash, org_name FROM lenders WHERE email = ?",
                    (email,),
                )
                user = cur.fetchone()
                if user and check_password_hash(user["password_hash"], password):
                    session["lender_id"] = user["id"]
                    session["unique_lender_id"] = user["unique_lender_id"]
                    session["username"] = user["name"]
                    session["role"] = "lender"
                    flash(f"Welcome back, {user['name']}!", "success")
                    return redirect(url_for("lender_dashboard"))
            else:
                cur = conn.execute(
                    "SELECT id, unique_user_id, username, email, password_hash FROM users WHERE email = ?",
                    (email,),
                )
                user = cur.fetchone()
                if user and check_password_hash(user["password_hash"], password):
                    session["user_id"] = user["id"]
                    session["unique_user_id"] = user["unique_user_id"]
                    session["username"] = user["username"]
                    session["role"] = "user"
                    flash(f"Welcome back, {user['username']}!", "success")
                    return redirect(url_for("dashboard"))

        flash("Invalid email or password.", "error")
        return redirect(url_for("signin"))

    return render_template("signin.html")

@app.route("/dashboard")
def dashboard():
    """User dashboard (protected)"""
    if "user_id" not in session or session.get("role") != "user":
        return redirect(url_for("signin"))
    
    with get_db(app) as conn:
        # Get unique user ID
        cur = conn.execute(
            "SELECT unique_user_id FROM users WHERE id = ?",
            (session["user_id"],)
        )
        user = cur.fetchone()
        unique_user_id = user["unique_user_id"] if user else None
        
        # Get latest quick score
        cur = conn.execute(
            "SELECT hybrid_score, behavior_json, created_at FROM quick_scores WHERE user_id = ? ORDER BY created_at DESC LIMIT 1",
            (session["user_id"],)
        )
        latest_quick_score = cur.fetchone()
        
        # Get latest verified score
        cur = conn.execute(
            "SELECT hybrid_score, behavior_json, cibil_json, bank_json, upi_json, salary_json, created_at FROM verified_scores WHERE user_id = ? ORDER BY created_at DESC LIMIT 1",
            (session["user_id"],)
        )
        latest_verified_score = cur.fetchone()
        
        # Get quick score history (last 6 months)
        cur = conn.execute(
            "SELECT hybrid_score, created_at FROM quick_scores WHERE user_id = ? ORDER BY created_at DESC LIMIT 6",
            (session["user_id"],)
        )
        quick_score_history = cur.fetchall()
        
        # Get loan requests
        cur = conn.execute(
            """SELECT lr.id, lr.loan_type, lr.status, lr.decision_json, lr.created_at, l.name as lender_name
               FROM loan_requests lr
               LEFT JOIN lenders l ON lr.lender_id = l.id
               WHERE lr.user_id = ? ORDER BY lr.created_at DESC""",
            (session["user_id"],)
        )
        loan_requests = cur.fetchall()
        
        # Get unread notifications
        cur = conn.execute(
            """SELECT n.id, n.notification_type, n.message, n.created_at, n.is_read, l.name as lender_name, l.org_name
               FROM notifications n
               LEFT JOIN lenders l ON n.lender_id = l.id
               WHERE n.user_id = ? ORDER BY n.created_at DESC LIMIT 10""",
            (session["user_id"],)
        )
        notifications = cur.fetchall()
        
        # Count unread notifications
        cur = conn.execute(
            "SELECT COUNT(*) as count FROM notifications WHERE user_id = ? AND is_read = 0",
            (session["user_id"],)
        )
        unread_result = cur.fetchone()
        unread_count = unread_result["count"] if unread_result else 0
        
        # Check and send monthly reminder if needed
        check_monthly_reminder(session["user_id"], conn)
    
    return render_template("dashboard.html", 
                         username=session.get("username"),
                         unique_user_id=unique_user_id,
                         latest_quick_score=latest_quick_score,
                         latest_verified_score=latest_verified_score,
                         quick_score_history=quick_score_history,
                         loan_requests=loan_requests,
                         notifications=notifications,
                         unread_count=unread_count,
                         loan_types=LOAN_TYPES)

@app.route("/check", methods=["GET", "POST"])
def check():
    """CIBIL input page"""
    if "user_id" not in session:
        return redirect(url_for("signin"))
    
    if request.method == "POST":
        cibil_score = request.form.get("cibil_score", "").strip()
        cibil_file = request.files.get("cibil_file")
        
        session["cibil_data"] = {}
        
        if cibil_file and allowed_file(cibil_file.filename):
            filename = secure_filename(cibil_file.filename)
            filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
            cibil_file.save(filepath)
            
            extracted = extract_cibil_from_pdf(filepath)
            if extracted.get("cibil_score"):
                session["cibil_data"] = extracted
                session["cibil_score"] = extracted["cibil_score"]
            else:
                flash("Could not extract CIBIL score from PDF. Please enter manually.", "error")
            
            # Delete file after parsing
            try:
                os.remove(filepath)
            except:
                pass
        elif cibil_score:
            try:
                score = int(cibil_score)
                if 300 <= score <= 900:
                    session["cibil_score"] = score
                    session["cibil_data"] = {"cibil_score": score}
                else:
                    flash("CIBIL score must be between 300 and 900.", "error")
                    return redirect(url_for("check"))
            except ValueError:
                flash("Invalid CIBIL score format.", "error")
                return redirect(url_for("check"))
        else:
            flash("Please enter CIBIL score or upload PDF.", "error")
            return redirect(url_for("check"))
        
        return redirect(url_for("behavior_form"))
    
    return render_template("check.html")

@app.route("/behavior-form", methods=["GET", "POST"])
def behavior_form():
    """Behavioral data form"""
    if "user_id" not in session:
        return redirect(url_for("signin"))
    
    if "cibil_score" not in session:
        flash("Please provide CIBIL score first.", "error")
        return redirect(url_for("check"))
    
    if request.method == "POST":
        # Collect all form data
        behavior_data = {
            "monthly_income": request.form.get("monthly_income", ""),
            "income_stability": request.form.get("income_stability", ""),
            "monthly_expenses": request.form.get("monthly_expenses", ""),
            "monthly_savings": request.form.get("monthly_savings", ""),
            "emergency_fund": request.form.get("emergency_fund", ""),
            "paid_bills_on_time": request.form.get("paid_bills_on_time", ""),
            "missed_payments": request.form.get("missed_payments", ""),
            "monthly_upi_transactions": request.form.get("monthly_upi_transactions", ""),
            "digital_vs_cash": request.form.get("digital_vs_cash", ""),
            "tracks_expenses": request.form.get("tracks_expenses", ""),
            "overspends_often": request.form.get("overspends_often", ""),
            "sudden_big_expenses": request.form.get("sudden_big_expenses", ""),
        }
        
        # Handle UPI file uploads
        upi_file = request.files.get("upi_file")
        upi_data = {}
        
        if upi_file and allowed_file(upi_file.filename):
            filename = secure_filename(upi_file.filename)
            filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
            upi_file.save(filepath)
            
            if filename.endswith('.csv'):
                upi_data = parse_upi_csv(filepath)
            elif filename.endswith('.pdf'):
                upi_data = parse_upi_pdf(filepath)
            
            # Delete file after parsing
            try:
                os.remove(filepath)
            except:
                pass
        
        behavior_data["upi_data"] = upi_data
        session["behavior_data"] = behavior_data
        
        return redirect(url_for("process_score"))
    
    return render_template("behavior_form.html")

@app.route("/process-score")
def process_score():
    """Process Quick Score with LLM"""
    if "user_id" not in session:
        return redirect(url_for("signin"))
    
    if "behavior_data" not in session:
        flash("Please complete the behavior form first.", "error")
        return redirect(url_for("behavior_form"))
    
    cibil_score = session.get("cibil_score")
    behavior_data = session.get("behavior_data", {})
    
    # Calculate behavioral score using LLM
    behavior_result = calculate_behavioral_score(behavior_data)
    behavior_score = behavior_result.get("behavior_score", 7.0)
    
    # Calculate hybrid score
    hybrid_score = calculate_hybrid_score(cibil_score, behavior_score)
    
    # Store in quick_scores table
    with get_db(app) as conn:
        conn.execute(
            """INSERT INTO quick_scores (user_id, behavior_json, hybrid_score)
               VALUES (?, ?, ?)""",
            (session["user_id"], json.dumps(behavior_result), hybrid_score)
        )
    
    # Store in session for result page
    session["result"] = {
        "cibil_score": cibil_score,
        "behavior_score": behavior_score,
        "hybrid_score": hybrid_score,
        "behavior_details": behavior_result,
        "score_type": "quick"
    }
    
    # Clear session data
    session.pop("cibil_score", None)
    session.pop("behavior_data", None)
    
    return redirect(url_for("result"))

@app.route("/result")
def result():
    """Result page"""
    if "user_id" not in session:
        return redirect(url_for("signin"))
    
    if "result" not in session:
        flash("No score data found. Please start from the beginning.", "error")
        return redirect(url_for("check"))
    
    result_data = session["result"]
    return render_template("result.html", result=result_data)

@app.route("/verified-score-upload", methods=["GET", "POST"])
def verified_score_upload():
    """Upload official documents for verified score"""
    if "user_id" not in session or session.get("role") != "user":
        return redirect(url_for("signin"))
    
    if request.method == "POST":
        files_uploaded = {}
        
        # Handle CIBIL PDF
        cibil_file = request.files.get("cibil_file")
        if cibil_file and allowed_file(cibil_file.filename):
            filename = secure_filename(cibil_file.filename)
            filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
            cibil_file.save(filepath)
            files_uploaded['cibil'] = filepath
        
        # Handle Bank Statement PDF
        bank_file = request.files.get("bank_file")
        if bank_file and allowed_file(bank_file.filename):
            filename = secure_filename(bank_file.filename)
            filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
            bank_file.save(filepath)
            files_uploaded['bank'] = filepath
        
        # Handle UPI CSV/PDF
        upi_file = request.files.get("upi_file")
        if upi_file and allowed_file(upi_file.filename):
            filename = secure_filename(upi_file.filename)
            filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
            upi_file.save(filepath)
            files_uploaded['upi'] = filepath
        
        # Handle Salary Slip PDF
        salary_file = request.files.get("salary_file")
        if salary_file and allowed_file(salary_file.filename):
            filename = secure_filename(salary_file.filename)
            filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
            salary_file.save(filepath)
            files_uploaded['salary'] = filepath
        
        if not files_uploaded:
            flash("Please upload at least one document.", "error")
            return redirect(url_for("verified_score_upload"))
        
        # Store file paths in session for processing
        session["verified_files"] = files_uploaded
        return redirect(url_for("process_verified_score"))
    
    return render_template("verified_score_upload.html")

@app.route("/process-verified-score")
def process_verified_score():
    """Process verified score from documents"""
    if "user_id" not in session or session.get("role") != "user":
        return redirect(url_for("signin"))
    
    if "verified_files" not in session:
        flash("Please upload documents first.", "error")
        return redirect(url_for("verified_score_upload"))
    
    files_uploaded = session["verified_files"]
    
    # Parse documents
    cibil_json = {}
    bank_json = {}
    upi_json = {}
    salary_json = {}
    
    if 'cibil' in files_uploaded:
        cibil_json = extract_cibil_from_pdf(files_uploaded['cibil'])
        try:
            os.remove(files_uploaded['cibil'])
        except:
            pass
    
    if 'bank' in files_uploaded:
        bank_json = parse_bank_statement(files_uploaded['bank'])
        try:
            os.remove(files_uploaded['bank'])
        except:
            pass
    
    if 'upi' in files_uploaded:
        if files_uploaded['upi'].endswith('.csv'):
            upi_json = parse_upi_csv(files_uploaded['upi'])
        else:
            upi_json = parse_upi_pdf(files_uploaded['upi'])
        try:
            os.remove(files_uploaded['upi'])
        except:
            pass
    
    if 'salary' in files_uploaded:
        salary_json = parse_salary_slip(files_uploaded['salary'])
        try:
            os.remove(files_uploaded['salary'])
        except:
            pass
    
    # Calculate document hash for caching
    doc_hash = calculate_doc_hash({
        'cibil': cibil_json,
        'bank': bank_json,
        'upi': upi_json,
        'salary': salary_json
    })
    
    # Check if verified score already exists for this doc_hash
    with get_db(app) as conn:
        cur = conn.execute(
            "SELECT * FROM verified_scores WHERE user_id = ? AND doc_hash = ?",
            (session["user_id"], doc_hash)
        )
        existing_score = cur.fetchone()
        
        if existing_score:
            # Use cached score
            behavior_json = json.loads(existing_score["behavior_json"])
            hybrid_score = existing_score["hybrid_score"]
            flash("Using cached verified score (documents unchanged).", "info")
        else:
            # Calculate new verified score using LLM
            behavior_result = calculate_verified_behavioral_score(
                cibil_json, bank_json, upi_json, salary_json
            )
            behavior_score = behavior_result.get("behavior_score", 7.0)
            cibil_score = cibil_json.get("cibil_score")
            hybrid_score = calculate_hybrid_score(cibil_score, behavior_score)
            
            # Store in verified_scores table
            conn.execute(
                """INSERT INTO verified_scores (user_id, cibil_json, bank_json, upi_json, salary_json, behavior_json, hybrid_score, doc_hash)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (session["user_id"], json.dumps(cibil_json), json.dumps(bank_json),
                 json.dumps(upi_json), json.dumps(salary_json), json.dumps(behavior_result),
                 hybrid_score, doc_hash)
            )
            behavior_json = behavior_result
    
    # Store in session for result page
    session["result"] = {
        "cibil_json": cibil_json,
        "bank_json": bank_json,
        "upi_json": upi_json,
        "salary_json": salary_json,
        "behavior_score": behavior_json.get("behavior_score", 7.0),
        "hybrid_score": hybrid_score,
        "behavior_details": behavior_json,
        "score_type": "verified"
    }
    
    # Clear session data
    session.pop("verified_files", None)
    
    return redirect(url_for("result"))

@app.route("/request-loan", methods=["POST"])
def request_loan():
    """User requests a loan"""
    if "user_id" not in session or session.get("role") != "user":
        return jsonify({"error": "Unauthorized"}), 401
    
    loan_type = request.form.get("loan_type")
    if not loan_type or loan_type not in LOAN_TYPES:
        flash("Invalid loan type.", "error")
        return redirect(url_for("dashboard"))
    
    with get_db(app) as conn:
        conn.execute(
            "INSERT INTO loan_requests (user_id, loan_type, status) VALUES (?, ?, ?)",
            (session["user_id"], loan_type, "pending")
        )
    
    flash(f"Loan request for {loan_type} loan submitted successfully!", "success")
    return redirect(url_for("dashboard"))

@app.route("/lender/dashboard")
def lender_dashboard():
    """Lender dashboard"""
    if "lender_id" not in session or session.get("role") != "lender":
        return redirect(url_for("signin"))
    
    with get_db(app) as conn:
        # Get lender info
        cur = conn.execute(
            "SELECT unique_lender_id, org_name, loan_types_offered FROM lenders WHERE id = ?",
            (session["lender_id"],)
        )
        lender = cur.fetchone()
        
        # Get pending loan requests
        cur = conn.execute(
            """SELECT lr.id, lr.user_id, lr.loan_type, lr.created_at, u.unique_user_id, u.username
               FROM loan_requests lr
               JOIN users u ON lr.user_id = u.id
               WHERE lr.status = 'pending' AND lr.lender_id IS NULL
               ORDER BY lr.created_at DESC LIMIT 20""",
        )
        pending_requests = cur.fetchall()
        
        # Get approved loans history (loans approved by this lender)
        cur = conn.execute(
            """SELECT lr.id, lr.user_id, lr.loan_type, lr.status, lr.decision_json, lr.created_at, 
                      u.unique_user_id, u.username
               FROM loan_requests lr
               JOIN users u ON lr.user_id = u.id
               WHERE lr.lender_id = ? AND lr.status = 'approved'
               ORDER BY lr.created_at DESC LIMIT 50""",
            (session["lender_id"],)
        )
        approved_loans_raw = cur.fetchall()
        
        # Parse decision_json for each loan
        approved_loans = []
        for loan in approved_loans_raw:
            loan_dict = dict(loan)
            if loan_dict["decision_json"]:
                try:
                    loan_dict["decision"] = json.loads(loan_dict["decision_json"])
                except:
                    loan_dict["decision"] = None
            else:
                loan_dict["decision"] = None
            approved_loans.append(loan_dict)
    
    loan_types_offered = json.loads(lender["loan_types_offered"]) if lender["loan_types_offered"] else []
    
    return render_template("lender_dashboard.html",
                         lender_id=lender["unique_lender_id"],
                         org_name=lender["org_name"],
                         loan_types_offered=loan_types_offered,
                         pending_requests=pending_requests,
                         approved_loans=approved_loans,
                         loan_types=LOAN_TYPES)

@app.route("/lender/search-user", methods=["GET", "POST"])
def lender_search_user():
    """Lender searches for user by unique ID"""
    if "lender_id" not in session or session.get("role") != "lender":
        return redirect(url_for("signin"))
    
    # Handle GET request with user_id parameter (from pending requests)
    if request.method == "GET":
        user_id = request.args.get("user_id")
        request_id = request.args.get("request_id")
        if user_id:
            unique_user_id = user_id.upper()
            loan_type = request.args.get("loan_type", "")
            
            with get_db(app) as conn:
                # Find user
                cur = conn.execute(
                    "SELECT id, username, unique_user_id FROM users WHERE unique_user_id = ?",
                    (unique_user_id,)
                )
                user = cur.fetchone()
                
                if not user:
                    flash("User not found.", "error")
                    return redirect(url_for("lender_search_user"))
                
            # Get verified score
            cur = conn.execute(
                "SELECT * FROM verified_scores WHERE user_id = ? ORDER BY created_at DESC LIMIT 1",
                (user["id"],)
            )
            verified_score = cur.fetchone()
            
            if not verified_score:
                # Send notification to user
                lender_name = session.get("username", "A lender")
                conn.execute(
                    """INSERT INTO notifications (user_id, lender_id, notification_type, message)
                       VALUES (?, ?, ?, ?)""",
                    (user["id"], session["lender_id"], "score_request",
                     f"{lender_name} tried to check your verified score, but you haven't generated one yet. Please upload your official documents to generate your verified score.")
                )
                conn.commit()
                
                # Send WhatsApp notification
                cur = conn.execute("SELECT phone FROM users WHERE id = ?", (user["id"],))
                user_phone = cur.fetchone()
                if user_phone and user_phone["phone"]:
                    cur = conn.execute("SELECT name, org_name FROM lenders WHERE id = ?", (session["lender_id"],))
                    lender_info = cur.fetchone()
                    lender_org = lender_info["org_name"] if lender_info and lender_info["org_name"] else lender_name
                    whatsapp_message = f"🔔 InsightScore Alert: {lender_org} tried to check your verified credit score, but you haven't generated one yet. Please upload your official documents (Bank statement, UPI transactions, CIBIL report) to generate your verified score. Visit your dashboard to upload documents now!"
                    send_whatsapp_message(user_phone["phone"], whatsapp_message)
                
                # Get lender info for display
                cur = conn.execute(
                    "SELECT name, org_name FROM lenders WHERE id = ?",
                    (session["lender_id"],)
                )
                lender_info = cur.fetchone()
                
                return render_template("lender_user_no_score.html",
                                     user=user,
                                     lender_info=lender_info,
                                     loan_type=loan_type,
                                     request_id=request_id,
                                     loan_types=LOAN_TYPES)
                
                # Get loan request if request_id provided
                loan_request = None
                if request_id:
                    cur = conn.execute(
                        "SELECT * FROM loan_requests WHERE id = ?",
                        (request_id,)
                    )
                    loan_request = cur.fetchone()
                    if loan_request:
                        loan_type = loan_request["loan_type"]
                
                # Parse verified score data
                cibil_json = json.loads(verified_score["cibil_json"]) if verified_score["cibil_json"] else {}
                bank_json = json.loads(verified_score["bank_json"]) if verified_score["bank_json"] else {}
                upi_json = json.loads(verified_score["upi_json"]) if verified_score["upi_json"] else {}
                salary_json = json.loads(verified_score["salary_json"]) if verified_score["salary_json"] else {}
                behavior_json = json.loads(verified_score["behavior_json"]) if verified_score["behavior_json"] else {}
                
                # Calculate loan-type-specific score
                loan_decision = None
                if loan_type:
                    loan_decision = calculate_loan_type_score(behavior_json, loan_type, cibil_json.get("cibil_score"), salary_json)
                
                return render_template("lender_user_score.html",
                                     user=user,
                                     verified_score=verified_score,
                                     cibil_json=cibil_json,
                                     bank_json=bank_json,
                                     upi_json=upi_json,
                                     salary_json=salary_json,
                                     behavior_json=behavior_json,
                                     loan_type=loan_type,
                                     loan_decision=loan_decision,
                                     loan_request=loan_request,
                                     loan_types=LOAN_TYPES)
    
    if request.method == "POST":
        unique_user_id = request.form.get("unique_user_id", "").strip().upper()
        
        if not unique_user_id:
            flash("Please enter a user ID.", "error")
            return redirect(url_for("lender_search_user"))
        
        with get_db(app) as conn:
            # Find user
            cur = conn.execute(
                "SELECT id, username, unique_user_id FROM users WHERE unique_user_id = ?",
                (unique_user_id,)
            )
            user = cur.fetchone()
            
            if not user:
                flash("User not found.", "error")
                return redirect(url_for("lender_search_user"))
            
            # Get user's pending loan request to show loan type
            cur = conn.execute(
                """SELECT loan_type, id FROM loan_requests 
                   WHERE user_id = ? AND status = 'pending' 
                   ORDER BY created_at DESC LIMIT 1""",
                (user["id"],)
            )
            loan_request = cur.fetchone()
            loan_type = loan_request["loan_type"] if loan_request else None
            request_id = loan_request["id"] if loan_request else None
            
            # Prepare user info for display
            user_info = {
                "id": user["id"],
                "username": user["username"],
                "unique_user_id": user["unique_user_id"],
                "loan_type": loan_type,
                "request_id": request_id
            }
            
            # Show user profile card first (with loan type if they have a pending request)
            return render_template("lender_search_user.html",
                                 loan_types=LOAN_TYPES,
                                 user_info=user_info)
    
    # Check if user_id is provided in GET request for display
    user_id = request.args.get("user_id")
    user_info = None
    
    if user_id:
        with get_db(app) as conn:
            cur = conn.execute(
                "SELECT id, username, unique_user_id FROM users WHERE unique_user_id = ?",
                (user_id.upper(),)
            )
            user = cur.fetchone()
            
            if user:
                # Get user's pending loan request to show loan type
                cur = conn.execute(
                    """SELECT loan_type, id FROM loan_requests 
                       WHERE user_id = ? AND status = 'pending' 
                       ORDER BY created_at DESC LIMIT 1""",
                    (user["id"],)
                )
                loan_request = cur.fetchone()
                
                user_info = {
                    "id": user["id"],
                    "username": user["username"],
                    "unique_user_id": user["unique_user_id"],
                    "loan_type": loan_request["loan_type"] if loan_request else None,
                    "request_id": loan_request["id"] if loan_request else None
                }
    
    return render_template("lender_search_user.html", 
                         loan_types=LOAN_TYPES,
                         user_info=user_info)

@app.route("/lender/edit-loan-types", methods=["GET", "POST"])
def lender_edit_loan_types():
    """Lender edits loan types they offer"""
    if "lender_id" not in session or session.get("role") != "lender":
        return redirect(url_for("signin"))
    
    if request.method == "POST":
        loan_types = request.form.getlist("loan_types")
        loan_types_json = json.dumps(loan_types) if loan_types else "[]"
        
        with get_db(app) as conn:
            conn.execute(
                "UPDATE lenders SET loan_types_offered = ? WHERE id = ?",
                (loan_types_json, session["lender_id"])
            )
            conn.commit()
        
        flash("Loan types updated successfully!", "success")
        return redirect(url_for("lender_dashboard"))
    
    # GET request - show edit form
    with get_db(app) as conn:
        cur = conn.execute(
            "SELECT loan_types_offered FROM lenders WHERE id = ?",
            (session["lender_id"],)
        )
        lender = cur.fetchone()
    
    current_loan_types = json.loads(lender["loan_types_offered"]) if lender["loan_types_offered"] else []
    
    return render_template("lender_edit_loan_types.html",
                         current_loan_types=current_loan_types,
                         all_loan_types=LOAN_TYPES)

@app.route("/lender/approve-loan/<int:request_id>", methods=["POST"])
def lender_approve_loan(request_id):
    """Lender approves a loan request"""
    if "lender_id" not in session or session.get("role") != "lender":
        return redirect(url_for("signin"))
    
    decision = request.form.get("decision")  # 'approve' or 'reject'
    notes = request.form.get("notes", "")
    
    decision_json = {
        "decision": decision,
        "notes": notes,
        "lender_id": session["lender_id"],
        "decided_at": datetime.now().isoformat()
    }
    
    status = "approved" if decision == "approve" else "rejected"
    
    with get_db(app) as conn:
        conn.execute(
            """UPDATE loan_requests SET lender_id = ?, status = ?, decision_json = ? WHERE id = ?""",
            (session["lender_id"], status, json.dumps(decision_json), request_id)
        )
        conn.commit()
    
    flash(f"Loan request {status} successfully!", "success")
    return redirect(url_for("lender_dashboard"))

@app.route("/notifications/mark-read/<int:notification_id>", methods=["POST"])
def mark_notification_read(notification_id):
    """Mark a notification as read"""
    if "user_id" not in session or session.get("role") != "user":
        return jsonify({"error": "Unauthorized"}), 401
    
    with get_db(app) as conn:
        conn.execute(
            "UPDATE notifications SET is_read = 1 WHERE id = ? AND user_id = ?",
            (notification_id, session["user_id"])
        )
        conn.commit()
    
    return jsonify({"success": True})

@app.route("/logout")
def logout():
    """User/Lender logout"""
    session.clear()
    flash("Signed out successfully.", "success")
    return redirect(url_for("signin"))

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug_mode = os.environ.get("SECRET_KEY") is None
    app.run(host="0.0.0.0", port=port, debug=debug_mode)
