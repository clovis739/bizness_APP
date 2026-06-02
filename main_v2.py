import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from apscheduler.schedulers.background import BackgroundScheduler
import sentry_sdk
from dotenv import load_dotenv

load_dotenv()

# Shared infrastructure reused from V1
from app.database import supabase
from app.limiter import limiter
from app.routers.communication import send_html_email as send_email

# V1 routers reused as-is
from app.routers import auth, communication, dashboard
from app import settings, market

# V2-only routers
from app_v2.routers.business_v2 import router as business_v2_router
from app_v2.routers.predict_v2  import router as predict_v2_router

# V3 model loader
from app_v2.services.ml_service_v2 import load_models

# Rate limiter
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

# ============================================================
# SENTRY - same DSN as V1
# ============================================================
sentry_sdk.init(
    dsn=os.getenv("SENTRY_DSN", ""),
    traces_sample_rate=1.0,
    profiles_sample_rate=1.0,
    send_default_pii=True
)

# ============================================================
# DAILY NEWSLETTER (shared with V1)
# ============================================================
def send_daily_newsletter():
    print("Running Daily Newsletter (V2 server)...")
    try:
        res = supabase.table("subscribers").select("email").execute()
        tip_html = """
        <html>
            <body style="font-family:Arial,sans-serif;padding:20px;background:#f8f9fa;">
                <div style="max-width:600px;margin:0 auto;background:#fff;padding:30px;
                            border-radius:12px;border-top:5px solid #3B7FFF;">
                    <h2 style="color:#111827;">Your Daily SME Insight</h2>
                    <p style="color:#4b5563;font-size:15px;line-height:1.6;">
                        <strong>BizSense Tip:</strong> Keeping energy overhead below 15% increases
                        your 3-year survival probability by over 40% in the Cameroonian market.
                    </p>
                    <a href="https://bizsense.cm"
                       style="display:inline-block;background:#3B7FFF;color:#fff;
                              text-decoration:none;padding:12px 24px;border-radius:8px;
                              font-weight:bold;margin-top:15px;">
                        Open Your Dashboard
                    </a>
                </div>
            </body>
        </html>
        """
        for sub in res.data:
            send_email(sub["email"], "Your Daily BizSense Insight", tip_html)
    except Exception as e:
        print(f"Daily newsletter failed: {e}")


# ============================================================
# LIFESPAN - startup / shutdown
# ============================================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    print("BizSense OS V2 starting up...")
    # Load V3 models into memory
    load_models()

    scheduler = BackgroundScheduler()
    scheduler.add_job(send_daily_newsletter, "cron", hour=8, minute=0)
    scheduler.start()
    print("Background scheduler started.")

    yield

    print("BizSense OS V2 shutting down...")
    scheduler.shutdown()
    print("Scheduler stopped.")


# ============================================================
# APP INIT
# ============================================================
app = FastAPI(
    title="BizSense OS API V2",
    description=(
        "V2 backend - V3 ML models (CatBoost + LightGBM + Cox PH), "
        "Groq LLM (Llama 3.3 70B), full 49-feature pipeline."
    ),
    version="2.0.0",
    lifespan=lifespan
)

# Serve uploaded avatars/logos
uploads_dir = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(uploads_dir, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=uploads_dir), name="uploads")

# Rate limiter
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS
base_origins = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:3001",
    "http://127.0.0.1:3001",
    "http://localhost:3002",
    "http://127.0.0.1:3002",
    "https://bizsense.cm",
    "https://www.bizsense.cm",
    "https://bizness-frontend-cyan.vercel.app",
]
configured_origins = [
    origin.strip()
    for origin in os.getenv("FRONTEND_URL", "https://your-vercel-app-url.vercel.app").split(",")
    if origin.strip()
]
origins = list(dict.fromkeys(base_origins + configured_origins))
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================
# ROUTERS
# Reused from V1: auth, dashboard, communication, market, settings
# New V2: business_v2, predict_v2
# ============================================================
app.include_router(auth.router)            # /api/v1/auth - unchanged
app.include_router(dashboard.router)       # /api/v1/dashboard - unchanged
app.include_router(communication.router)   # /api/v1/communication - unchanged
app.include_router(settings.router)        # /api/v1/settings - unchanged
app.include_router(market.router)          # /api/v1/market - unchanged

app.include_router(business_v2_router)     # /api/v2/business
app.include_router(predict_v2_router)      # /api/v2/predict


# ============================================================
# SYSTEM ROUTES
# ============================================================
@app.get("/health", tags=["System"])
def health_check():
    from app_v2.services.ml_service_v2 import survival_model, profit_model
    status = {"api": "online", "database": "offline", "v3_models": "offline"}

    try:
        supabase.table("sme").select("sme_id").limit(1).execute()
        status["database"] = "online"
    except Exception:
        pass

    if survival_model is not None and profit_model is not None:
        status["v3_models"] = "online"

    if status["database"] == "online" and status["v3_models"] == "online":
        return {"status": "Healthy", "version": "2.0.0", "details": status}
    raise HTTPException(status_code=503, detail={"status": "Degraded", "details": status})


@app.get("/")
def root():
    return {
        "message": "BizSense OS V2 is running!",
        "v1_endpoints": "/api/v1/...",
        "v2_endpoints": "/api/v2/...",
        "docs": "/docs"
    }
