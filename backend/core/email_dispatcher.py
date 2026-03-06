import os
import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import List

logger = logging.getLogger(__name__)

class EmailDispatcher:
    """
    Dispatcher responsible for sending Email alerts via SMTP.
    Supports broad alerts for public health anomalies to both users and officials.
    """
    def __init__(self):
        self.smtp_server = os.getenv("SMTP_SERVER")
        self.smtp_port = int(os.getenv("SMTP_PORT", "587"))
        self.smtp_user = os.getenv("SMTP_USER")
        self.smtp_password = os.getenv("SMTP_PASSWORD")
        self.email_from = os.getenv("EMAIL_FROM")
        
        self.enabled = all([self.smtp_server, self.smtp_user, self.smtp_password, self.email_from])
        
        if self.enabled:
            logger.info(f"Email Dispatcher initialized (SMTP: {self.smtp_server}).")
        else:
            logger.warning("Email Dispatcher disabled — SMTP credentials not found in environment.")

    def send_email(self, to_email: str, subject: str, body_html: str, body_text: str) -> bool:
        """Sends a single email via SMTP."""
        if not self.enabled:
            logger.warning(f"Email Dispatcher disabled. Would have sent to {to_email}: {subject}")
            return False
            
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = self.email_from
            msg["To"] = to_email

            part1 = MIMEText(body_text, "plain")
            part2 = MIMEText(body_html, "html")

            msg.attach(part1)
            msg.attach(part2)

            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.smtp_user, self.smtp_password)
                server.sendmail(self.email_from, to_email, msg.as_string())
            
            logger.info(f"Email alert sent successfully to {to_email}.")
            return True
        except Exception as e:
            logger.error(f"Failed to send email to {to_email}: {e}")
            return False

    def broadcast_anomaly_alert(self, users: List[object], disease: str, location: str, risk_level: str):
        """Broadcasts an anomaly alert email to a list of users."""
        if not self.enabled:
            logger.info(f"Email Broadcast skipped (Disabled): {disease} outbreak detected in {location}.")
            return

        subject = f"⚠️ ADIPHAS ALERT: Critical {disease} Anomaly in {location}"
        
        # Simple HTML template
        html_content = f"""
        <html>
            <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
                <div style="background-color: #f8d7da; padding: 20px; border-radius: 8px; border: 1px solid #f5c6cb;">
                    <h2 style="color: #721c24;">Critical Health Alert</h2>
                    <p>ADIPHAS Intelligence has detected a <strong>{risk_level}</strong> risk anomaly for <strong>{disease}</strong> in <strong>{location}</strong>.</p>
                    <p><strong>Immediate surveillance and precaution are advised.</strong></p>
                    <hr>
                    <p style="font-size: 0.8em; color: #666;">This is an automated alert from the GraceTech ADIS-PHAS Monitoring System.</p>
                </div>
            </body>
        </html>
        """
        
        text_content = f"ADIPHAS ALERT: Critical {disease} anomaly detected in {location}. Risk Level: {risk_level}. Immediate surveillance required."
        
        for user in users:
            if hasattr(user, 'email') and user.email:
                self.send_email(user.email, subject, html_content, text_content)

# Singleton instance
email_dispatcher = EmailDispatcher()
