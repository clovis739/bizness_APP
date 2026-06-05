import os
import smtplib
from datetime import datetime
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from dotenv import load_dotenv
from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile

from app.database import supabase
from app.email_service import open_smtp_server, send_email
from app.schemas import BroadcastRequest, SubscribeRequest
from app.security import get_current_user

load_dotenv()
SMTP_EMAIL = os.getenv("SMTP_EMAIL")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL")

router = APIRouter(
    prefix="/api/v1/communication",
    tags=["Communication & Engagement"]
)


# Format the stored support-ticket timestamp into the short UI style used by mobile.
def _format_ticket_date(value: str | None) -> str:
    if not value:
        return "Recently"

    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.strftime("%b %d, %Y")
    except ValueError:
        return value


# Infer the support category from subjects stored like "[Billing] My issue".
def _extract_ticket_category(subject: str | None) -> str:
    if not subject:
        return "General"

    if subject.startswith("[") and "]" in subject:
        return subject.split("]", 1)[0].strip("[]") or "General"

    return "General"


# Build one branded HTML email payload, optionally with an attachment.
def _build_html_message(
    *,
    to_email: str,
    subject: str,
    html_content: str,
    file_name: str = None,
    file_data: bytes = None,
):
    message = MIMEMultipart("alternative")
    message["From"] = f"BizSense OS <{SMTP_EMAIL}>"
    message["To"] = to_email
    message["Subject"] = subject
    message.attach(MIMEText(html_content, "html"))

    if file_name and file_data:
        attachment = MIMEApplication(file_data, Name=file_name)
        attachment["Content-Disposition"] = f'attachment; filename="{file_name}"'
        message.attach(attachment)

    return message


# Open one SMTP connection with an explicit timeout so back-to-back sends are more reliable.
def _open_smtp_server():
    if not SMTP_EMAIL or not SMTP_PASSWORD:
        print("Email credentials missing in .env. Skipping real email.")
        return None

    return open_smtp_server()


# Send one branded HTML email, optionally reusing an existing SMTP connection.
def send_html_email(
    to_email: str,
    subject: str,
    html_content: str,
    file_name: str = None,
    file_data: bytes = None,
    server=None,
):
    return send_email(
        to_email=to_email,
        subject=subject,
        html_content=html_content,
        file_name=file_name,
        file_data=file_data,
        server=server,
        raise_on_error=False,
    )


# Send the subscriber thank-you email and the admin alert over one shared SMTP session.
def send_newsletter_subscription_emails(subscriber_email: str, welcome_html: str, admin_html: str):
    smtp_server = _open_smtp_server()
    if smtp_server is None:
        return

    try:
        send_html_email(
            subscriber_email,
            "Welcome to BizSense OS!",
            welcome_html,
            server=smtp_server,
        )
        if ADMIN_EMAIL:
            send_html_email(
                ADMIN_EMAIL,
                "New BizSense newsletter subscriber",
                admin_html,
                server=smtp_server,
            )
    finally:
        try:
            smtp_server.quit()
        except Exception:
            pass


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

        # Persist the support request before notifying the admin inbox.
        message_data = {
            "name": name,
            "email": email,
            "subject": subject,
            "message": message,
            "priority": priority
        }
        supabase.table("contact_messages").insert(message_data).execute()

        # Style the admin email based on urgency so support can triage quickly.
        priority_color = "#dc2626" if priority.lower() == "high" else ("#ea580c" if priority.lower() == "medium" else "#16a34a")

        admin_html = f"""
        <html>
          <body style="font-family: Arial, sans-serif; background-color: #f8f9fa; padding: 20px;">
            <div style="max-width: 600px; margin: 0 auto; background: white; padding: 30px; border-radius: 12px; border-top: 5px solid #476DDC;">
                <h2 style="margin-top: 0; color: #111827;">New Support Ticket</h2>
                <div style="background-color: {priority_color}15; border-left: 4px solid {priority_color}; padding: 12px; margin-bottom: 20px;">
                    <strong style="color: {priority_color};">Priority: {priority.upper()}</strong>
                </div>
                <p><strong>From:</strong> {name} ({email})</p>
                <p><strong>Subject:</strong> {subject}</p>
                <hr style="border: none; border-top: 1px solid #eaeaea; margin: 20px 0;" />
                <p style="color: #4b5563; line-height: 1.6; white-space: pre-wrap;">{message}</p>
                {f'<p style="margin-top: 20px; font-size: 13px; color: #6b7280;">Attachment: <strong>{file_name}</strong></p>' if file_name else ''}
            </div>
          </body>
        </html>
        """

        background_tasks.add_task(
            send_html_email,
            ADMIN_EMAIL,
            f"[{priority.upper()}] {subject}",
            admin_html,
            file_name,
            file_bytes,
        )
        return {"status": "Success", "message": "Message sent!"}
    except Exception as error:
        raise HTTPException(status_code=500, detail="Could not process contact form.") from error


