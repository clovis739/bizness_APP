import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from fastapi import APIRouter, HTTPException, BackgroundTasks, Form, UploadFile, File
from app.database import supabase
from app.schemas import SubscribeRequest
from dotenv import load_dotenv

load_dotenv()
SMTP_EMAIL = os.getenv("SMTP_EMAIL")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL")

router = APIRouter(
    prefix="/api/v1/communication",
    tags=["Communication & Engagement"]
)

# --- UPGRADED HTML EMAIL SENDER ---
def send_html_email(to_email: str, subject: str, html_content: str, file_name: str = None, file_data: bytes = None):
    if not SMTP_EMAIL or not SMTP_PASSWORD:
        print("⚠️ Email credentials missing in .env! Skipping real email.")
        return
        
    try:
        # Use 'alternative' so email clients know it contains HTML
        msg = MIMEMultipart("alternative")
        msg['From'] = f"BizSense OS <{SMTP_EMAIL}>"
        msg['To'] = to_email
        msg['Subject'] = subject

        # Attach the HTML design
        msg.attach(MIMEText(html_content, "html"))

        # Attach the file if it exists
        if file_name and file_data:
            part = MIMEApplication(file_data, Name=file_name)
            part['Content-Disposition'] = f'attachment; filename="{file_name}"'
            msg.attach(part)

        server = smtplib.SMTP_SSL('smtp.gmail.com', 465)
        server.login(SMTP_EMAIL, SMTP_PASSWORD)
        server.send_message(msg)
        server.quit()
        print(f"✅ Branded Email sent to {to_email}")
    except Exception as e:
        print(f"❌ Failed to send email: {e}")


# --- 1. BRANDED SUPPORT TICKET (For Admins) ---
@router.post("/contact")
async def submit_contact_form(
    background_tasks: BackgroundTasks,
    name: str = Form(...),
    email: str = Form(...),
    subject: str = Form(...),
    message: str = Form(...),
    priority: str = Form("Normal"),
    file: UploadFile = File(None)
):
    try:
        file_name = file.filename if file else None
        file_bytes = await file.read() if file else None

        # Save to database
        message_data = {
            "name": name, 
            "email": email, 
            "subject": subject, 
            "message": message, 
            "priority": priority
        }
        supabase.table("contact_messages").insert(message_data).execute()
        
        # Color code the priority for the admin's inbox
        priority_color = "#dc2626" if priority.lower() == "high" else ("#ea580c" if priority.lower() == "medium" else "#16a34a")

        admin_html = f"""
        <html>
          <body style="font-family: Arial, sans-serif; background-color: #f8f9fa; padding: 20px;">
            <div style="max-w: 600px; margin: 0 auto; background: white; padding: 30px; border-radius: 12px; border-top: 5px solid #476DDC;">
                <h2 style="margin-top: 0; color: #111827;">New Support Ticket</h2>
                <div style="background-color: {priority_color}15; border-left: 4px solid {priority_color}; padding: 12px; margin-bottom: 20px;">
                    <strong style="color: {priority_color};">Priority: {priority.upper()}</strong>
                </div>
                <p><strong>From:</strong> {name} ({email})</p>
                <p><strong>Subject:</strong> {subject}</p>
                <hr style="border: none; border-top: 1px solid #eaeaea; margin: 20px 0;" />
                <p style="color: #4b5563; line-height: 1.6; white-space: pre-wrap;">{message}</p>
                {f'<p style="margin-top: 20px; font-size: 13px; color: #6b7280;">📎 <strong>Attachment:</strong> {file_name}</p>' if file_name else ''}
            </div>
          </body>
        </html>
        """

        background_tasks.add_task(send_html_email, ADMIN_EMAIL, f"[{priority.upper()}] {subject}", admin_html, file_name, file_bytes)
        return {"status": "Success", "message": "Message sent!"}
    except Exception as e:
        raise HTTPException(status_code=500, detail="Could not process contact form.")


# --- 2. BRANDED NEWSLETTER WELCOME (For Users) ---
@router.post("/subscribe")
def subscribe_newsletter(request: SubscribeRequest, background_tasks: BackgroundTasks):
    try:
        supabase.table("subscribers").insert({"email": request.email}).execute()
        
        # Beautiful HTML Template matching your Next.js UI
        welcome_html = f"""
        <html>
          <body style="font-family: Arial, sans-serif; background-color: #f8f9fa; padding: 40px 20px; text-align: center;">
            <div style="max-w: 500px; margin: 0 auto; background: white; padding: 40px 30px; border-radius: 20px; border: 1px solid #eaeaea; box-shadow: 0 4px 14px rgba(71, 109, 220, 0.05);">
                
                <div style="background-color: #476DDC; width: 60px; height: 60px; border-radius: 16px; margin: 0 auto 20px auto; display: flex; align-items: center; justify-content: center;">
                    <h1 style="color: white; margin: 0; font-size: 24px;">📊</h1>
                </div>

                <h2 style="color: #111827; font-size: 24px; margin-bottom: 10px;">Welcome to BizSense OS</h2>
                <p style="color: #6b7280; font-size: 15px; line-height: 1.6; margin-bottom: 30px;">
                    Thank you for subscribing! You are now on the list to receive our exclusive daily business insights, funding opportunities, and market trends tailored specifically for African SMEs.
                </p>
                
                <a href="http://localhost:3000" style="display: inline-block; background-color: #476DDC; color: white; text-decoration: none; padding: 14px 28px; border-radius: 12px; font-weight: bold; font-size: 15px;">
                    Go to your Dashboard
                </a>
                
                <p style="color: #9ca3af; font-size: 12px; margin-top: 40px;">
                    © 2026 BizSense OS. Empowering African Entrepreneurs.<br/>
                    If you didn't request this, you can safely ignore this email.
                </p>
            </div>
          </body>
        </html>
        """
        
        background_tasks.add_task(send_html_email, request.email, "Welcome to BizSense OS!", welcome_html)
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





from app.schemas import BroadcastRequest

# --- 4. MASS EMAIL BROADCAST (For Admin Use) ---
@router.post("/broadcast")
def send_newsletter_broadcast(request: BroadcastRequest, background_tasks: BackgroundTasks):
    """
    Fetches all emails from the 'subscribers' table and sends them your HTML newsletter.
    """
    # 1. Very basic security check so hackers can't spam your users
    if request.admin_password != "MySuperSecretAdminPassword123!":
        raise HTTPException(status_code=401, detail="Unauthorized")

    try:
        # 2. Fetch all subscribers from Supabase
        res = supabase.table("subscribers").select("email").execute()
        subscribers = res.data

        if not subscribers:
            return {"status": "Error", "message": "No subscribers found in database."}

        # 3. Loop through every subscriber and queue an email
        count = 0
        for sub in subscribers:
            user_email = sub["email"]
            background_tasks.add_task(send_html_email, user_email, request.subject, request.html_content)
            count += 1

        return {"status": "Success", "message": f"Broadcast successfully queued for {count} users!"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    