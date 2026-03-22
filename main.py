import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from apscheduler.schedulers.background import BackgroundScheduler
import sentry_sdk
from dotenv import load_dotenv

# Load Environment Variables for Production
load_dotenv()

from app.database import supabase
from app.routers import auth, business, predict, communication, dashboard
from app import settings, market
from app.services.ml_service import load_models, survival_model, profit_model

# Adjust this import based on exactly where your communication file lives!
from app.routers.communication import send_html_email as send_email 

# --- NEW IMPORTS FOR RATE LIMITING ---
from app.limiter import limiter
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
# -------------------------------------

# ==========================================
# SENTRY CONFIGURATION (Production Error Tracking)
# ==========================================
sentry_sdk.init(
    dsn="https://d0a45c4a114b3855b58b91266c302cb8@o4510100157693952.ingest.us.sentry.io/4510984763211776",
    traces_sample_rate=1.0,    
    profiles_sample_rate=1.0, 
    send_default_pii=True 
)

# ==========================================
# AUTOMATED DAILY EMAILS TASK
# ==========================================
def send_daily_newsletter():
    print("⏰ Running Daily Newsletter Task...")
    try:
        res = supabase.table("subscribers").select("email").execute()
        subscribers = res.data
        
        # Upgraded to our beautiful HTML format!
        daily_tip_html = """
        <html>
            <body style="font-family: Arial, sans-serif; padding: 20px; background: #f8f9fa;">
                <div style="max-w: 600px; margin: 0 auto; background: white; padding: 30px; border-radius: 12px; border-top: 5px solid #476DDC;">
                    <h2 style="color: #111827;">Your Daily SME Insight 📈</h2>
                    <p style="color: #4b5563; font-size: 15px; line-height: 1.6;">
                        <strong>BizSense Tip:</strong> Keeping your energy overhead strictly below 15% increases your 3-year survival probability by over 40% in the Cameroonian market. 
                    </p>
                    <a href="https://bizsense.cm" style="display: inline-block; background-color: #476DDC; color: white; text-decoration: none; padding: 12px 24px; border-radius: 8px; font-weight: bold; margin-top: 15px;">Open Your Dashboard</a>
                </div>
            </body>
        </html>
        """
        for sub in subscribers:
            send_email(sub['email'], "Your Daily BizSense Insight 📈", daily_tip_html)
    except Exception as e:
        print(f"❌ Daily newsletter failed: {e}")

# ==========================================
# MODERN LIFESPAN MANAGER
# ==========================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- 1. STARTUP PHASE ---
    print("🚀 Server is starting up...")
    load_models()
    
    scheduler = BackgroundScheduler()
    scheduler.add_job(send_daily_newsletter, 'cron', hour=8, minute=0)
    scheduler.start()
    print("⏱️ Background Scheduler started.")
    
    yield  # <-- This tells FastAPI: "The server is now running!"
    
    # --- 2. SHUTDOWN PHASE ---
    print("🛑 Server is shutting down...")
    scheduler.shutdown()
    print("⏱️ Background Scheduler stopped safely.")


# ==========================================
# APP INITIALIZATION
# ==========================================
app = FastAPI(
    title="BizSense OS API",
    description="Enterprise Backend for the Data-Driven Smart SME Analytics Platform",
    version="1.0.0",
    lifespan=lifespan
)

# ==========================================
# REGISTER THE RATE LIMITER
# ==========================================
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


# ==========================================
# CORS CONFIGURATION (CRITICAL FOR PRODUCTION)
# ==========================================
# This tells the Python server which websites are allowed to talk to it.
origins = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "https://bizsense.com",                   # Your future custom domain
    "https://www.bizsense.com",               # Custom domain with www
    os.getenv("FRONTEND_URL", "https://your-vercel-app-url.vercel.app") # Fallback for Vercel
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True, # MUST be True for our secure HttpOnly Cookies to work across domains!
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==========================================
# PLUG IN ROUTERS
# ==========================================
app.include_router(auth.router)
app.include_router(business.router)
app.include_router(predict.router)
app.include_router(communication.router)
app.include_router(dashboard.router)
app.include_router(settings.router)
app.include_router(market.router)


# ==========================================
# SYSTEM ROUTES
# ==========================================
@app.get("/health", tags=["System Operations"])
def health_check():
    """
    Deep Health Check: Verifies the API, Database, and ML Models.
    External monitoring tools will ping this route every 60 seconds.
    """
    health_status = {"api": "online", "database": "offline", "ai_models": "offline"}
    
    # 1. Check Database Pulse
    try:
        supabase.table("sme").select("sme_id").limit(1).execute()
        health_status["database"] = "online"
    except Exception:
        pass # DB is unreachable
        
    # 2. Check AI Models Pulse
    if survival_model is not None and profit_model is not None:
        health_status["ai_models"] = "online"
        
    # 3. Determine overall status
    if health_status["database"] == "online" and health_status["ai_models"] == "online":
        return {"status": "Healthy 🟢", "details": health_status}
    else:
        raise HTTPException(status_code=503, detail={"status": "Degraded 🔴", "details": health_status})

@app.get("/")
def read_root():
    return {"message": "✅ BizSense OS FastAPI Server is running online!"}