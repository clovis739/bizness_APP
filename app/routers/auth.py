import os
import random
import smtplib
import uuid
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from urllib.parse import urlencode

import bcrypt
import requests
from dotenv import load_dotenv
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Response

from app.database import log_audit_action, supabase
from app.schemas import (
    ChangePasswordRequest,
    ForgotPassword,
    GoogleToken,
    MagicLinkRequest,
    MagicLinkVerify,
    MobileRefreshRequest,
    ResetPassword,
    SMELogin,
    SMERegistration,
    SupabaseEmailLinkExchange,
)
from app.security import (
    ACCESS_TOKEN_TTL_MINUTES,
    REFRESH_TOKEN_TTL_DAYS,
    create_mobile_access_token,
    create_mobile_refresh_token,
    decode_mobile_token,
    get_current_user,
)

load_dotenv()

# Set COOKIE_SECURE=true in production. Cross-domain web deployments also need SameSite=None.
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "false").lower() == "true"
COOKIE_SAMESITE = os.getenv("COOKIE_SAMESITE", "none" if COOKIE_SECURE else "lax").lower()

MOBILE_MAGIC_LINK_BASE_URL = os.getenv(
    "MOBILE_MAGIC_LINK_BASE_URL",
    "biznessmobileapp://magic-link",
)
WEB_MAGIC_LINK_BASE_URL = os.getenv(
    "WEB_MAGIC_LINK_BASE_URL",
    os.getenv("FRONTEND_URL", "http://localhost:3000").split(",")[0].strip().rstrip("/") + "/verify-link",
)
_supabase_url = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_AUTH_BASE_URL = f"{_supabase_url}/auth/v1" if _supabase_url else ""

router = APIRouter(prefix="/api/v1/auth", tags=["Authentication"])


def hash_password(password: str) -> str:
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def serialize_user(user: dict) -> dict:
    return {
        "name": user["name"],
        "email": user["email"],
        "sme_id": user["sme_id"],
        "preferences": user.get("preferences", {}),
    }


def build_mobile_auth_response(user: dict, message: str) -> dict:
    return {
        "status": "Success",
        "message": message,
        "sme_id": user["sme_id"],
        "user": serialize_user(user),
        "access_token": create_mobile_access_token(
            sme_id=user["sme_id"],
            email=user["email"],
        ),
        "refresh_token": create_mobile_refresh_token(
            sme_id=user["sme_id"],
            email=user["email"],
        ),
        "token_type": "bearer",
        "expires_in": ACCESS_TOKEN_TTL_MINUTES * 60,
        "refresh_expires_in": REFRESH_TOKEN_TTL_DAYS * 24 * 60 * 60,
    }


def get_user_by_email(email: str) -> dict | None:
    res = supabase.table("sme").select("*").eq("email", email).execute()
    if len(res.data) == 0:
        return None
    return res.data[0]


def create_sme_user(name: str, email: str, password_hash: str) -> dict:
    response = (
        supabase.table("sme")
        .insert({"name": name, "email": email, "password_hash": password_hash})
        .execute()
    )
    return response.data[0]


def get_or_create_google_user(access_token: str) -> tuple[dict, bool]:
    normalized_access_token = access_token.strip()
    if not normalized_access_token:
        raise HTTPException(status_code=400, detail="Google access token is required.")

    try:
        google_response = requests.get(
            "https://www.googleapis.com/oauth2/v3/userinfo",
            headers={"Authorization": f"Bearer {normalized_access_token}"},
            timeout=10,
        )
    except requests.RequestException as error:
        raise HTTPException(
            status_code=502,
            detail="Google authentication is temporarily unavailable.",
        ) from error

    if google_response.status_code != 200:
        raise HTTPException(status_code=400, detail="Invalid or expired Google access token.")

    try:
        user_info = google_response.json()
    except ValueError as error:
        raise HTTPException(
            status_code=502,
            detail="Google authentication returned an invalid response.",
        ) from error

    email = user_info.get("email")
    name = user_info.get("name", "Google User")

    if not email:
        raise HTTPException(status_code=400, detail="Google account has no email")

    existing_user = get_user_by_email(email)
    if existing_user:
        return existing_user, False

    dummy_password = hash_password(f"{uuid.uuid4()}google_auth_bypass")
    return create_sme_user(name=name, email=email, password_hash=dummy_password), True


