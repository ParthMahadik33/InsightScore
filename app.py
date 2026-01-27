from pathlib import Path
import os
import sqlite3

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    session,
)
from werkzeug.security import generate_password_hash, check_password_hash


BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "auth.db"


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
        conn.commit()


# Initialize Flask app
app = Flask(__name__)

# Use environment variables in production, with safe fallbacks for local dev
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "change-this-secret-key")
app.config["DATABASE"] = str(DB_PATH)

# Initialize database
init_db(app)


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
    return render_template("dashboard.html", username=session.get("username"))


@app.route("/logout")
def logout():
    """User logout"""
    session.clear()
    flash("Signed out successfully.", "success")
    return redirect(url_for("signin"))


if __name__ == "__main__":
    # Respect PORT env var (Render sets this), default to 5000 for local dev
    port = int(os.environ.get("PORT", 5000))
    # Disable debug mode in production (when SECRET_KEY is set via env var)
    debug_mode = os.environ.get("SECRET_KEY") is None
    app.run(host="0.0.0.0", port=port, debug=debug_mode)
