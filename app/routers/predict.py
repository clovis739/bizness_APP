



import json
from io import BytesIO
from fastapi.responses import StreamingResponse
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet 
from fastapi import UploadFile, File 
from fastapi import APIRouter, HTTPException, Request 
from app.database import supabase
from app.schemas import PredictionRequest
from app.services.ml_service import run_predictions
from app.services.llm_service import generate_business_report 
from app.services.llm_service import extract_ml_features_from_pdf
from app.limiter import limiter 
from app.redis_client import redis_db 

router = APIRouter(
    prefix="/api/v1/predict",
    tags=["AI Predictions"]
)

# ==========================================
# PROTECTED AI GENERATION ENDPOINT WITH CACHING
# ==========================================
@router.post("/generate")
@limiter.limit("100/minute") # 🛡️ LIMITER: Adjust this to "5/day" for production
def generate_prediction(
    request: Request, 
    payload: PredictionRequest 
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

        growth_insert = {
            "business_id": payload.business_id,
            "predicted_profit_cfa": ai_results["projected_profit_cfa"],
            "growth_rate": 0.0,
            "chart_data": ai_payload.get("chart_data", {}),
            "full_report": ai_payload 
            # We now save the entire AI text!
        }
        
        supabase.table("growth_forecast").insert(growth_insert).execute()
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
            # Save to Redis for 24 hours (86400 seconds)
            redis_db.setex(
                name=cache_key, 
                time=86400, 
                value=json.dumps(final_response) 
            )

        return final_response

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Prediction Endpoint Error: {str(e)}")

        
@router.get("/history/{business_id}")
def get_prediction_history(business_id: str):
    """
    Fetches all past AI predictions and financial forecasts for a specific business.
    This will be used to populate the Entrepreneur's Next.js Dashboard.
    """
    try:
        # Step A: Fetch all past survival predictions for this business
        surv_res = supabase.table("survival_prediction") \
            .select("*") \
            .eq("business_id", business_id) \
            .order("created_at", desc=True) \
            .execute()
            
        # Step B: Fetch all past profit forecasts for this business
        growth_res = supabase.table("growth_forecast") \
            .select("*") \
            .eq("business_id", business_id) \
            .order("created_at", desc=True) \
            .execute()

        # Step C: Combine and return the data
        return {
            "status": "Success",
            "message": "Prediction history retrieved successfully!",
            "data": {
                "business_id": business_id,
                "survival_history": surv_res.data,
                "growth_history": growth_res.data
            }
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database Error: Could not fetch history. {str(e)}")


@router.post("/upload-pdf")
async def analyze_pdf_business_plan(business_id: str, file: UploadFile = File(...)):
    """
    Allows a user to upload a PDF Business Plan or Financial Statement.
    The AI extracts the data and automatically runs the Machine Learning prediction!
    """
    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are allowed.")
        
    try:
        # 1. Read the uploaded file into memory
        pdf_bytes = await file.read()
        
        # 2. Ask Gemini to extract the structured ML features from the PDF
        ml_input = extract_ml_features_from_pdf(pdf_bytes)
        
        if "error" in ml_input:
            raise HTTPException(status_code=500, detail="Failed to read data from PDF.")
            
        # 3. Feed the extracted data straight into CatBoost/XGBoost!
        print(f"🧠 Running ML Analysis using PDF data for Business ID: {business_id}")
        ai_results = run_predictions(ml_input)
        
        # 4. Ask Gemini to write the final Advisory Report based on the ML results
        ai_payload = generate_business_report(ml_input, ai_results)
        
        return {
            "status": "Success",
            "message": "PDF Analyzed Successfully!",
            "extracted_data": ml_input,
            "predictions": ai_results,
            "advisory_report": ai_payload
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PDF Processing Error: {str(e)}")




# ==========================================
# PDF EXPORT ENDPOINT
# ==========================================
@router.get("/download-report/{business_id}")
def download_pdf_report(business_id: str):
    """
    Fetches the latest AI report from the database and converts it into 
    a highly professional, downloadable PDF document for banks and investors.
    """
    try:
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
        Story.append(Paragraph("BizNess AI Advisory Report", styles['Title']))
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
            headers={"Content-Disposition": f"attachment; filename=BizNess_Report_{business_id}.pdf"}
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PDF Generation Error: {str(e)}")        