def send_otp_email(receiver_email: str, otp_code: str):
    sender_email = os.getenv("SMTP_EMAIL")
    sender_password = os.getenv("SMTP_PASSWORD")

    if not sender_email or not sender_password:
        print(
            f"\nWARNING: SMTP credentials missing in .env.\nOTP for {receiver_email}: {otp_code}\n"
        )
        return

    message = MIMEMultipart("alternative")
    message["Subject"] = "Your BizSense OS Password Reset Code"
    message["From"] = f"BizSense OS <{sender_email}>"
    message["To"] = receiver_email

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

    message.attach(MIMEText(html, "html"))

    try:
        server = smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=15)
        server.login(sender_email, sender_password)
        server.sendmail(sender_email, receiver_email, message.as_string())
        server.quit()
    except Exception as error:
        print(f"SMTP ERROR: {error}")
        raise HTTPException(
            status_code=500,
            detail="Failed to send email. Please check server configuration.",
        ) from error


def send_magic_link_email(receiver_email: str, token: str):
    sender_email = os.getenv("SMTP_EMAIL")
    sender_password = os.getenv("SMTP_PASSWORD")
    magic_link = f"{WEB_MAGIC_LINK_BASE_URL}?{urlencode({'email': receiver_email, 'token': token})}"

    if not sender_email or not sender_password:
        print(f"\nWARNING: SMTP credentials missing! Link: {magic_link}\n")
        return

    message = MIMEMultipart("alternative")
    message["Subject"] = "Sign in to BizSense OS"
    message["From"] = f"BizSense OS <{sender_email}>"
    message["To"] = receiver_email

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

    message.attach(MIMEText(html, "html"))

    try:
        server = smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=15)
        server.login(sender_email, sender_password)
        server.sendmail(sender_email, receiver_email, message.as_string())
        server.quit()
    except Exception as error:
        # This function can run after the HTTP response has already been sent.
        # Log SMTP failures without raising, otherwise Starlette reports
        # "response already started" and the server records an ASGI exception.
        print(f"SMTP ERROR: {error}")
        return


def validate_magic_link_token(email: str, token: str) -> dict:
    user = get_user_by_email(email)
    if not user:
        raise HTTPException(status_code=400, detail="Invalid request.")

    # Compare against the stored "magic:" prefixed value
    if user.get("reset_otp") != "magic:" + token:
        raise HTTPException(status_code=400, detail="Invalid or expired magic link.")

    expiry_str = user.get("otp_expiry")
    if not expiry_str:
        raise HTTPException(status_code=400, detail="No magic link requested.")

    expiry_time = datetime.fromisoformat(expiry_str.replace("Z", "+00:00"))
    if expiry_time.tzinfo is None:
        expiry_time = expiry_time.replace(tzinfo=timezone.utc)

    if datetime.now(timezone.utc) > expiry_time:
        raise HTTPException(status_code=400, detail="Magic link has expired.")

    supabase.table("sme").update({"reset_otp": None, "otp_expiry": None}).eq(
        "email", email
    ).execute()
    return user


def request_supabase_email_link(email: str):
    supabase_key = os.getenv("SUPABASE_KEY", "")
    if not SUPABASE_AUTH_BASE_URL or not supabase_key:
        raise HTTPException(
            status_code=500,
            detail="Supabase email-link configuration is missing on the server.",
        )

    try:
        response = requests.post(
            f"{SUPABASE_AUTH_BASE_URL}/otp",
            headers={
                "apikey": supabase_key,
                "Authorization": f"Bearer {supabase_key}",
                "Content-Type": "application/json",
            },
            json={
                "email": email,
                "create_user": True,
                "email_redirect_to": MOBILE_MAGIC_LINK_BASE_URL,
            },
            timeout=10,
        )
    except requests.RequestException as error:
        raise HTTPException(
            status_code=502,
            detail="Supabase email-link service is temporarily unavailable.",
        ) from error

    if response.status_code not in {200, 201}:
        try:
            payload = response.json()
        except ValueError:
            payload = {}

        detail = payload.get("msg") or payload.get("error_description") or payload.get("error")
        raise HTTPException(
            status_code=400,
            detail=str(detail or "Supabase could not send the email link."),
        )


