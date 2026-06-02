


```markdown
# 🌍 BizSense OS: AI-Powered SME Consultant API 🇨🇲

[![Python 3.11](https://img.shields.io/badge/Python-3.11-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.109+-009688.svg)](https://fastapi.tiangolo.com)
[![Machine Learning](https://img.shields.io/badge/CatBoost%2FXGBoost-Predictive_AI-yellow.svg)]()
[![Google Gemini](https://img.shields.io/badge/Gemini_Pro-Generative_AI-orange.svg)]()
[![Supabase](https://img.shields.io/badge/Supabase-PostgreSQL-3ECF8E.svg)]()

## 📖 What is BizSense OS?
BizSense OS is a comprehensive, autonomous backend engine designed to solve the high failure rate of Small and Medium Enterprises (SMEs) in Cameroon. 

It takes raw business data (capital, region, overheads), processes it through **Machine Learning (CatBoost)** to predict survival probability and profit, and then feeds those mathematical results into **Google Gemini**. Gemini acts as an elite business consultant, generating localized, **MIT-Standard Business Plans** tailored specifically to the Cameroonian economic landscape (including exact local tax regimes like *l'Impôt Libératoire*).

---

## ⚡ System Architecture
1. **API Gateway:** FastAPI handles incoming requests.
2. **Security & Speed:** SlowAPI limits IP requests (100/min), and Upstash Redis caches generated reports for 24 hours (dropping response times from 15s to 0.01s).
3. **ML Prediction Engine:** Uses custom-trained CatBoost models to analyze risk and forecast 3-year profits in CFA Francs.
4. **LLM Advisory Engine:** Gemini Pro structures the data into a strict JSON MIT-Standard business plan.
5. **Data Persistence:** Everything is saved to a Supabase PostgreSQL database for historical tracking.

---

## ✨ Key Features

- 🧠 **Predictive Machine Learning:** Evaluates startup capital, energy/transport overheads, and regional data to accurately calculate a business's survival probability and projected profit.
- 🤖 **Autonomous AI Advisory:** Leverages Google Gemini to generate highly structured, localized business strategies, including exact Cameroonian tax regime classifications (e.g., *Régime de l'Impôt Libératoire*).
- ⚡ **Lightning-Fast Caching:** Integrated with **Upstash Redis**, reducing repeat-query latency from ~15 seconds to **0.01 seconds** while minimizing LLM API costs.
- 📄 **Smart PDF Processing:** Upload a raw PDF business plan, and the AI will automatically extract the core metrics needed to run the ML prediction models.
- 🛡️ **Enterprise Security:** Built-in IP rate limiting (SlowAPI) to protect against DDoS attacks and massive API billing spikes.
- 🚀 **Automated CI/CD Pipeline:** Fully configured GitHub Actions pipeline that lints syntax and securely triggers automated deployments to Render.com.

---

## 🚀 Base URL
**Live API Endpoint:** `https://bizness-app.onrender.com`

---

## 📚 API Reference

### 1. Generate AI Business Plan & Prediction
The core engine. Evaluates the business profile, runs ML models, and generates a structured advisory report.

- **URL:** `/api/v1/predict/generate`
- **Method:** `POST`
- **Rate Limit:** 100 requests per minute per IP.
- **Cache:** Responses are cached in Redis for 24 hours based on `business_id`.

**Request Body (`application/json`)**
```json
{
  "business_id": "uuid-or-string-1234",
  "industry": "Agriculture",
  "startup_capital_cfa": 1500000,
  "transport_cost_percentage": 15.5,
  "energy_cost_percentage": 12.0
}

```

**Response (`200 OK`)**

