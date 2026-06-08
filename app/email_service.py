import base64
import os
import smtplib
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import requests
from fastapi import HTTPException


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _email_from() -> str:
    return os.getenv("EMAIL_FROM") or f"BizSense OS <{os.getenv('SMTP_EMAIL', '')}>"


def _email_provider() -> str:
    return os.getenv("EMAIL_PROVIDER", "auto").strip().lower()


def send_resend_email(
    to_email: str,
    subject: str,
    html_content: str,
    file_name: str | None = None,
    file_data: bytes | None = None,
):
    api_key = os.getenv("RESEND_API_KEY")
    if not api_key:
        return None

    payload = {
        "from": _email_from(),
        "to": [to_email],
        "subject": subject,
        "html": html_content,
    }

    if file_name and file_data:
        payload["attachments"] = [
            {
                "filename": file_name,
                "content": base64.b64encode(file_data).decode("ascii"),
            }
        ]

    try:
        response = requests.post(
            "https://api.resend.com/emails",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=15,
        )
        if response.status_code >= 400:
            print(f"Resend email error: {response.status_code} {response.text}")
            return False
        return True
    except Exception as error:
        print(f"Resend email exception: {error}")
        return False


def build_html_message(
    *,
    to_email: str,
    subject: str,
    html_content: str,
    file_name: str | None = None,
    file_data: bytes | None = None,
):
    message = MIMEMultipart("alternative")
    message["From"] = _email_from()
    message["To"] = to_email
    message["Subject"] = subject
    message.attach(MIMEText(html_content, "html"))

    if file_name and file_data:
        attachment = MIMEApplication(file_data, Name=file_name)
        attachment["Content-Disposition"] = f'attachment; filename="{file_name}"'
        message.attach(attachment)

    return message


def open_smtp_server():
    smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_username = os.getenv("SMTP_USERNAME") or os.getenv("SMTP_EMAIL")
    smtp_password = os.getenv("SMTP_PASSWORD")
    smtp_timeout = int(os.getenv("SMTP_TIMEOUT", "10"))
    use_ssl = _env_bool("SMTP_USE_SSL", smtp_port == 465)
    use_starttls = _env_bool("SMTP_USE_STARTTLS", not use_ssl)

    if not smtp_host or not smtp_username or not smtp_password:
        print("SMTP configuration missing. Skipping SMTP email.")
        return None

    try:
        if use_ssl:
            server = smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=smtp_timeout)
        else:
            server = smtplib.SMTP(smtp_host, smtp_port, timeout=smtp_timeout)
            if use_starttls:
                server.starttls()

        server.login(smtp_username, smtp_password)
        return server
    except Exception as error:
        print(f"Failed to open SMTP connection to {smtp_host}:{smtp_port}: {error}")
        return None


def send_smtp_email(
    to_email: str,
    subject: str,
    html_content: str,
    file_name: str | None = None,
    file_data: bytes | None = None,
    server=None,
):
    owns_server = server is None
    smtp_server = server or open_smtp_server()
    if smtp_server is None:
        return False

    try:
        smtp_server.send_message(
            build_html_message(
                to_email=to_email,
                subject=subject,
                html_content=html_content,
                file_name=file_name,
                file_data=file_data,
            )
        )
        print(f"Email sent to {to_email} via SMTP")
        return True
    except Exception as error:
        print(f"Failed to send email to {to_email}: {error}")
        return False
    finally:
        if owns_server:
            try:
                smtp_server.quit()
            except Exception:
                pass


def send_email(
    to_email: str,
    subject: str,
    html_content: str,
    file_name: str | None = None,
    file_data: bytes | None = None,
    server=None,
    raise_on_error: bool = False,
) -> bool:
    provider = _email_provider()

    if provider == "smtp":
        sent = send_smtp_email(to_email, subject, html_content, file_name, file_data, server)
    elif provider == "resend":
        sent = send_resend_email(to_email, subject, html_content, file_name, file_data) is True
    else:
        resend_result = send_resend_email(to_email, subject, html_content, file_name, file_data)
        if resend_result is True:
            print(f"Email sent to {to_email} via Resend")
            return True
        sent = send_smtp_email(to_email, subject, html_content, file_name, file_data, server)

    if sent:
        return True

    if raise_on_error:
        raise HTTPException(status_code=500, detail="Failed to send email.")
    return False