def get_or_create_supabase_email_user(access_token: str) -> tuple[dict, bool]:
    normalized_access_token = access_token.strip()
    supabase_key = os.getenv("SUPABASE_KEY", "")

    if not normalized_access_token:
        raise HTTPException(status_code=400, detail="Supabase access token is required.")

    if not SUPABASE_AUTH_BASE_URL or not supabase_key:
        raise HTTPException(
            status_code=500,
            detail="Supabase email-link configuration is missing on the server.",
        )

    try:
        response = requests.get(
            f"{SUPABASE_AUTH_BASE_URL}/user",
            headers={
                "apikey": supabase_key,
                "Authorization": f"Bearer {normalized_access_token}",
            },
            timeout=10,
        )
    except requests.RequestException as error:
        raise HTTPException(
            status_code=502,
            detail="Supabase email-link verification is temporarily unavailable.",
        ) from error

    if response.status_code != 200:
        raise HTTPException(
            status_code=400,
            detail="Invalid or expired Supabase email-link session.",
        )

    try:
        user_info = response.json()
    except ValueError as error:
        raise HTTPException(
            status_code=502,
            detail="Supabase email-link returned an invalid response.",
        ) from error

    email = user_info.get("email")
    metadata = user_info.get("user_metadata") or {}
    name = (
        metadata.get("full_name")
        or metadata.get("name")
        or (email.split("@", 1)[0] if email else "Email User")
    )

    if not email:
        raise HTTPException(status_code=400, detail="Supabase account has no email.")

    existing_user = get_user_by_email(email)
    if existing_user:
        return existing_user, False

    dummy_password = hash_password(f"{uuid.uuid4()}supabase_email_link_bypass")
    return create_sme_user(name=name, email=email, password_hash=dummy_password), True


@router.post("/register")
def register_sme(user_data: SMERegistration):
    try:
        if get_user_by_email(user_data.email):
            raise HTTPException(
                status_code=400,
                detail="An account with this email already exists.",
            )

        user = create_sme_user(
            name=user_data.name,
            email=user_data.email,
            password_hash=hash_password(user_data.password),
        )
        return {
            "status": "Success",
            "message": "SME Account Created!",
            "sme_id": user["sme_id"],
        }
    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error)) from error


@router.post("/mobile/register")
def mobile_register_sme(user_data: SMERegistration):
    try:
        if get_user_by_email(user_data.email):
            raise HTTPException(
                status_code=400,
                detail="An account with this email already exists.",
            )

        user = create_sme_user(
            name=user_data.name,
            email=user_data.email,
            password_hash=hash_password(user_data.password),
        )
        log_audit_action(
            actor_id=user["sme_id"],
            actor_type="SME",
            action_type="MOBILE_REGISTER_SUCCESS",
            description=f"{user['email']} created a mobile account.",
        )
        return build_mobile_auth_response(user, "Account created successfully.")
    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error)) from error


@router.post("/login")
def login_sme(credentials: SMELogin, response: Response):
    try:
        user = get_user_by_email(credentials.email)
        if not user:
            raise HTTPException(status_code=400, detail="Invalid email or password.")

        if not bcrypt.checkpw(
            credentials.password.encode("utf-8"),
            user["password_hash"].encode("utf-8"),
        ):
            raise HTTPException(status_code=400, detail="Invalid email or password.")

        response.set_cookie(
            key="bizness_session",
            value=user["sme_id"],
            httponly=True,
            secure=COOKIE_SECURE,
            samesite=COOKIE_SAMESITE,
            max_age=86400,
        )
        log_audit_action(
            actor_id=user["sme_id"],
            actor_type="SME",
            action_type="LOGIN_SUCCESS",
            description=f"{user['email']} successfully logged in.",
        )

        return {
            "status": "Success",
            "message": f"Welcome back, {user['name']}!",
            "sme_id": user["sme_id"],
        }
    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error)) from error


@router.post("/mobile/login")
def mobile_login_sme(credentials: SMELogin):
    try:
        user = get_user_by_email(credentials.email)
        if not user:
            raise HTTPException(status_code=400, detail="Invalid email or password.")

        if not bcrypt.checkpw(
            credentials.password.encode("utf-8"),
            user["password_hash"].encode("utf-8"),
        ):
            raise HTTPException(status_code=400, detail="Invalid email or password.")

        log_audit_action(
            actor_id=user["sme_id"],
            actor_type="SME",
            action_type="MOBILE_LOGIN_SUCCESS",
            description=f"{user['email']} successfully logged in on mobile.",
        )
        return build_mobile_auth_response(user, f"Welcome back, {user['name']}!")
    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error)) from error


