

from fastapi import APIRouter, HTTPException, Response
from app.database import supabase
from app.schemas import SMERegistration, SMELogin, ForgotPassword, ResetPassword, GoogleToken, MagicLinkRequest, MagicLinkVerify
import bcrypt
import requests
from pydantic import BaseModel
import uuid
import random
from datetime import datetime, timedelta, timezone
from app.database import supabase, log_audit_action 
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
from dotenv import load_dotenv


# Force Python to read the .env file
load_dotenv()


# Initialize the Router
router = APIRouter(
    prefix="/api/v1/auth",
    tags=["Authentication"]
)

# Helper function to encrypt passwords
def hash_password(password: str) -> str:
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')


# Helper function to send real HTML emails
def send_otp_email(receiver_email: str, otp_code: str):
    sender_email = os.getenv("SMTP_EMAIL")
    sender_password = os.getenv("SMTP_PASSWORD")

    # Fallback to console if you forgot to set your .env variables
    if not sender_email or not sender_password:
        print(f"\n⚠️ WARNING: SMTP Credentials missing in .env! \nOTP for {receiver_email}: {otp_code}\n")
        return

    message = MIMEMultipart("alternative")
    message["Subject"] = "Your BizSense OS Password Reset Code"
    message["From"] = f"BizSense OS <{sender_email}>"
    message["To"] = receiver_email

    # Beautiful HTML Email Template matching your branding
    html = f"""
    <html>
      <body style="font-family: Arial, sans-serif; color: #333; background-color: #f8f9fa; padding: 20px;">
        <div style="max-w: 500px; margin: 0 auto; background-color: #ffffff; padding: 30px; border-radius: 15px; border: 1px solid #eaeaea;">
            <h2 style="color: #111827; margin-top: 0;">Password Reset Request</h2>
            <p style="color: #4b5563; line-height: 1.5;">You requested to reset your BizSense OS password. Please use the verification code below to securely access your account.</p>
            
            <div style="background-color: #f0f4ff; border: 1px solid #dde5fb; padding: 20px; text-align: center; border-radius: 10px; margin: 25px 0;">
                <h1 style="color: #476DDC; letter-spacing: 8px; margin: 0; font-size: 32px;">{otp_code}</h1>
            </div>
            
            <p style="color: #4b5563; font-size: 13px;">This code will expire in <strong>15 minutes</strong>.</p>
            <p style="color: #9ca3af; font-size: 12px; margin-top: 30px;">If you did not request this reset, please ignore this email or contact support.</p>
        </div>
      </body>
    </html>
    """
    
    part = MIMEText(html, "html")
    message.attach(part)

    try:
        # Connect to Gmail's secure SMTP server
        server = smtplib.SMTP_SSL("smtp.gmail.com", 465)
        server.login(sender_email, sender_password)
        server.sendmail(sender_email, receiver_email, message.as_string())
        server.quit()
    except Exception as e:
        print(f"🔥 SMTP ERROR: {e}")
        raise HTTPException(status_code=500, detail="Failed to send email. Please check server configuration.")

@router.post("/register")
def register_sme(user_data: SMERegistration):
    try:
        existing_user = supabase.table("sme").select("*").eq("email", user_data.email).execute()
        if len(existing_user.data) > 0:
            raise HTTPException(status_code=400, detail="An account with this email already exists.")

        secure_password = hash_password(user_data.password)
        new_sme = {"name": user_data.name, "email": user_data.email, "password_hash": secure_password}
        response = supabase.table("sme").insert(new_sme).execute()
        
        return {"status": "Success", "message": "SME Account Created!", "sme_id": response.data[0]['sme_id']}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/login")
def login_sme(credentials: SMELogin, response: Response):
    try:
        res = supabase.table("sme").select("*").eq("email", credentials.email).execute()
        if len(res.data) == 0:
            raise HTTPException(status_code=400, detail="Invalid email or password.")

        user = res.data[0]
        stored_hash = user['password_hash'].encode('utf-8')
        provided_password = credentials.password.encode('utf-8')

        if not bcrypt.checkpw(provided_password, stored_hash):
            raise HTTPException(status_code=400, detail="Invalid email or password.")

        # ==========================================
        # SET THE SECURE SESSION COOKIE
        # ==========================================
        response.set_cookie(
            key="bizness_session",
            value=user['sme_id'],
            httponly=True,   
            # Hides the cookie from frontend JavaScript (Huge security boost!)
            secure=False,    
            # Set to True in production when using HTTPS
            samesite="lax",
            max_age=86400    
            # Cookie expires in 1 day (60 * 60 * 24)
        )
        log_audit_action(
        actor_id=user['sme_id'],
        actor_type='SME',
        action_type='LOGIN_SUCCESS',
        description=f"{user['email']} successfully logged in."
    )

        return {"status": "Success", "message": f"Welcome back, {user['name']}!", "sme_id": user['sme_id']}
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    


