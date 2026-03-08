import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from fastapi import APIRouter, HTTPException, BackgroundTasks
from app.database import supabase
from app.schemas import SubscribeRequest, ContactRequest
from dotenv import load_dotenv

load_dotenv()
SMTP_EMAIL = os.getenv("SMTP_EMAIL")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL")

router = APIRouter(
    prefix="/api/v1/communication",
    tags=["Communication & Engagement"]
)

# --- HELPER FUNCTION: SEND EMAIL ---
def send_email(to_email: str, subject: str, body: str):
    if not SMTP_EMAIL or not SMTP_PASSWORD:
        print("⚠️ Email credentials missing in .env! Skipping real email.")
        return
        
    try:
        msg = MIMEMultipart()
        msg['From'] = SMTP_EMAIL
        msg['To'] = to_email
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain'))

        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(SMTP_EMAIL, SMTP_PASSWORD)
        server.send_message(msg)
        server.quit()
        print(f"✅ Email successfully sent to {to_email}")
    except Exception as e:
        print(f"❌ Failed to send email: {e}")

# --- 1. CONTACT US (Sends email to Admin) ---
@router.post("/contact")
def submit_contact_form(request: ContactRequest, background_tasks: BackgroundTasks):
    try:
        # Save to database
        message_data = {"name": request.name, "email": request.email, "subject": request.subject, "message": request.message}
        supabase.table("contact_messages").insert(message_data).execute()
        
        # Fire off the email in the background so the user doesn't have to wait!
        email_body = f"New message from {request.name} ({request.email}):\n\n{request.message}"
        background_tasks.add_task(send_email, ADMIN_EMAIL, f"SUPPORT REQUEST: {request.subject}", email_body)
        
        return {"status": "Success", "message": "Your message has been sent to our support team!"}
    except Exception as e:
        raise HTTPException(status_code=500, detail="Could not process contact form.")

# --- 2. SUBSCRIBE TO NEWSLETTER ---
@router.post("/subscribe")
def subscribe_newsletter(request: SubscribeRequest, background_tasks: BackgroundTasks):
    try:
        supabase.table("subscribers").insert({"email": request.email}).execute()
        
        # Send a welcome email immediately!
        welcome_msg = "Welcome to BizNess Analytics! You will now receive daily insights on the Cameroonian SME market."
        background_tasks.add_task(send_email, request.email, "Welcome to BizNess!", welcome_msg)
        
        return {"status": "Success", "message": "Successfully subscribed!"}
    except Exception as e:
        return {"status": "Success", "message": "You are already subscribed or an error occurred."}

# --- 3. GOOGLE AUTH URL GENERATOR ---
@router.get("/auth/google/url")
def get_google_auth_url():
    """
    Returns the Supabase OAuth URL. The Next.js frontend will redirect the user here.
    """
    try:
        # Ask Supabase to generate the Google Login link
        res = supabase.auth.sign_in_with_oauth({
            "provider": "google",
            "options": {"redirectTo": "http://localhost:3000/auth/callback"}
        })
        return {"status": "Success", "url": res.url}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"OAuth Error: {str(e)}")