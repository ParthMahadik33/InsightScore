# InsightScore v3 - Hybrid Credit Scoring System

A FinTech web application that combines traditional CIBIL scores with AI-powered behavioral analysis to provide a comprehensive hybrid credit score.

## Features

- **CIBIL Score Integration**: Manual entry or PDF upload with automatic extraction
- **Behavioral Analysis**: Comprehensive form capturing financial behavior patterns
- **UPI Transaction Analysis**: Parse CSV/PDF statements from Google Pay, PhonePe, Paytm
- **AI-Powered Scoring**: Uses Google Gemini LLM to analyze behavioral patterns
- **Hybrid Score Calculation**: Combines CIBIL (40%) + Behavioral (60%)
- **Visual Analytics**: Interactive radar charts and score breakdowns
- **Score History**: Track improvements over time

## Tech Stack

- **Backend**: Flask (Python)
- **Database**: SQLite
- **AI/LLM**: Google Gemini API
- **PDF Parsing**: pdfplumber
- **CSV Processing**: pandas
- **Charts**: Chart.js

## Installation

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Set up environment (optional):
```bash
export SECRET_KEY="your-secret-key-here"
export PORT=5000
```

3. Run the application:
```bash
python app.py
```

4. Access the app at `http://localhost:5000`

## Usage Flow

1. **Sign Up / Sign In**: Create an account or log in
2. **Enter CIBIL Score**: 
   - Option A: Manual entry (300-900)
   - Option B: Upload CIBIL credit report PDF
3. **Complete Behavior Form**:
   - Income & expenses
   - Savings patterns
   - Bill payment discipline
   - UPI transaction data (optional CSV/PDF upload)
   - Lifestyle questions
4. **View Results**: 
   - Hybrid score breakdown
   - Behavioral sub-scores (radar chart)
   - Key insights and improvement tips

## File Uploads

- **CIBIL PDF**: Credit report from CIBIL
- **UPI CSV**: Transaction export from Google Pay/PhonePe/Paytm
- **UPI PDF**: Statement PDF from payment apps

Files are automatically deleted after parsing for security.

## API Endpoints

- `GET /` - Home page
- `GET /signup` - Registration page
- `POST /signup` - Create account
- `GET /signin` - Login page
- `POST /signin` - Authenticate user
- `GET /dashboard` - User dashboard
- `GET /check` - CIBIL input page
- `POST /check` - Submit CIBIL data
- `GET /behavior-form` - Behavioral data form
- `POST /behavior-form` - Submit behavioral data
- `GET /process-score` - Process score with LLM
- `GET /result` - Display results
- `GET /logout` - Sign out

## Database Schema

### users
- id, username, email, password_hash, created_at

### scores
- id, user_id, cibil_score, behavior_score, hybrid_score, behavior_details, created_at

## Security Notes

- Files are deleted immediately after parsing
- Passwords are hashed using Werkzeug
- Session-based authentication
- No long-term file storage

## Gemini API

The app uses Google Gemini API for behavioral analysis. The API key is configured in `app.py`. For production, move this to environment variables.

## License

MIT

