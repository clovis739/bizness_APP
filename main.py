

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from apscheduler.schedulers.background import BackgroundScheduler
from app.database import supabase
from app.routers import auth, business, predict, communication
from app.services.ml_service import load_models
from app.routers.communication import send_email
from app.services.ml_service import survival_model, profit_model
from fastapi import HTTPException

import sentry_sdk

# --- NEW IMPORTS FOR RATE LIMITING ---
from app.limiter import limiter
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
# -------------------------------------





# ==========================================
# SENTRY CONFIGURATION
# ==========================================
# 2. Initialize Sentry before the FastAPI app starts
sentry_sdk.init(
    dsn="https://d0a45c4a114b3855b58b91266c302cb8@o4510100157693952.ingest.us.sentry.io/4510984763211776",
    traces_sample_rate=1.0,    # Captures 100% of traffic for performance monitoring
    profiles_sample_rate=1.0,  # Profiles the speed of your Python functions (like the ML models!)
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
        daily_tip = "Daily BizNess Tip: Keeping your energy overhead strictly below 15% increases your 3-year survival probability by over 40% in the Cameroonian market. Check your dashboard today!"
        for sub in subscribers:
            send_email(sub['email'], "Your Daily SME Insight 📈", daily_tip)
    except Exception as e:
        print(f"❌ Daily newsletter failed: {e}")

# ==========================================
# MODERN LIFESPAN MANAGER (Replaces on_event)
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
# Notice we pass the lifespan function into the FastAPI app here!
app = FastAPI(
    title="BizNess SME Analytics API",
    description="Backend for the Data-Driven Smart SME Analytics Platform",
    version="1.0.0",
    lifespan=lifespan
    )

# ==========================================
# REGISTER THE RATE LIMITER
# ==========================================
# 1. Attach the limiter to the FastAPI app state
app.state.limiter = limiter

# 2. Tell FastAPI to return a standard '429 Too Many Requests' error 
# instead of crashing when someone hits the limit.
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)



# CORS Configuration
origins = ["http://localhost:3000", "http://127.0.0.1:3000"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Plug in routers
app.include_router(auth.router)
app.include_router(business.router)
app.include_router(predict.router)
app.include_router(communication.router)




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
        
    # 2. Check AI Models Pulse (from ml_service)
    if survival_model is not None and profit_model is not None:
        health_status["ai_models"] = "online"
        
    # 3. Determine overall status
    if health_status["database"] == "online" and health_status["ai_models"] == "online":
        return {"status": "Healthy 🟢", "details": health_status}
    else:
        # Return a 503 Service Unavailable if something is broken
        raise HTTPException(status_code=503, detail={"status": "Degraded 🔴", "details": health_status})


@app.get("/")
def read_root():
    return {"message": "✅ BizNess FastAPI Server is running!"}




