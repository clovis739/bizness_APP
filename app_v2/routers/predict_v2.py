import json
from io import BytesIO
from fastapi import APIRouter, HTTPException, Request, BackgroundTasks, Depends, UploadFile, File
from fastapi.responses import StreamingResponse
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet

from app.database import supabase
from app.routers.dashboard import get_current_user
from app.routers.communication import send_html_email
from app.services.push_notifications import extract_push_token_values, send_expo_push_notifications
from app.services.forecast_math import calculate_growth_rate
from app.limiter import limiter
from app.redis_client import redis_db
from app_v2.schemas_v2 import PredictionRequestV2
from app_v2.services.ml_service_v2 import run_predictions
from app_v2.services.llm_service_v2 import generate_business_report, extract_ml_features_from_pdf

import os

# ============================================================
# BizNess OS — Predict Router V2
# Uses V3 models + Groq. Reads from business_profile_v2.
# Cache key uses _v2 suffix to avoid V1 cache collisions.
# ============================================================

router = APIRouter(
    prefix="/api/v2/predict",
    tags=["AI Predictions V2"]
)

FRONTEND_URL = os.getenv("FRONTEND_URL", "https://your-vercel-app-url.vercel.app")


@router.post("/generate")
@limiter.limit("3/minute")
def generate_prediction_v2(
    request: Request,
    payload: PredictionRequestV2,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user)
):
    """
    Core V2 prediction endpoint.
    1. Checks Redis cache (v2 key)
    2. Fetches real data from business_profile_v2 (all V3 fields)
    3. Runs V3 ML models (CatBoost calibrated + LightGBM + Cox PH)
    4. Calls Groq for advisory report
    5. Saves to survival_prediction + growth_forecast
    6. Caches for 24 hours
    7. Sends email + push notification (background)
    """
    try:
        # ── Cache check ──────────────────────────────────────────
        cache_key = f"business_report_{payload.business_id}_v2"
        if redis_db:
            try:
                cached = redis_db.get(cache_key)
                if cached:
                    print(f"⚡ CACHE HIT (V2): {payload.business_id}")
                    return json.loads(cached)
            except Exception as redis_err:
                print(f"⚠️ Redis read failed, continuing without cache: {redis_err}")

        print(f"🐢 CACHE MISS (V2). Generating report for: {payload.business_id}")

        # ── Security: verify ownership ───────────────────────────
        sme_id = current_user["sme_id"]
        owner_res = supabase.table("owner").select("owner_id").eq("sme_id", sme_id).execute()
        if not owner_res.data:
            raise HTTPException(status_code=403, detail="Access Denied: No owner profile found.")
        owner_id = owner_res.data[0]["owner_id"]

        biz_res = supabase.table("business").select("business_id", "industry").eq("owner_id", owner_id).eq("business_id", payload.business_id).execute()
        if not biz_res.data:
            raise HTTPException(status_code=403, detail="Access Denied: You do not own this business.")
        industry = biz_res.data[0]["industry"]

        # ── Fetch V2 profile (all V3 fields) ────────────────────
        profile_res = supabase.table("business_profile_v2").select("*").eq("business_id", payload.business_id).execute()
        if not profile_res.data:
            raise HTTPException(
                status_code=404,
                detail="No V2 business profile found. Please register via POST /api/v2/business/register first."
            )
        profile = profile_res.data[0]

        # ── Build ML input from real stored data ─────────────────
        ml_input = {
            "region":                    profile["region"],
            "sector":                    profile["sector"],
            "industry":                  industry,
            "startup_capital_cfa":       profile["startup_capital_cfa"],
            "employees":                 profile["employees"],
            "years_of_experience":       profile["years_of_experience"],
            "year_started":              profile["year_started"],
            "transport_cost_percentage": profile["transport_cost_percentage"],
            "energy_cost_percentage":    profile["energy_cost_percentage"],
            # V3 new fields — real values, no hardcoding
            "has_business_plan":         profile.get("has_business_plan", False),
            "formal_financial_records":  profile.get("formal_financial_records", False),
            "registered_formal":         profile.get("registered_formal", False),
            "owner_education_level":     profile.get("owner_education_level", "Secondary"),
            "competition_level":         profile.get("competition_level", "Medium"),
            "access_to_financing":       profile.get("access_to_financing", "No"),
            "financing_method":          profile.get("financing_method", "Own Resources"),
            "owner_hours_per_week":      profile.get("owner_hours_per_week", 40),
            "business_type":             profile.get("business_type", "Sole Proprietorship"),
        }

        # ── Run V3 ML models ─────────────────────────────────────
        print(f"🧠 Running V3 ML Analysis for: {payload.business_id}")
        ai_results = run_predictions(ml_input)

        # ── Generate Groq advisory report ────────────────────────
        ai_payload = generate_business_report(ml_input, ai_results)

        # ── Save to database ─────────────────────────────────────
        supabase.table("survival_prediction").insert({
            "business_id":        payload.business_id,
            "survival_probability": ai_results["survival_probability"],
            "risk_level":         ai_results["risk_level"],
        }).execute()

        growth_rate = calculate_growth_rate(
            ai_results["projected_profit_cfa"],
            ml_input["startup_capital_cfa"],
        )

        supabase.table("growth_forecast").insert({
            "business_id":          payload.business_id,
            "predicted_profit_cfa": ai_results["projected_profit_cfa"],
            "growth_rate":          growth_rate,
            "chart_data":           ai_payload.get("chart_data", {}),
            "full_report":          ai_payload,
        }).execute()

        # ── Build final response ─────────────────────────────────
        # Remove internal feature context from public response
        public_results = {k: v for k, v in ai_results.items() if k != "_feature_context"}

        final_response = {
            "status":  "Success",
            "message": "V2 AI Analysis & Consulting Report Complete!",
            "api_version": "v2",
            "data": {
                "predictions":    public_results,
                "advisory_report": ai_payload,
            }
        }

        # ── Cache for 24 hours ───────────────────────────────────
        if redis_db:
            try:
                redis_db.setex(cache_key, 86400, json.dumps(final_response))
            except Exception as redis_err:
                print(f"⚠️ Redis write failed (report still returned): {redis_err}")

        # ── Background: email + push notifications ───────────────
        user_prefs_res = supabase.table("sme").select("preferences").eq("sme_id", sme_id).execute()
        prefs_data = (user_prefs_res.data[0].get("preferences") or {}) if user_prefs_res.data else {}
        notifs = prefs_data.get("notifs", {})

        if notifs.get("prediction_complete", True):
            user_email = current_user["email"]
            user_name  = current_user.get("name", "Entrepreneur")
            survival_pct = round(ai_results["survival_probability"] * 100, 1)
            email_html = f"""
            <html>
                <body style="font-family:Arial,sans-serif;padding:20px;background:#f8f9fa;">
                    <div style="max-width:600px;margin:0 auto;background:#fff;padding:30px;border-radius:12px;border-top:5px solid #3B7FFF;">
                        <h2 style="color:#111827;">Your AI Prediction is Ready! 🚀</h2>
                        <p style="color:#4b5563;">Hello {user_name},</p>
                        <p style="color:#4b5563;">Your BizNess V3 AI analysis is complete.</p>
                        <p style="color:#4b5563;font-size:18px;font-weight:bold;">3-Year Survival Probability: {survival_pct}%</p>
                        <p style="color:#4b5563;">Risk Level: {ai_results['risk_level']}</p>
                        <a href="{FRONTEND_URL}/history"
                           style="display:inline-block;background:#3B7FFF;color:#fff;text-decoration:none;padding:12px 24px;border-radius:8px;font-weight:bold;margin-top:10px;">
                            View Full Report
                        </a>
                    </div>
                </body>
            </html>
            """
            background_tasks.add_task(
                send_html_email, user_email,
                "Your BizNess V2 AI Prediction is Ready!", email_html
            )

        if notifs.get("push_mobile", True):
            push_tokens = extract_push_token_values(prefs_data)
            if push_tokens:
                background_tasks.add_task(
                    send_expo_push_notifications,
                    push_tokens=push_tokens,
                    title="V2 Prediction complete",
                    body=f"Your BizNess V3 AI report is ready.",
                    data={"business_id": payload.business_id, "type": "prediction_complete_v2"},
                )

        return final_response

    except HTTPException:
        raise
    except Exception as e:
        print(f"🔥 V2 PREDICTION CRASH: {str(e)}")
        raise HTTPException(status_code=500, detail=f"V2 Prediction Error: {str(e)}")


