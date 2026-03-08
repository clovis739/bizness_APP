

from fastapi import APIRouter, HTTPException, Response
from app.database import supabase
from app.schemas import SMERegistration, SMELogin, ForgotPassword, ResetPassword
import bcrypt
import random
from datetime import datetime, timedelta, timezone
from app.database import supabase, log_audit_action 



# Initialize the Router
router = APIRouter(
    prefix="/api/v1/auth",
    tags=["Authentication"]
)

# Helper function to encrypt passwords
def hash_password(password: str) -> str:
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')

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
            httponly=True,   # Hides the cookie from frontend JavaScript (Huge security boost!)
            secure=False,    # Set to True in production when using HTTPS
            samesite="lax",
            max_age=86400    # Cookie expires in 1 day (60 * 60 * 24)
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
        if len(user_res.data) == 0:
            return {"status": "Success", "message": "If the email exists, an OTP has been sent."}

        otp_code = str(random.randint(100000, 999999))
        expiry_time = datetime.now(timezone.utc) + timedelta(minutes=15)
        
        supabase.table("sme").update({"reset_otp": otp_code, "otp_expiry": expiry_time.isoformat()}).eq("email", request.email).execute()

        print(f"\n=== MOCK EMAIL SENT ===\nTo: {request.email}\nOTP: {otp_code}\n=======================\n")
        
        return {"status": "Success", "message": "OTP generated. Check console!"}
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