


```markdown
# 🌍 BizNess OS: AI-Powered SME Consultant API 🇨🇲

[![Python 3.11](https://img.shields.io/badge/Python-3.11-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.109+-009688.svg)](https://fastapi.tiangolo.com)
[![Machine Learning](https://img.shields.io/badge/CatBoost%2FXGBoost-Predictive_AI-yellow.svg)]()
[![Google Gemini](https://img.shields.io/badge/Gemini_Pro-Generative_AI-orange.svg)]()
[![Supabase](https://img.shields.io/badge/Supabase-PostgreSQL-3ECF8E.svg)]()

## 📖 What is BizNess OS?
BizNess OS is a comprehensive, autonomous backend engine designed to solve the high failure rate of Small and Medium Enterprises (SMEs) in Cameroon. 

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
curl -o BizNess_Report.pdf "[https://bizness-app.onrender.com/api/v1/predict/download-report/test-001](https://bizness-app.onrender.com/api/v1/predict/download-report/test-001)"

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