@router.post("/forgot-password")
def forgot_password(request: ForgotPassword):
    try:
        user = get_user_by_email(request.email)
        if not user:
            return {
                "status": "Success",
                "message": "If the email exists, an OTP has been sent.",
            }

        otp_code = str(random.randint(100000, 999999))
        expiry_time = datetime.now(timezone.utc) + timedelta(minutes=15)
        # "otp:" prefix stops this token from being accepted as a magic link
        supabase.table("sme").update(
            {"reset_otp": "otp:" + otp_code, "otp_expiry": expiry_time.isoformat()}
        ).eq("email", request.email).execute()

        send_otp_email(request.email, otp_code)
        return {"status": "Success", "message": "OTP sent to your email!"}
    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error)) from error


@router.post("/reset-password")
def reset_password(request: ResetPassword):
    try:
        user = get_user_by_email(request.email)
        if not user:
            raise HTTPException(status_code=400, detail="Invalid request.")

        # Compare against the stored "otp:" prefixed value
        if user.get("reset_otp") != "otp:" + request.otp:
            raise HTTPException(status_code=400, detail="Invalid OTP code.")

        expiry_str = user.get("otp_expiry")
        if not expiry_str:
            raise HTTPException(status_code=400, detail="No OTP requested.")

        expiry_time = datetime.fromisoformat(expiry_str.replace("Z", "+00:00"))
        if expiry_time.tzinfo is None:
            expiry_time = expiry_time.replace(tzinfo=timezone.utc)

        if datetime.now(timezone.utc) > expiry_time:
            raise HTTPException(status_code=400, detail="OTP has expired.")

        supabase.table("sme").update(
            {
                "password_hash": hash_password(request.new_password),
                "reset_otp": None,
                "otp_expiry": None,
            }
        ).eq("email", request.email).execute()

        return {"status": "Success", "message": "Password reset successfully!"}
    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error)) from error


