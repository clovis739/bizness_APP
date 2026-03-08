


---

#  BizNess SME Analytics Engine (Backend)

An enterprise-grade, AI-powered backend designed to analyze, predict, and advise Small and Medium Enterprises (SMEs) in Cameroon.

By combining traditional Machine Learning (CatBoost/XGBoost) with cutting-edge Large Language Models (Google Gemini), this API calculates an SME's survival probability and generates a customized, localized advisory report including tax compliance, market trends, and actionable business strategies.

## 🛠️ Tech Stack & Architecture

* **Core Framework:** FastAPI (Python 3.14+)
* **Database:** PostgreSQL (Hosted on Supabase)
* **Machine Learning:** CatBoost, XGBoost, Scikit-Learn
* **Generative AI:** Google Gemini (via `google-generativeai` SDK)
* **Task Scheduling:** APScheduler (for daily automated cron jobs)
* **Monitoring & Error Tracking:** Sentry SDK
* **Testing:** Pytest & HTTPX
* **Security:** HttpOnly Session Cookies, Bcrypt Password Hashing, CORS Middleware

---

## 🧠 Core Features & Modules

### 1. Authentication & Security (`app/routers/auth.py`)

* Secure SME registration and login.
* Passwords hashed via `bcrypt`.
* **HttpOnly Session Cookies:** Protects user sessions from Cross-Site Scripting (XSS) attacks.
* **Google OAuth:** Generates SSO login URLs integrated with Supabase.

### 2. Business Profiling (`app/routers/business.py`)

* Links business owners to specific company profiles.
* Captures dynamic features required for ML inference: Region, Industry, Sector, Startup Capital (CFA), Transport Overhead (%), and Energy Overhead (%).

### 3. Machine Learning Engine (`app/services/ml_service.py`)

* In-memory loading of serialized `.pkl` models to ensure sub-second inference times.
* Calculates **Survival Probability** (Next 3 Years) based on a strict 60% risk threshold.
* Calculates **Projected Annual Profit** (CFA Francs).

### 4. AI CFO & Advisory Service (`app/services/llm_service.py`)

* Feeds ML predictions into Google Gemini to reason through the data.
* Enforces a strict JSON schema output for seamless Next.js frontend integration.
* **Outputs include:** Executive Summary, Cameroonian Tax Regime Classification (e.g., Impôt Libératoire vs. Simplified Regime), Strategic Recommendations, and structured Chart Data (Target Audience, Market Trends, Competitor Threat Levels).

### 5. Communication & Engagement (`app/routers/communication.py`)

* Integrated SMTP email service.
* Contact forms routed directly to the Admin Support email.
* Newsletter subscription system.
* **Daily Cron Jobs:** `APScheduler` automatically emails daily business insights to all subscribers at 8:00 AM.

### 6. Health & Monitoring

* **Sentry Integration:** 24/7 performance profiling and error tracking.
* **Health Check (`/health`):** Endpoint to monitor API, Database, and ML model pulse.
* **Audit Logging:** Database utility to track system events and administrative actions.

---

## 📂 Project Structure

```text
bizness-backend/
│
├── app/
│   ├── database.py          # Supabase connection & Audit Logger
│   ├── schemas.py           # Pydantic data validation models
│   ├── routers/             # API Endpoints
│   │   ├── auth.py          # User login, registration, cookies
│   │   ├── business.py      # SME profile management
│   │   ├── predict.py       # ML & LLM generation and history
│   │   └── communication.py # Emails, Contact, Google SSO
│   │
│   ├── services/            # Core Business Logic
│   │   ├── ml_service.py    # Loads .pkl models & runs math
│   │   └── llm_service.py   # Prompts Google Gemini for JSON reports
│   │
│   └── models/              # Saved Machine Learning weights
│       ├── v1/              # Current production models
│       │   ├── survival_model.pkl
│       │   └── profit_model.pkl
│
├── tests/                   # Pytest automated testing suite
│   ├── __init__.py
│   ├── test_main.py         # Tests server health & API routes
│   └── test_ml_models.py    # Mathematically verifies ML outputs
│
├── main.py                  # FastAPI Application Entry Point (Lifespan manager)
├── requirements.txt         # Python dependencies
└── .env                     # Environment variables (Ignored by Git)

```

---

## ⚙️ Local Setup & Installation

**1. Clone the repository and navigate to the directory:**

```bash
git clone <your-repo-url>
cd bizness-backend

```

**2. Activate the Virtual Environment:**

```bash
# Windows
python -m venv venv
venv\Scripts\activate

# Mac/Linux
python3 -m venv venv
source venv/bin/activate

```

**3. Install Dependencies:**
*(Note: Ensure you are using `scikit-learn==1.7.2` to prevent pickle version drift!)*

```bash
pip install -r requirements.txt

```

**4. Configure Environment Variables (`.env`):**
Create a `.env` file in the root directory and add the following:

```env
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-service-role-key
GEMINI_API_KEY=your-google-gemini-key
SMTP_EMAIL=your-sender-email@gmail.com
SMTP_PASSWORD=your-16-char-app-password
ADMIN_EMAIL=your-support-inbox@gmail.com

```

**5. Start the Server:**

```bash
uvicorn main:app --reload

```

* The API will be available at: `http://127.0.0.1:8000`
* Swagger UI Documentation: `http://127.0.0.1:8000/docs`

---

## 🧪 Testing

This project uses `pytest` for automated mathematical and API verification.

Run all tests:

```bash
python -m pytest -v

```

---

## 📝 TODO & Future Roadmap

### Phase 1: Frontend Implementation (Current)

* [ ] Initialize Next.js (App Router, Tailwind, TypeScript).
* [ ] Build the User Authentication flow (Login/Register/Google SSO).
* [ ] Build the dynamic Business Profile input form.
* [ ] Create the Entrepreneur Dashboard using `Recharts` or `Chart.js` to map the `chart_data` JSON generated by Gemini.
* [ ] Build the "Tax & Legal" compliance UI card based on Gemini's localized output.

### Phase 2: System Administration Portal

* [ ] Build the Next.js Admin Dashboard.
* [ ] Create UI to view the `audit_log` database table.
* [ ] Create UI to manage and moderate SME user accounts.

### Phase 3: MLOps & Continuous Learning

* [ ] Implement an automated pipeline to pull live user data from Supabase.
* [ ] Retrain CatBoost/XGBoost models using the new real-world data.
* [ ] Create an Admin endpoint to "Hot-Swap" models (Upload `v2.pkl` to replace `v1.pkl` without server downtime).

---

