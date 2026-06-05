import base64
import os
import smtplib
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import requests
from fastapi import HTTPException


def _email_from() -> str:
    return os.getenv("EMAIL_FROM") or f"BizSense OS <{os.getenv('SMTP_EMAIL', '')}>"


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
    smtp_email = os.getenv("SMTP_EMAIL")
    smtp_password = os.getenv("SMTP_PASSWORD")
    if not smtp_email or not smtp_password:
        print("Email credentials missing in .env. Skipping SMTP email.")
        return None

    try:
        server = smtplib.SMTP("smtp.gmail.com", 587, timeout=8)
        server.starttls()
        server.login(smtp_email, smtp_password)
        return server
    except Exception as error:
        print(f"Failed to open SMTP connection: {error}")
        return None


def send_email(
    to_email: str,
    subject: str,
    html_content: str,
    file_name: str | None = None,
    file_data: bytes | None = None,
    server=None,
    raise_on_error: bool = False,
) -> bool:
    api_result = send_resend_email(to_email, subject, html_content, file_name, file_data)
    if api_result is True:
        print(f"Email sent to {to_email} via Resend")
        return True
    if api_result is False and raise_on_error:
        raise HTTPException(status_code=500, detail="Failed to send email through email provider.")

    owns_server = server is None
    smtp_server = server or open_smtp_server()
    if smtp_server is None:
        if raise_on_error:
            raise HTTPException(status_code=500, detail="Failed to connect to email server.")
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
        if raise_on_error:
            raise HTTPException(status_code=500, detail="Failed to send email.") from error
        return False
    finally:
        if owns_server:
            try:
                smtp_server.quit()
            except Exception:
                pass