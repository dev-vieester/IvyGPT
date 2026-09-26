import smtplib
from email.message import EmailMessage

from celery import Celery

from ivy_gpt.config import settings


celery_app = Celery(
    "ivy_gpt",
    broker=settings.redis_url,
    backend=settings.redis_url
)


@celery_app.task(name="ivy_gpt.send_otp_email")
def send_otp_email(email: str, otp: str) -> None:
    subject = "Your IvyGPT verification code"
    body = f"Your IvyGPT verification code is {otp}. It expires in {settings.otp_expire_minutes} minutes."

    if not settings.smtp_host:
        print(f"[IvyGPT OTP] email={email} otp={otp}")
        return

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = settings.smtp_from_email
    message["To"] = email
    message.set_content(body)

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
        server.starttls()

        if settings.smtp_username and settings.smtp_password:
            server.login(settings.smtp_username, settings.smtp_password)

        server.send_message(message)