```json
{
  "status": "Success",
  "message": "AI Analysis & Consulting Report Complete!",
  "data": {
    "predictions": {
      "survival_probability": 0.2574,
      "risk_level": "High Risk of Failure",
      "projected_profit_cfa": 400458.06
    },
    "advisory_report": {
      "executive_summary": "A highly encouraging overview...",
      "prediction_explanation": "Explanation citing the 15.5% transport overhead...",
      "optimal_business_model": "Hybrid B2B-centric model for the North West region...",
      "cameroon_tax_breakdown": "Classified under Régime de l'Impôt Libératoire...",
      "future_recommendations": [
        "Optimize Transport & Logistics",
        "Invest in Energy Efficiency"
      ],
      "mit_business_plan": {
        "company_description": "...",
        "market_analysis": "...",
        "organization_management": "...",
        "service_product_line": "...",
        "marketing_sales_strategy": "...",
        "financial_projections": "..."
      },
      "chart_data": {
        "competitors": [
          {"type": "Informal Sellers", "threat_level": 85}
        ]
      }
    }
  }
}

```

**cURL Example**

```bash
curl -X POST "[https://bizness-app.onrender.com/api/v1/predict/generate](https://bizness-app.onrender.com/api/v1/predict/generate)" \
     -H "Content-Type: application/json" \
     -d '{"business_id": "test-001", "industry": "Agriculture", "startup_capital_cfa": 1500000, "transport_cost_percentage": 15.5, "energy_cost_percentage": 12.0}'

```

---

### 2. Fetch Prediction History

Retrieves all historical AI predictions and profit forecasts for a specific business.

* **URL:** `/api/v1/predict/history/{business_id}`
* **Method:** `GET`

**Response (`200 OK`)**

```json
{
  "status": "Success",
  "message": "Prediction history retrieved successfully!",
  "data": {
    "business_id": "test-001",
    "survival_history": [
      {
        "id": 1,
        "survival_probability": 0.2574,
        "risk_level": "High Risk",
        "created_at": "2024-03-09T12:00:00Z"
      }
    ],
    "growth_history": [
      {
        "id": 1,
        "predicted_profit_cfa": 400458.06,
        "full_report": { /* Full JSON Report */ },
        "created_at": "2024-03-09T12:00:00Z"
      }
    ]
  }
}

```

---

### 3. Upload & Analyze PDF Business Plan

Allows a user to upload a raw PDF document (like a rough draft business plan). The AI extracts the unstructured text, finds the ML parameters, and automatically runs the prediction engine.

* **URL:** `/api/v1/predict/upload-pdf?business_id={id}`
* **Method:** `POST`
* **Content-Type:** `multipart/form-data`

**Request Format**

* Form Data Field: `file` (Must be a `.pdf` file)

**Response (`200 OK`)**
*Returns the exact same comprehensive JSON structure as the `/generate` endpoint, plus an `extracted_data` block showing what it parsed from the PDF.*

---

### 4. Download Legacy PDF Report

Fetches the latest AI report for a business from the Supabase database and dynamically compiles a physical PDF file via `ReportLab` for banking/loan applications.

* **URL:** `/api/v1/predict/download-report/{business_id}`
* **Method:** `GET`
* **Response:** File Stream (`application/pdf`)

**cURL Example**

```bash
# This will download the file directly to your machine
curl -o BizSense_Report.pdf "[https://bizness-app.onrender.com/api/v1/predict/download-report/test-001](https://bizness-app.onrender.com/api/v1/predict/download-report/test-001)"

```

---

## 🛠️ Local Development & Setup

**1. Clone the repository**

```bash
git clone [https://github.com/YOUR_GITHUB_USERNAME/bizness-backend.git](https://github.com/YOUR_GITHUB_USERNAME/bizness-backend.git)
cd bizness-backend

```

**2. Virtual Environment & Dependencies**

```bash
python -m venv venv
# Activate on Windows: venv\Scripts\activate
pip install -r requirements.txt

```

**3. Environment Variables (`.env`)**
Create a `.env` file in the root directory:

```env
SUPABASE_URL=your_supabase_url
SUPABASE_KEY=your_supabase_key
GEMINI_API_KEY=your_google_gemini_key
REDIS_URL=rediss://your_upstash_redis_url:port

```