@router.post("/mobile/change-password")
def mobile_change_password(
    payload: ChangePasswordRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Allow an authenticated mobile user to change their password by confirming the current password first.
    """
    try:
        user = get_user_by_email(current_user["email"])
        if not user:
            raise HTTPException(status_code=404, detail="User account not found.")

        if not bcrypt.checkpw(
            payload.current_password.encode("utf-8"),
            user["password_hash"].encode("utf-8"),
        ):
            raise HTTPException(status_code=400, detail="Current password is incorrect.")

        if payload.current_password == payload.new_password:
            raise HTTPException(status_code=400, detail="New password must be different from the current password.")

        next_hash = hash_password(payload.new_password)

        # Update the SME credential source used by mobile login.
        supabase.table("sme").update({"password_hash": next_hash}).eq("sme_id", user["sme_id"]).execute()

        # Keep the mirrored owner password in sync because business registration copies it there.
        owner_res = supabase.table("owner").select("owner_id").eq("sme_id", user["sme_id"]).execute()
        if owner_res.data:
            supabase.table("owner").update({"password_hash": next_hash}).eq("owner_id", owner_res.data[0]["owner_id"]).execute()

        return {"status": "Success", "message": "Password changed successfully."}
    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error)) from error


@router.post("/google")
def google_auth(token_data: GoogleToken, response: Response):
    try:
        user, _created = get_or_create_google_user(token_data.access_token)
        response.set_cookie(
            key="bizness_session",
            value=user["sme_id"],
            httponly=True,
            secure=COOKIE_SECURE,
            samesite=COOKIE_SAMESITE,
            max_age=86400,
        )
        log_audit_action(
            actor_id=user["sme_id"],
            actor_type="SME",
            action_type="GOOGLE_LOGIN_SUCCESS",
            description=f"{user['email']} logged in via Google.",
        )
        return {
            "status": "Success",
            "message": "Google Login Successful",
            "sme_id": user["sme_id"],
        }
    except HTTPException:
        raise
    except Exception as error:
        print(f"GOOGLE AUTH ERROR: {error}")
        raise HTTPException(
            status_code=500,
            detail="Internal Server Error during Google Auth",
        ) from error


@router.post("/mobile/google")
def mobile_google_auth(token_data: GoogleToken):
    try:
        user, created = get_or_create_google_user(token_data.access_token)
        log_audit_action(
            actor_id=user["sme_id"],
            actor_type="SME",
            action_type="MOBILE_GOOGLE_LOGIN_SUCCESS",
            description=f"{user['email']} logged in via Google on mobile.",
        )
        message = (
            "Google account created successfully."
            if created
            else "Google login successful."
        )
        return build_mobile_auth_response(user, message)
    except HTTPException:
        raise
    except Exception as error:
        print(f"MOBILE GOOGLE AUTH ERROR: {error}")
        raise HTTPException(
            status_code=500,
            detail="Internal Server Error during mobile Google Auth",
        ) from error


@router.post("/mobile/email-link/request")
def mobile_request_supabase_email_link(request: MagicLinkRequest):
    try:
        request_supabase_email_link(request.email)
        return {
            "status": "Success",
            "message": "Email link sent successfully.",
        }
    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error)) from error


@router.post("/mobile/email-link/exchange")
def mobile_exchange_supabase_email_link(payload: SupabaseEmailLinkExchange):
    try:
        user, created = get_or_create_supabase_email_user(payload.access_token)
        log_audit_action(
            actor_id=user["sme_id"],
            actor_type="SME",
            action_type="MOBILE_EMAIL_LINK_SUCCESS",
            description=f"{user['email']} logged in with a Supabase email link on mobile.",
        )
        message = (
            "Email-link account created successfully."
            if created
            else "Email-link login successful."
        )
        return build_mobile_auth_response(user, message)
    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error)) from error


@router.post("/magic-link/request")
def request_magic_link(request: MagicLinkRequest, background_tasks: BackgroundTasks):
    try:
        user = get_user_by_email(request.email)
        if not user:
            create_sme_user(
                name="New SME",
                email=request.email,
                password_hash=hash_password(f"{uuid.uuid4()}magic_link_dummy"),
            )

        secure_token = uuid.uuid4().hex
        expiry_time = datetime.now(timezone.utc) + timedelta(minutes=15)
        # "magic:" prefix stops this token from being accepted as a password-reset OTP
        supabase.table("sme").update(
            {"reset_otp": "magic:" + secure_token, "otp_expiry": expiry_time.isoformat()}
        ).eq("email", request.email).execute()

        background_tasks.add_task(send_magic_link_email, request.email, secure_token)
        return {"status": "Success", "message": "Magic link queued. Check your email shortly."}
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error)) from error


@router.post("/magic-link/verify")
def verify_magic_link(request: MagicLinkVerify, response: Response):
    try:
        user = validate_magic_link_token(request.email, request.token)
        response.set_cookie(
            key="bizness_session",
            value=user["sme_id"],
            httponly=True,
            secure=COOKIE_SECURE,
            samesite=COOKIE_SAMESITE,
            max_age=86400,
        )
        return {
            "status": "Success",
            "message": "Successfully logged in!",
            "sme_id": user["sme_id"],
        }
    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error)) from error


@router.post("/mobile/magic-link/verify")
def mobile_verify_magic_link(request: MagicLinkVerify):
    try:
        user = validate_magic_link_token(request.email, request.token)
        log_audit_action(
            actor_id=user["sme_id"],
            actor_type="SME",
            action_type="MOBILE_MAGIC_LINK_SUCCESS",
            description=f"{user['email']} logged in with a magic link on mobile.",
        )
        return build_mobile_auth_response(user, "Successfully logged in!")
    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error)) from error


@router.post("/mobile/refresh")
def refresh_mobile_session(payload: MobileRefreshRequest):
    try:
        decoded = decode_mobile_token(payload.refresh_token, expected_type="refresh")
        user = get_user_by_email(str(decoded["email"]))
        if not user or user["sme_id"] != decoded["sub"]:
            raise HTTPException(status_code=401, detail="Refresh session is invalid.")

        return build_mobile_auth_response(user, "Session refreshed successfully.")
    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error)) from error


@router.post("/logout")
def logout_sme(response: Response):
    response.delete_cookie(
        key="bizness_session",
        httponly=True,
        secure=COOKIE_SECURE,
        samesite=COOKIE_SAMESITE,
    )
    return {"status": "Success", "message": "Logged out successfully"}


@router.post("/mobile/logout")
def mobile_logout_sme():
    return {"status": "Success", "message": "Logged out successfully"}