@router.post("/forgot-password")
def forgot_password(request: ForgotPassword):
    try:
        user_res = supabase.table("sme").select("*").eq("email", request.email).execute()
        
        # Security Best Practice: Always return success even if email doesn't exist to prevent email scraping
        if len(user_res.data) == 0:
            return {"status": "Success", "message": "If the email exists, an OTP has been sent."}

        # Generate OTP and Expiry
        otp_code = str(random.randint(100000, 999999))
        expiry_time = datetime.now(timezone.utc) + timedelta(minutes=15)
        
        # Save to Supabase
        supabase.table("sme").update({
            "reset_otp": otp_code, 
            "otp_expiry": expiry_time.isoformat()
        }).eq("email", request.email).execute()

        # ==========================================
        # SEND THE ACTUAL EMAIL
        # ==========================================
        send_otp_email(request.email, otp_code)
        
        return {"status": "Success", "message": "OTP sent to your email!"}
        
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))




@router.post("/reset-password")
def reset_password(request: ResetPassword):
    try:
        user_res = supabase.table("sme").select("*").eq("email", request.email).execute()
        if len(user_res.data) == 0:
            raise HTTPException(status_code=400, detail="Invalid request.")
            
        user = user_res.data[0]
        if user.get("reset_otp") != request.otp:
            raise HTTPException(status_code=400, detail="Invalid OTP code.")
            
        expiry_str = user.get("otp_expiry")
        if not expiry_str:
            raise HTTPException(status_code=400, detail="No OTP requested.")
            
        clean_str = expiry_str.replace("Z", "+00:00")
        expiry_time = datetime.fromisoformat(clean_str)
        if expiry_time.tzinfo is None:
            expiry_time = expiry_time.replace(tzinfo=timezone.utc)
            
        if datetime.now(timezone.utc) > expiry_time:
            raise HTTPException(status_code=400, detail="OTP has expired.")

        secure_new_password = hash_password(request.new_password)
        supabase.table("sme").update({"password_hash": secure_new_password, "reset_otp": None, "otp_expiry": None}).eq("email", request.email).execute()

        return {"status": "Success", "message": "Password reset successfully!"}
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))



@router.post("/google")
def google_auth(token_data: GoogleToken, response: Response):
    try:
        # 1. Verify token with Google's official API
        google_response = requests.get(
            "https://www.googleapis.com/oauth2/v3/userinfo",
            headers={"Authorization": f"Bearer {token_data.access_token}"}
        )
        
        if google_response.status_code != 200:
            raise HTTPException(status_code=400, detail="Invalid Google token")
            
        user_info = google_response.json()
        email = user_info.get("email")
        name = user_info.get("name", "Google User")

        if not email:
            raise HTTPException(status_code=400, detail="Google account has no email")

        # 2. Check if user already exists in Supabase
        res = supabase.table("sme").select("*").eq("email", email).execute()
        
        if len(res.data) > 0:
            # User exists! Grab their ID
            sme_id = res.data[0]['sme_id']
        else:
            # 3. New User! Create an account automatically.
            # We generate a massive, random password hash since they use Google to log in
            dummy_password = hash_password(str(uuid.uuid4()) + "google_auth_bypass")
            new_sme = {
                "name": name, 
                "email": email, 
                "password_hash": dummy_password
            }
            insert_res = supabase.table("sme").insert(new_sme).execute()
            sme_id = insert_res.data[0]['sme_id']

        # 4. Set the exact same secure Session Cookie as standard login!
        response.set_cookie(
            key="bizness_session",
            value=sme_id,
            httponly=True,
            secure=False, # True in production
            samesite="lax",
            max_age=86400
        )
        
        log_audit_action(
            actor_id=sme_id,
            actor_type='SME',
            action_type='GOOGLE_LOGIN_SUCCESS',
            description=f"{email} logged in via Google."
        )

        return {"status": "Success", "message": "Google Login Successful", "sme_id": sme_id}

    except HTTPException as he:
        raise he
    except Exception as e:
        print(f"🔥 GOOGLE AUTH ERROR: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error during Google Auth") 