**4. Run the Server**

```bash
uvicorn main:app --reload

```

Interactive API Docs available at: `http://127.0.0.1:8000/docs`

---

## 🔒 CI/CD & Deployment

This project uses a rigorous **GitHub Actions Pipeline**.

1. Any push to `main` triggers a virtual Ubuntu environment.
2. Code is checked for fatal syntax errors using `flake8`.
3. If tests pass, a secure webhook is fired to Render.com for automatic deployment.

---

*Built to empower the next generation of Cameroonian entrepreneurs.* 🌍

```

***

### Why this is radically better:
1. **Copy-Paste Ready:** Any frontend developer can look at the `/generate` endpoint, see the exact JSON they need to send, and know exactly what JSON keys they will get back.
2. **Clear Explanations:** It explains the connection between the Machine Learning, the Gemini LLM, and the database beautifully.
3. **cURL Examples:** By providing terminal commands, developers can test your API without even opening up code.

Commit this to your GitHub right now. Let me know when you've pushed it, and we will finally jump into building the React UI dashboard!
uvicorn main:app --reload
***

### How to push this to GitHub right now:
1. Copy the markdown above into your `README.md` file and save it.
2. Run these commands in your terminal:
```bash
git add README.md
git commit -m "Added comprehensive project documentation"
git push

