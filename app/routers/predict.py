import json
from io import BytesIO
from fastapi.responses import StreamingResponse
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet 
from fastapi import UploadFile, File 
from fastapi import APIRouter, HTTPException, Request, BackgroundTasks, Depends
from app.database import supabase
from app.schemas import PredictionRequest
from app.services.ml_service import run_predictions
from app.services.llm_service import generate_business_report 
from app.services.llm_service import extract_ml_features_from_pdf
from app.services.forecast_math import calculate_growth_rate
from app.services.push_notifications import extract_push_token_values, send_expo_push_notifications
from app.limiter import limiter 
from app.redis_client import redis_db 
from app.routers.communication import send_html_email
from app.routers.dashboard import get_current_user # Our secure cookie bouncer!

router = APIRouter(
    prefix="/api/v1/predict",
    tags=["AI Predictions"]
)

# ==========================================
# PROTECTED AI GENERATION ENDPOINT WITH CACHING
# ==========================================
@router.post("/generate")
@limiter.limit("1/minute") 
# 🛡️ LIMITER: Adjust this to "5/day" for production
def generate_prediction(
    request: Request, 
    payload: PredictionRequest,                    # <-- FIXED: Added missing comma
    background_tasks: BackgroundTasks,             
    current_user: dict = Depends(get_current_user) 
):
    """
    Checks the Redis cache first. If no cache exists, runs the ML & Gemini models,
    saves the result to the database, and caches the response for 24 hours.
    """
    try:
        # ==========================================
        # ⚡ THE CACHE CHECK (SPEED BOOST)
        # ==========================================
        cache_key = f"business_report_{payload.business_id}_v1"
        
        if redis_db:
            cached_result = redis_db.get(cache_key)
            if cached_result:
                print(f"⚡ CACHE HIT! Returning instant report for: {payload.business_id}")
                return json.loads(cached_result) # Return instantly without running ML/AI!
                
        print(f"🐢 CACHE MISS. Generating new AI report for: {payload.business_id}")

        # Step A: Fetch the Business Profile from Supabase
        profile_res = supabase.table("business_profile").select("*").eq("business_id", payload.business_id).execute()
        if len(profile_res.data) == 0:
            raise HTTPException(status_code=404, detail="Business profile not found.")
        profile_data = profile_res.data[0]

        # Step B: Fetch the main Business details
        biz_res = supabase.table("business").select("industry").eq("business_id", payload.business_id).execute()
        if len(biz_res.data) == 0:
            raise HTTPException(status_code=404, detail="Business not found.")
        industry = biz_res.data[0]['industry']

        # Step C: Merge the data for the Machine Learning model
        ml_input = {
            "region": profile_data["region"],
            "sector": profile_data["sector"],
            "industry": industry,
            "startup_capital_cfa": profile_data["startup_capital_cfa"],
            "employees": profile_data["employees"],
            "years_of_experience": profile_data["years_of_experience"],
            "transport_cost_percentage": profile_data["transport_cost_percentage"],
            "energy_cost_percentage": profile_data["energy_cost_percentage"]
        }

        # Step D: Run the Machine Learning Models (CatBoost & XGBoost)
        print(f"🧠 Running ML Analysis for Business ID: {payload.business_id}")
        ai_results = run_predictions(ml_input)

        # Step E: Ask Gemini to generate the Structured JSON Advisory Report
        ai_payload = generate_business_report(ml_input, ai_results)

        # Step F: Save the results to the Supabase Database
        surv_insert = { 
            "business_id": payload.business_id,
            "survival_probability": ai_results["survival_probability"],
            "risk_level": ai_results["risk_level"]
        }
        supabase.table("survival_prediction").insert(surv_insert).execute()

        # Calculate growth rate: profit as a % of startup capital (simple ROI).
        # Clamp to the database column range: growth_forecast.growth_rate is numeric(5,2).
        growth_rate = calculate_growth_rate(
            ai_results["projected_profit_cfa"],
            ml_input["startup_capital_cfa"],
        )

        growth_insert = {
            "business_id": payload.business_id,
            "predicted_profit_cfa": ai_results["projected_profit_cfa"],
            "growth_rate": growth_rate,
            "chart_data": ai_payload.get("chart_data", {}),
            "full_report": ai_payload 
        }
        # FIXED: Removed the duplicate insert command that was here
        supabase.table("growth_forecast").insert(growth_insert).execute()

        # Step G: Prepare the final comprehensive response
        final_response = {
            "status": "Success",
            "message": "AI Analysis & Consulting Report Complete!",
            "data": {
                "predictions": ai_results,
                "advisory_report": ai_payload 
            }
        }

        # ==========================================
        # 💾 SAVE TO CACHE FOR NEXT TIME
        # ==========================================
        if redis_db:
            redis_db.setex(
                name=cache_key, 
                time=86400, 
                value=json.dumps(final_response) 
            )

        # ==========================================
        # 📩 NOTIFICATION SYSTEM: CHECK PREFERENCES & SEND
        # ==========================================
        # 1. Fetch preferences from the user's account
        user_prefs_res = supabase.table("sme").select("preferences").eq("sme_id", current_user["sme_id"]).execute()
        prefs_data = user_prefs_res.data[0].get("preferences") or {}
        notifs = prefs_data.get("notifs", {})

        # 2. Only send the email if they didn't toggle it off!
        if notifs.get("prediction_complete", True) == True:
            user_email = current_user["email"]
            user_name = current_user["name"]
            
            # The beautifully branded HTML email
            email_html = f"""
            <html>
                <body style="font-family: Arial, sans-serif; padding: 20px; background: #f8f9fa;">
                    <div style="max-w: 600px; margin: 0 auto; background: white; padding: 30px; border-radius: 12px; border-top: 5px solid #476DDC;">
                        <h2 style="color: #111827;">Your AI Prediction is Ready! 🚀</h2>
                        <p style="color: #4b5563;">Hello {user_name},</p>
                        <p style="color: #4b5563;">The AI has successfully analyzed your business data and generated your MIT-Standard Business Plan and profit forecast.</p>
                        <a href="http://localhost:3000/history" style="display: inline-block; background-color: #476DDC; color: white; text-decoration: none; padding: 12px 24px; border-radius: 8px; font-weight: bold; margin-top: 10px;">View Your Report</a>
                    </div>
                </body>
            </html>
            """
            # Send quietly in the background
            background_tasks.add_task(send_html_email, user_email, "Your AI Business Prediction is Ready!", email_html)

        if notifs.get("push_mobile", True) == True:
            push_tokens = extract_push_token_values(prefs_data)
            if push_tokens:
                background_tasks.add_task(
                    send_expo_push_notifications,
                    push_tokens=push_tokens,
                    title="Prediction completed",
                    body=f"Your BizSense AI report for {payload.business_id} is ready.",
                    data={"business_id": payload.business_id, "type": "prediction_complete"},
                )

        return final_response

    except Exception as e:
        print(f"🔥 MASSIVE CRASH LOG: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Prediction Endpoint Error: {str(e)}")