def send_magic_link_email(receiver_email: str, token: str):
    sender_email = os.getenv("SMTP_EMAIL")
    sender_password = os.getenv("SMTP_PASSWORD")
    
    if not sender_email or not sender_password:
        print(f"\n⚠️ WARNING: SMTP Credentials missing! Link: http://localhost:3000/verify-link?email={receiver_email}&token={token}\n")
        return

    message = MIMEMultipart("alternative")
    message["Subject"] = "Sign in to BizSense OS"
    message["From"] = f"BizSense OS <{sender_email}>"
    message["To"] = receiver_email

    # The link points to a new Next.js route we are about to build
    magic_link = f"http://localhost:3000/verify-link?email={receiver_email}&token={token}"

    html = f"""
    <html>
      <body style="font-family: Arial, sans-serif; color: #333; background-color: #f8f9fa; padding: 20px;">
        <div style="max-w: 500px; margin: 0 auto; background-color: #ffffff; padding: 30px; border-radius: 15px; border: 1px solid #eaeaea; text-align: center;">
            <h2 style="color: #111827; margin-top: 0;">Your Magic Link</h2>
            <p style="color: #4b5563; line-height: 1.5; margin-bottom: 30px;">Click the secure button below to instantly sign in to your BizSense OS dashboard.</p>
            
            <a href="{magic_link}" style="background-color: #476DDC; color: #ffffff; padding: 14px 28px; text-decoration: none; border-radius: 10px; font-weight: bold; display: inline-block;">Sign In to BizSense</a>
            
            <p style="color: #9ca3af; font-size: 12px; margin-top: 40px;">This link expires in 15 minutes. If you did not request this, please ignore this email.</p>
        </div>
      </body>
    </html>
    """
    
    part = MIMEText(html, "html")
    message.attach(part)

    try:
        server = smtplib.SMTP_SSL("smtp.gmail.com", 465)
        server.login(sender_email, sender_password)
        server.sendmail(sender_email, receiver_email, message.as_string())
        server.quit()
    except Exception as e:
        print(f"🔥 SMTP ERROR: {e}")

@router.post("/magic-link/request")
def request_magic_link(request: MagicLinkRequest):
    try:
        # 1. Check if user exists. If not, create a skeleton account for them!
        res = supabase.table("sme").select("*").eq("email", request.email).execute()
        
        if len(res.data) == 0:
            dummy_password = hash_password(str(uuid.uuid4()) + "magic_link_dummy")
            new_sme = {"name": "New SME", "email": request.email, "password_hash": dummy_password}
            supabase.table("sme").insert(new_sme).execute()

        # 2. Generate a secure, 32-character token
        secure_token = uuid.uuid4().hex
        expiry_time = datetime.now(timezone.utc) + timedelta(minutes=15)

        # 3. Save it to the database (reusing our OTP columns to keep the DB clean!)
        supabase.table("sme").update({
            "reset_otp": secure_token, 
            "otp_expiry": expiry_time.isoformat()
        }).eq("email", request.email).execute()

        # 4. Send the email
        send_magic_link_email(request.email, secure_token)

        return {"status": "Success", "message": "Magic link sent to your email!"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/magic-link/verify")
def verify_magic_link(request: MagicLinkVerify, response: Response):
    try:
        res = supabase.table("sme").select("*").eq("email", request.email).execute()
        if len(res.data) == 0:
            raise HTTPException(status_code=400, detail="Invalid request.")
            
        user = res.data[0]
        
        # Check Token Match
        if user.get("reset_otp") != request.token:
            raise HTTPException(status_code=400, detail="Invalid or expired magic link.")
            
        # Check Expiry
        expiry_str = user.get("otp_expiry")
        if not expiry_str:
            raise HTTPException(status_code=400, detail="No magic link requested.")
            
        clean_str = expiry_str.replace("Z", "+00:00")
        expiry_time = datetime.fromisoformat(clean_str)
        if expiry_time.tzinfo is None:
            expiry_time = expiry_time.replace(tzinfo=timezone.utc)
            
        if datetime.now(timezone.utc) > expiry_time:
            raise HTTPException(status_code=400, detail="Magic link has expired.")

        # CLEAR the token so it can't be used twice
        supabase.table("sme").update({"reset_otp": None, "otp_expiry": None}).eq("email", request.email).execute()

        # SET THE SECURE LOGIN COOKIE
        response.set_cookie(
            key="bizness_session",
            value=user['sme_id'],
            httponly=True,
            secure=False,
            samesite="lax",
            max_age=86400
        )

        return {"status": "Success", "message": "Successfully logged in!", "sme_id": user['sme_id']}
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))




@router.post("/logout")
def logout_sme(response: Response):
    """Destroys the secure HttpOnly cookie to log the user out."""
    response.delete_cookie(
        key="bizness_session",
        httponly=True,
        secure=False,
        samesite="lax"
    )
    return {"status": "Success", "message": "Logged out successfully"}