python -m venv venv
# Windows: venv\Scripts\activate
# Mac/Linux: source venv/bin/activate
```
<!-- Test command  python -n pytest -v -->







from fastapi import APIRouter, HTTPException, Response
from app.database import supabase
from app.schemas import SMERegistration, SMELogin, ForgotPassword, ResetPassword, GoogleToken, MagicLinkRequest, MagicLinkVerify
import bcrypt
import requests
from pydantic import BaseModel
import uuid
import random
from datetime import datetime, timedelta, timezone
from app.database import supabase, log_audit_action 
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
from dotenv import load_dotenv
from urllib.parse import urlencode


# Force Python to read the .env file
load_dotenv()

MOBILE_MAGIC_LINK_BASE_URL = os.getenv("MOBILE_MAGIC_LINK_BASE_URL", "biznessmobileapp://magic-link")


# Initialize the Router
router = APIRouter(
    prefix="/api/v1/auth",
    tags=["Authentication"]
)

# Helper function to encrypt passwords
def hash_password(password: str) -> str:
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')


# Helper function to send real HTML emails
def send_otp_email(receiver_email: str, otp_code: str):
    sender_email = os.getenv("SMTP_EMAIL")
    sender_password = os.getenv("SMTP_PASSWORD")

    # Fallback to console if you forgot to set your .env variables
    if not sender_email or not sender_password:
        print(f"\nWARNING: SMTP Credentials missing! Link: {magic_link}\n")
        return
        print(f"\n⚠️ WARNING: SMTP Credentials missing in .env! \nOTP for {receiver_email}: {otp_code}\n")
        return

    message = MIMEMultipart("alternative")
    message["Subject"] = "Your BizSense OS Password Reset Code"
    message["From"] = f"BizSense OS <{sender_email}>"
    message["To"] = receiver_email

    # Beautiful HTML Email Template matching your branding
    html = f"""
    <html>
      <body style="font-family: Arial, sans-serif; color: #333; background-color: #f8f9fa; padding: 20px;">
        <div style="max-w: 500px; margin: 0 auto; background-color: #ffffff; padding: 30px; border-radius: 15px; border: 1px solid #eaeaea;">
            <h2 style="color: #111827; margin-top: 0;">Password Reset Request</h2>
            <p style="color: #4b5563; line-height: 1.5;">You requested to reset your BizSense OS password. Please use the verification code below to securely access your account.</p>
            
            <div style="background-color: #f0f4ff; border: 1px solid #dde5fb; padding: 20px; text-align: center; border-radius: 10px; margin: 25px 0;">
                <h1 style="color: #476DDC; letter-spacing: 8px; margin: 0; font-size: 32px;">{otp_code}</h1>
            </div>
            
            <p style="color: #4b5563; font-size: 13px;">This code will expire in <strong>15 minutes</strong>.</p>
            <p style="color: #9ca3af; font-size: 12px; margin-top: 30px;">If you did not request this reset, please ignore this email or contact support.</p>
        </div>
      </body>
    </html>
    """
    
    part = MIMEText(html, "html")
    message.attach(part)

    try:
        # Connect to Gmail's secure SMTP server
        server = smtplib.SMTP_SSL("smtp.gmail.com", 465)
        server.login(sender_email, sender_password)
        server.sendmail(sender_email, receiver_email, message.as_string())
        server.quit()
    except Exception as e:
        print(f"🔥 SMTP ERROR: {e}")
        raise HTTPException(status_code=500, detail="Failed to send email. Please check server configuration.")

@router.post("/register")
def register_sme(user_data: SMERegistration):
    try:
        existing_user = supabase.table("sme").select("*").eq("email", user_data.email).execute()
        if len(existing_user.data) > 0:
            raise HTTPException(status_code=400, detail="An account with this email already exists.")

        secure_password = hash_password(user_data.password)
        new_sme = {"name": user_data.name, "email": user_data.email, "password_hash": secure_password}
        response = supabase.table("sme").insert(new_sme).execute()
        
        return {"status": "Success", "message": "SME Account Created!", "sme_id": response.data[0]['sme_id']}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/login")
def login_sme(credentials: SMELogin, response: Response):
    try:
        res = supabase.table("sme").select("*").eq("email", credentials.email).execute()
        if len(res.data) == 0:
            raise HTTPException(status_code=400, detail="Invalid email or password.")

        user = res.data[0]
        stored_hash = user['password_hash'].encode('utf-8')
        provided_password = credentials.password.encode('utf-8')

        if not bcrypt.checkpw(provided_password, stored_hash):
            raise HTTPException(status_code=400, detail="Invalid email or password.")

        # ==========================================
        # SET THE SECURE SESSION COOKIE
        # ==========================================
        response.set_cookie(
            key="bizness_session",
            value=user['sme_id'],
            httponly=True,   
            # Hides the cookie from frontend JavaScript (Huge security boost!)
            secure=False,    
            # Set to True in production when using HTTPS
            samesite="lax",
            max_age=86400    
            # Cookie expires in 1 day (60 * 60 * 24)
        )
        log_audit_action(
        actor_id=user['sme_id'],
        actor_type='SME',
        action_type='LOGIN_SUCCESS',
        description=f"{user['email']} successfully logged in."
    )

        return {"status": "Success", "message": f"Welcome back, {user['name']}!", "sme_id": user['sme_id']}
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    


@router.post("/forgot-password")
def forgot_password(request: ForgotPassword):
    try:
        user_res = supabase.table("sme").select("*").eq("email", request.email).execute()
        
        # Security Best Practice: Always return success even if email doesn't exist to prevent email scraping
        if len(user_res.data) == 0:
            return {"status": "Success", "message": "If the email exists, an OTP has been sent."}

        # Generate OTP and Expiry
        otp_code = str(random.randint(100000, 999999))
        expiry_time = datetime.now(timezone.utc) + timedelta(minutes=15)
        
        # Save to Supabase
        supabase.table("sme").update({
            "reset_otp": otp_code, 
            "otp_expiry": expiry_time.isoformat()
        }).eq("email", request.email).execute()

        # ==========================================
        # SEND THE ACTUAL EMAIL
        # ==========================================
        send_otp_email(request.email, otp_code)
        
        return {"status": "Success", "message": "OTP sent to your email!"}
        
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))




@router.post("/reset-password")
def reset_password(request: ResetPassword):
    try:
        user_res = supabase.table("sme").select("*").eq("email", request.email).execute()
        if len(user_res.data) == 0:
            raise HTTPException(status_code=400, detail="Invalid request.")
            
        user = user_res.data[0]
        if user.get("reset_otp") != request.otp:
            raise HTTPException(status_code=400, detail="Invalid OTP code.")
            
        expiry_str = user.get("otp_expiry")
        if not expiry_str:
            raise HTTPException(status_code=400, detail="No OTP requested.")
            
        clean_str = expiry_str.replace("Z", "+00:00")
        expiry_time = datetime.fromisoformat(clean_str)
        if expiry_time.tzinfo is None:
            expiry_time = expiry_time.replace(tzinfo=timezone.utc)
            
        if datetime.now(timezone.utc) > expiry_time:
            raise HTTPException(status_code=400, detail="OTP has expired.")

        secure_new_password = hash_password(request.new_password)
        supabase.table("sme").update({"password_hash": secure_new_password, "reset_otp": None, "otp_expiry": None}).eq("email", request.email).execute()

        return {"status": "Success", "message": "Password reset successfully!"}
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))



@router.post("/google")
def google_auth(token_data: GoogleToken, response: Response):
    try:
        # 1. Verify token with Google's official API
        google_response = requests.get(
            "https://www.googleapis.com/oauth2/v3/userinfo",
            headers={"Authorization": f"Bearer {token_data.access_token}"}
        )
        
        if google_response.status_code != 200:
            raise HTTPException(status_code=400, detail="Invalid Google token")
            
        user_info = google_response.json()
        email = user_info.get("email")
        name = user_info.get("name", "Google User")

        if not email:
            raise HTTPException(status_code=400, detail="Google account has no email")

        # 2. Check if user already exists in Supabase
        res = supabase.table("sme").select("*").eq("email", email).execute()
        
        if len(res.data) > 0:
            # User exists! Grab their ID
            sme_id = res.data[0]['sme_id']
        else:
            # 3. New User! Create an account automatically.
            # We generate a massive, random password hash since they use Google to log in
            dummy_password = hash_password(str(uuid.uuid4()) + "google_auth_bypass")
            new_sme = {
                "name": name, 
                "email": email, 
                "password_hash": dummy_password
            }
            insert_res = supabase.table("sme").insert(new_sme).execute()
            sme_id = insert_res.data[0]['sme_id']

        # 4. Set the exact same secure Session Cookie as standard login!
        response.set_cookie(
            key="bizness_session",
            value=sme_id,
            httponly=True,
            secure=False, # True in production
            samesite="lax",
            max_age=86400
        )
        
        log_audit_action(
            actor_id=sme_id,
            actor_type='SME',
            action_type='GOOGLE_LOGIN_SUCCESS',
            description=f"{email} logged in via Google."
        )

        return {"status": "Success", "message": "Google Login Successful", "sme_id": sme_id}

    except HTTPException as he:
        raise he
    except Exception as e:
        print(f"🔥 GOOGLE AUTH ERROR: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error during Google Auth") 








def send_magic_link_email(receiver_email: str, token: str):
    sender_email = os.getenv("SMTP_EMAIL")
    sender_password = os.getenv("SMTP_PASSWORD")
    query_string = urlencode({"email": receiver_email, "token": token})
    magic_link = f"{MOBILE_MAGIC_LINK_BASE_URL}?{query_string}"
    
    if not sender_email or not sender_password:
        print(f"\n⚠️ WARNING: SMTP Credentials missing! Link: http://localhost:3000/verify-link?email={receiver_email}&token={token}\n")
        return

    message = MIMEMultipart("alternative")
    message["Subject"] = "Sign in to BizSense OS"
    message["From"] = f"BizSense OS <{sender_email}>"
    message["To"] = receiver_email

    html = f"""
    <html>
      <body style="font-family: Arial, sans-serif; color: #333; background-color: #f8f9fa; padding: 20px;">
        <div style="max-w: 500px; margin: 0 auto; background-color: #ffffff; padding: 30px; border-radius: 15px; border: 1px solid #eaeaea; text-align: center;">
            <h2 style="color: #111827; margin-top: 0;">Your Magic Link</h2>
            <p style="color: #4b5563; line-height: 1.5; margin-bottom: 30px;">Click the secure button below to instantly sign in to your BizSense OS dashboard.</p>
            
            <a href="{magic_link}" style="background-color: #476DDC; color: #ffffff; padding: 14px 28px; text-decoration: none; border-radius: 10px; font-weight: bold; display: inline-block;">Sign In to BizSense</a>
            
            <p style="color: #9ca3af; font-size: 12px; margin-top: 40px;">This link expires in 15 minutes. If you did not request this, please ignore this email.</p>
        </div>
      </body>
    </html>
    """
    
    part = MIMEText(html, "html")
    message.attach(part)

    try:
        server = smtplib.SMTP_SSL("smtp.gmail.com", 465)
        server.login(sender_email, sender_password)
        server.sendmail(sender_email, receiver_email, message.as_string())
        server.quit()
    except Exception as e:
        print(f"🔥 SMTP ERROR: {e}")

@router.post("/magic-link/request")
def request_magic_link(request: MagicLinkRequest):
    try:
        # 1. Check if user exists. If not, create a skeleton account for them!
        res = supabase.table("sme").select("*").eq("email", request.email).execute()
        
        if len(res.data) == 0:
            dummy_password = hash_password(str(uuid.uuid4()) + "magic_link_dummy")
            new_sme = {"name": "New SME", "email": request.email, "password_hash": dummy_password}
            supabase.table("sme").insert(new_sme).execute()

        # 2. Generate a secure, 32-character token
        secure_token = uuid.uuid4().hex
        expiry_time = datetime.now(timezone.utc) + timedelta(minutes=15)

        # 3. Save it to the database (reusing our OTP columns to keep the DB clean!)
        supabase.table("sme").update({
            "reset_otp": secure_token, 
            "otp_expiry": expiry_time.isoformat()
        }).eq("email", request.email).execute()

        # 4. Send the email
        send_magic_link_email(request.email, secure_token)

        return {"status": "Success", "message": "Magic link sent to your email!"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/magic-link/verify")
def verify_magic_link(request: MagicLinkVerify, response: Response):
    try:
        res = supabase.table("sme").select("*").eq("email", request.email).execute()
        if len(res.data) == 0:
            raise HTTPException(status_code=400, detail="Invalid request.")
            
        user = res.data[0]
        
        # Check Token Match
        if user.get("reset_otp") != request.token:
            raise HTTPException(status_code=400, detail="Invalid or expired magic link.")
            
        # Check Expiry
        expiry_str = user.get("otp_expiry")
        if not expiry_str:
            raise HTTPException(status_code=400, detail="No magic link requested.")
            
        clean_str = expiry_str.replace("Z", "+00:00")
        expiry_time = datetime.fromisoformat(clean_str)
        if expiry_time.tzinfo is None:
            expiry_time = expiry_time.replace(tzinfo=timezone.utc)
            
        if datetime.now(timezone.utc) > expiry_time:
            raise HTTPException(status_code=400, detail="Magic link has expired.")

        # CLEAR the token so it can't be used twice
        supabase.table("sme").update({"reset_otp": None, "otp_expiry": None}).eq("email", request.email).execute()

        # SET THE SECURE LOGIN COOKIE
        response.set_cookie(
            key="bizness_session",
            value=user['sme_id'],
            httponly=True,
            secure=False,
            samesite="lax",
            max_age=86400
        )

        return {"status": "Success", "message": "Successfully logged in!", "sme_id": user['sme_id']}
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))




@router.post("/logout")
def logout_sme(response: Response):
    """Destroys the secure HttpOnly cookie to log the user out."""
    response.delete_cookie(
        key="bizness_session",
        httponly=True,
        secure=False,
        samesite="lax"
    )
    return {"status": "Success", "message": "Logged out successfully"}




    
python -m uvicorn main:app --reload
