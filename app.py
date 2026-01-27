from pathlib import Path
import os
import sqlite3
import json
import re
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

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "auth.db"
UPLOAD_FOLDER = BASE_DIR / "uploads"
UPLOAD_FOLDER.mkdir(exist_ok=True)

# Gemini API Key
GEMINI_API_KEY = "AIzaSyCrFYdJIoSYyyqH1McZ1S8V_wa9qL-TJu4"
genai.configure(api_key=GEMINI_API_KEY)

ALLOWED_EXTENSIONS = {'pdf', 'csv'}

def get_db(app: Flask) -> sqlite3.Connection:
    conn = sqlite3.connect(app.config["DATABASE"])
    conn.row_factory = sqlite3.Row
    return conn

def init_db(app: Flask) -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with get_db(app) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
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

@app.route("/")
def index():
    """Home page"""
    return render_template("index.html")

@app.route("/signup", methods=["GET", "POST"])
def signup():
    """User registration"""
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not username or not email or not password:
            flash("All fields are required.", "error")
            return redirect(url_for("signup"))

        if password != confirm_password:
            flash("Passwords do not match.", "error")
            return redirect(url_for("signup"))

        hashed = generate_password_hash(password)

        try:
            with get_db(app) as conn:
                conn.execute(
                    "INSERT INTO users (username, email, password_hash) VALUES (?, ?, ?)",
                    (username, email, hashed),
                )
            flash("Account created successfully. Please sign in.", "success")
            return redirect(url_for("signin"))
        except sqlite3.IntegrityError:
            flash("A user with that email already exists.", "error")
            return redirect(url_for("signup"))

    return render_template("signup.html")

@app.route("/signin", methods=["GET", "POST"])
def signin():
    """User login"""
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        with get_db(app) as conn:
            cur = conn.execute(
                "SELECT id, username, email, password_hash FROM users WHERE email = ?",
                (email,),
            )
            user = cur.fetchone()

        if not user or not check_password_hash(user["password_hash"], password):
            flash("Invalid email or password.", "error")
            return redirect(url_for("signin"))

        session["user_id"] = user["id"]
        session["username"] = user["username"]
        flash(f"Welcome back, {user['username']}!", "success")
        return redirect(url_for("dashboard"))

    return render_template("signin.html")

@app.route("/dashboard")
def dashboard():
    """User dashboard (protected)"""
    if "user_id" not in session:
        return redirect(url_for("signin"))
    
    # Get latest score if exists
    with get_db(app) as conn:
        cur = conn.execute(
            "SELECT hybrid_score, created_at FROM scores WHERE user_id = ? ORDER BY created_at DESC LIMIT 1",
            (session["user_id"],)
        )
        latest_score = cur.fetchone()
    
    return render_template("dashboard.html", 
                         username=session.get("username"),
                         latest_score=latest_score)

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
    """Process score with LLM"""
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
    
    # Store in database
    with get_db(app) as conn:
        conn.execute(
            """INSERT INTO scores (user_id, cibil_score, behavior_score, hybrid_score, behavior_details)
               VALUES (?, ?, ?, ?, ?)""",
            (session["user_id"], cibil_score, behavior_score, hybrid_score, 
             json.dumps(behavior_result))
        )
    
    # Store in session for result page
    session["result"] = {
        "cibil_score": cibil_score,
        "behavior_score": behavior_score,
        "hybrid_score": hybrid_score,
        "behavior_details": behavior_result
    }
    
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

@app.route("/logout")
def logout():
    """User logout"""
    session.clear()
    flash("Signed out successfully.", "success")
    return redirect(url_for("signin"))

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug_mode = os.environ.get("SECRET_KEY") is None
    app.run(host="0.0.0.0", port=port, debug=debug_mode)