@router.get("/history/{business_id}")
def get_prediction_history_v2(
    business_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Returns full prediction history for a business. Shared table with V1."""
    try:
        sme_id = current_user["sme_id"]
        owner_res = supabase.table("owner").select("owner_id").eq("sme_id", sme_id).execute()
        if not owner_res.data:
            raise HTTPException(status_code=403, detail="Access Denied.")
        owner_id = owner_res.data[0]["owner_id"]

        biz_res = supabase.table("business").select("business_id").eq("owner_id", owner_id).eq("business_id", business_id).execute()
        if not biz_res.data:
            raise HTTPException(status_code=403, detail="Access Denied: You do not own this business.")

        surv  = supabase.table("survival_prediction").select("*").eq("business_id", business_id).order("created_at", desc=True).execute()
        growth = supabase.table("growth_forecast").select("*").eq("business_id", business_id).order("created_at", desc=True).execute()

        return {
            "status": "Success",
            "data": {
                "business_id":    business_id,
                "survival_history": surv.data,
                "growth_history":   growth.data,
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"History Error: {str(e)}")


@router.post("/upload-pdf")
async def analyze_pdf_v2(
    business_id: str,
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user)
):
    """
    Upload a PDF business plan. Groq extracts V3 features,
    V3 models run prediction.
    """
    try:
        sme_id = current_user["sme_id"]
        owner_res = supabase.table("owner").select("owner_id").eq("sme_id", sme_id).execute()
        if not owner_res.data:
            raise HTTPException(status_code=403, detail="Access Denied.")

        biz_res = supabase.table("business").select("business_id").eq("owner_id", owner_res.data[0]["owner_id"]).eq("business_id", business_id).execute()
        if not biz_res.data:
            raise HTTPException(status_code=403, detail="Access Denied: You do not own this business.")

        if file.content_type != "application/pdf":
            raise HTTPException(status_code=400, detail="Invalid file type. Only PDF documents are accepted.")

        MAX_FILE_SIZE = 5 * 1024 * 1024
        pdf_bytes = await file.read(MAX_FILE_SIZE + 1)
        if len(pdf_bytes) > MAX_FILE_SIZE:
            raise HTTPException(status_code=413, detail="File exceeds the 5MB limit.")

        ml_input = extract_ml_features_from_pdf(pdf_bytes)
        if "error" in ml_input:
            raise HTTPException(status_code=500, detail="Failed to extract data from PDF.")

        ai_results  = run_predictions(ml_input)
        ai_payload  = generate_business_report(ml_input, ai_results)
        public_results = {k: v for k, v in ai_results.items() if k != "_feature_context"}

        return {
            "status":          "Success",
            "message":         "PDF analyzed successfully with V3 models!",
            "extracted_data":  ml_input,
            "predictions":     public_results,
            "advisory_report": ai_payload,
            "api_version":     "v2"
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PDF Analysis Error: {str(e)}")


@router.get("/download-report/{business_id}")
def download_report_v2(
    business_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Generates and streams the latest report as a PDF file."""
    try:
        sme_id = current_user["sme_id"]
        owner_res = supabase.table("owner").select("owner_id").eq("sme_id", sme_id).execute()
        if not owner_res.data:
            raise HTTPException(status_code=403, detail="Access Denied.")
        owner_id = owner_res.data[0]["owner_id"]

        biz_res = supabase.table("business").select("business_id").eq("owner_id", owner_id).eq("business_id", business_id).execute()
        if not biz_res.data:
            raise HTTPException(status_code=403, detail="Access Denied: You do not own this business.")

        res = supabase.table("growth_forecast").select("full_report").eq("business_id", business_id).order("created_at", desc=True).limit(1).execute()
        if not res.data or not res.data[0].get("full_report"):
            raise HTTPException(status_code=404, detail="No report found. Generate a prediction first.")

        report_data = res.data[0]["full_report"]
        buffer = BytesIO()
        doc    = SimpleDocTemplate(buffer, pagesize=letter)
        styles = getSampleStyleSheet()
        story  = []

        story.append(Paragraph("BizNess OS AI Advisory Report (V2)", styles["Title"]))
        story.append(Spacer(1, 20))

        sections = [
            ("Executive Summary",      report_data.get("executive_summary", "")),
            ("Prediction Explanation", report_data.get("prediction_explanation", "")),
            ("Optimal Business Model", report_data.get("optimal_business_model", "")),
            ("Cameroon Tax Breakdown", report_data.get("cameroon_tax_breakdown", "")),
        ]
        for title, text in sections:
            story.append(Paragraph(title, styles["Heading2"]))
            story.append(Paragraph(str(text), styles["Normal"]))
            story.append(Spacer(1, 12))

        story.append(Paragraph("Future Recommendations", styles["Heading2"]))
        for rec in report_data.get("future_recommendations", []):
            story.append(Paragraph(f"• {rec}", styles["Normal"]))
            story.append(Spacer(1, 6))

        doc.build(story)
        buffer.seek(0)

        return StreamingResponse(
            buffer,
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename=BizNess_V2_Report_{business_id}.pdf"}
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PDF Export Error: {str(e)}")