@router.get("/tickets")
def list_contact_tickets(current_user: dict = Depends(get_current_user)):
    try:
        result = (
            supabase
            .table("contact_messages")
            .select("*")
            .eq("email", current_user["email"])
            .execute()
        )

        rows = result.data or []
        rows.sort(
            key=lambda row: row.get("created_at") or row.get("updated_at") or "",
            reverse=True,
        )

        tickets = []
        for index, row in enumerate(rows, start=1):
            raw_status = str(row.get("status") or "Open").strip().lower()
            status = "Resolved" if raw_status in {"resolved", "closed", "done"} else "Open"
            subject = str(row.get("subject") or "Support request")
            ticket_id = (
                row.get("ticket_id")
                or row.get("id")
                or row.get("message_id")
                or f"T-{index:04d}"
            )

            tickets.append({
                "id": f"#{ticket_id}" if not str(ticket_id).startswith("#") else str(ticket_id),
                "subject": subject,
                "category": _extract_ticket_category(subject),
                "status": status,
                "date": _format_ticket_date(row.get("created_at") or row.get("updated_at")),
            })

        return {"status": "Success", "tickets": tickets}
    except Exception as error:
        raise HTTPException(status_code=500, detail="Could not load support tickets.") from error


@router.post("/subscribe")
def subscribe_newsletter(request: SubscribeRequest, background_tasks: BackgroundTasks):
    try:
        # Avoid duplicate subscriptions while preserving the same success semantics.
        existing_subscriber = (
            supabase
            .table("subscribers")
            .select("email")
            .eq("email", request.email)
            .execute()
        )
        if existing_subscriber.data:
            return {"status": "Success", "message": "You are already subscribed."}

        supabase.table("subscribers").insert({"email": request.email}).execute()

        welcome_html = f"""
        <html>
          <body style="font-family: Arial, sans-serif; background-color: #f8f9fa; padding: 40px 20px; text-align: center;">
            <div style="max-width: 500px; margin: 0 auto; background: white; padding: 40px 30px; border-radius: 20px; border: 1px solid #eaeaea; box-shadow: 0 4px 14px rgba(71, 109, 220, 0.05);">
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

        admin_html = f"""
        <html>
          <body style="font-family: Arial, sans-serif; background-color: #f8f9fa; padding: 20px;">
            <div style="max-width: 600px; margin: 0 auto; background: white; padding: 30px; border-radius: 12px; border-top: 5px solid #476DDC;">
              <h2 style="margin-top: 0; color: #111827;">New Newsletter Subscriber</h2>
              <p style="color: #4b5563; line-height: 1.6;">
                A new user has subscribed to the BizSense newsletter.
              </p>
              <div style="background-color: #EFF6FF; border: 1px solid #BFDBFE; border-radius: 12px; padding: 16px; margin-top: 20px;">
                <p style="margin: 0; color: #1E3A8A;"><strong>Email:</strong> {request.email}</p>
              </div>
            </div>
          </body>
        </html>
        """

        background_tasks.add_task(
            send_newsletter_subscription_emails,
            request.email,
            welcome_html,
            admin_html,
        )
        return {"status": "Success", "message": "Successfully subscribed!"}
    except Exception as error:
        print(f"Newsletter subscribe failed for {request.email}: {error}")
        raise HTTPException(status_code=500, detail="Could not complete newsletter subscription.") from error


@router.get("/auth/google/url")
def get_google_auth_url():
    """
    Returns the Supabase OAuth URL. The Next.js frontend will redirect the user here.
    """
    try:
        res = supabase.auth.sign_in_with_oauth({
            "provider": "google",
            "options": {"redirectTo": "http://localhost:3000/auth/callback"}
        })
        return {"status": "Success", "url": res.url}
    except Exception as error:
        raise HTTPException(status_code=500, detail=f"OAuth Error: {str(error)}") from error


@router.post("/broadcast")
def send_newsletter_broadcast(request: BroadcastRequest, background_tasks: BackgroundTasks):
    """
    Fetch every newsletter subscriber and queue a broadcast HTML email.
    """
    if request.admin_password != "MySuperSecretAdminPassword123!":
        raise HTTPException(status_code=401, detail="Unauthorized")

    try:
        result = supabase.table("subscribers").select("email").execute()
        subscribers = result.data

        if not subscribers:
            return {"status": "Error", "message": "No subscribers found in database."}

        count = 0
        for subscriber in subscribers:
            background_tasks.add_task(
                send_html_email,
                subscriber["email"],
                request.subject,
                request.html_content,
            )
            count += 1

        return {"status": "Success", "message": f"Broadcast successfully queued for {count} users!"}
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error)) from error