# ==========================================
# PATCHED: SECURE PREDICTION HISTORY ENDPOINT
# ==========================================
@router.get("/history/{business_id}")
def get_prediction_history(business_id: str, current_user: dict = Depends(get_current_user)):
    """
    Fetches all past AI predictions and financial forecasts for a specific business.
    SECURED: Checks if the current user actually owns the requested business_id.
    """
    try:
        sme_id = current_user["sme_id"]

        # 🛡️ SECURITY CHECK 1: Does this user own an owner_profile?
        owner_res = supabase.table("owner").select("owner_id").eq("sme_id", sme_id).execute()
        if len(owner_res.data) == 0:
            raise HTTPException(status_code=403, detail="Access Denied: No owner profile found.")
        owner_id = owner_res.data[0]["owner_id"]

        # 🛡️ SECURITY CHECK 2: Does this business belong to this owner?
        biz_res = supabase.table("business").select("business_id").eq("owner_id", owner_id).eq("business_id", business_id).execute()
        if len(biz_res.data) == 0:
            raise HTTPException(status_code=403, detail="Access Denied: You do not own this business data.")

        # If they pass the checks, fetch their private data securely
        surv_res = supabase.table("survival_prediction") \
            .select("*") \
            .eq("business_id", business_id) \
            .order("created_at", desc=True) \
            .execute()
            
        growth_res = supabase.table("growth_forecast") \
            .select("*") \
            .eq("business_id", business_id) \
            .order("created_at", desc=True) \
            .execute()

        return {
            "status": "Success",
            "message": "Prediction history retrieved successfully!",
            "data": {
                "business_id": business_id,
                "survival_history": surv_res.data,
                "growth_history": growth_res.data
            }
        }

    except HTTPException as he:
        # Pass through our security HTTP exceptions
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database Error: Could not fetch history. {str(e)}")

# ==========================================
# PATCHED: SECURE PDF UPLOAD ENDPOINT
# ==========================================
@router.post("/upload-pdf")
async def analyze_pdf_business_plan(
    business_id: str, 
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user) # 🛡️ Requires login
):
    """
    Allows a user to upload a PDF Business Plan.
    SECURED: Enforces strict 5MB size limits, MIME-type verification, and ownership checks.
    """
    try:
        sme_id = current_user["sme_id"]

        # 🛡️ SECURITY CHECK 1: Ownership (IDOR Protection)
        owner_res = supabase.table("owner").select("owner_id").eq("sme_id", sme_id).execute()
        if len(owner_res.data) == 0:
            raise HTTPException(status_code=403, detail="Access Denied.")
            
        biz_res = supabase.table("business").select("business_id").eq("owner_id", owner_res.data[0]["owner_id"]).eq("business_id", business_id).execute()
        if len(biz_res.data) == 0:
            raise HTTPException(status_code=403, detail="Access Denied: You do not own this business.")

        # 🛡️ SECURITY CHECK 2: True MIME-Type Validation
        if file.content_type != "application/pdf":
            raise HTTPException(status_code=400, detail="Invalid file. Only authentic PDF documents are allowed.")

        # 🛡️ SECURITY CHECK 3: Memory Exhaustion Prevention (Max 5MB)
        MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 Megabytes
        
        # Read up to 5MB + 1 extra byte
        pdf_bytes = await file.read(MAX_FILE_SIZE + 1)
        
        if len(pdf_bytes) > MAX_FILE_SIZE:
            raise HTTPException(status_code=413, detail="Payload Too Large: File exceeds the 5MB limit.")
            
        # 1. Ask Gemini to extract the structured ML features from the safe PDF bytes
        ml_input = extract_ml_features_from_pdf(pdf_bytes)
        
        if "error" in ml_input:
            raise HTTPException(status_code=500, detail="Failed to read data from PDF.")
            
        # 2. Feed the extracted data straight into CatBoost/XGBoost
        print(f"🧠 Running ML Analysis using PDF data for Business ID: {business_id}")
        ai_results = run_predictions(ml_input)
        
        # 3. Ask Gemini to write the final Advisory Report based on the ML results
        ai_payload = generate_business_report(ml_input, ai_results)
        
        return {
            "status": "Success",
            "message": "PDF Analyzed Successfully!",
            "extracted_data": ml_input,
            "predictions": ai_results,
            "advisory_report": ai_payload
        }

    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PDF Processing Error: {str(e)}")




# ==========================================
# PDF EXPORT ENDPOINT
# ==========================================
@router.get("/download-report/{business_id}")
def download_pdf_report(business_id: str, current_user: dict = Depends(get_current_user)):
    """
    Fetches the latest AI report from the database and converts it into
    a highly professional, downloadable PDF document for banks and investors.
    SECURED: Requires login and verifies the user owns this business.
    """
    try:
        sme_id = current_user["sme_id"]

        # Security check 1: does this user have an owner profile?
        owner_res = supabase.table("owner").select("owner_id").eq("sme_id", sme_id).execute()
        if len(owner_res.data) == 0:
            raise HTTPException(status_code=403, detail="Access Denied: No owner profile found.")
        owner_id = owner_res.data[0]["owner_id"]

        # Security check 2: does this business belong to this owner?
        biz_res = supabase.table("business").select("business_id").eq("owner_id", owner_id).eq("business_id", business_id).execute()
        if len(biz_res.data) == 0:
            raise HTTPException(status_code=403, detail="Access Denied: You do not own this business.")

        # 1. Fetch the latest report from the database
        res = supabase.table("growth_forecast") \
            .select("full_report") \
            .eq("business_id", business_id) \
            .order("created_at", desc=True) \
            .limit(1).execute()
            
        if not res.data or not res.data[0].get("full_report"):
            raise HTTPException(status_code=404, detail="No report found for this business.")
            
        report_data = res.data[0]["full_report"]

        # 2. Setup the PDF Canvas (in memory)
        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter)
        styles = getSampleStyleSheet()
        Story = [] # This array will hold all our paragraphs

        # 3. Build the PDF Content
        # Title
        Story.append(Paragraph("BizSense AI Advisory Report", styles['Title']))
        Story.append(Spacer(1, 20))

        # Main Text Sections
        sections = [
            ("Executive Summary", report_data.get("executive_summary", "")),
            ("Prediction Explanation", report_data.get("prediction_explanation", "")),
            ("Optimal Business Model", report_data.get("optimal_business_model", "")),
            ("Cameroon Tax Breakdown", report_data.get("cameroon_tax_breakdown", ""))
        ]

        for title, text in sections:
            Story.append(Paragraph(title, styles['Heading2']))
            Story.append(Paragraph(text, styles['Normal']))
            Story.append(Spacer(1, 12))

        # Recommendations (Bullet points)
        Story.append(Paragraph("Future Recommendations", styles['Heading2']))
        for rec in report_data.get("future_recommendations", []):
            Story.append(Paragraph(f"• {rec}", styles['Normal']))
            Story.append(Spacer(1, 6))

        # 4. Generate the PDF
        doc.build(Story)
        buffer.seek(0) # Rewind the buffer to the beginning

        # 5. Return as a file download prompt to the browser
        return StreamingResponse(
            buffer, 
            media_type="application/pdf", 
            headers={"Content-Disposition": f"attachment; filename=BizSense_Report_{business_id}.pdf"}
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PDF Generation Error: {str(e)}")
